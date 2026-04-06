"""
Wikidata-based entity linking helpers.

功能:
- 通过 Wikidata `wbsearchentities` API 生成候选实体
- （可选）使用 `sentence-transformers` 对上下文与候选描述进行相似度排序

实现上尽量保持轻量、对依赖容错：若未安装 `sentence-transformers`，使用简单启发式排序。
"""

from functools import lru_cache
import logging
from typing import List, Dict, Any, Optional, Tuple
import requests

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer, util

    _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as _e:  # pragma: no cover - optional dependency
    _EMBED_MODEL = None
    logger.debug("sentence-transformers not available: %s", _e)


@lru_cache(maxsize=2048)
def search_wikidata(
    term: str,
    limit: int = 5,
    language: str = "en",
    user_agent: str = "KG-Turing-Bot/1.0 (Academic Project)",
) -> List[Dict[str, Any]]:
    """调用 Wikidata 搜索 API，返回候选列表。

    返回项（每项为 dict）通常包含 `id`, `label`, `description` 等字段。
    在网络或 HTTP 错误时返回空列表以保证调用方鲁棒性。
    """
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": term,
        "language": language,
        "format": "json",
        "limit": limit,
    }
    headers = {"User-Agent": user_agent}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("search", [])
    except requests.RequestException as e:
        logger.debug("Wikidata search error for %s: %s", term, e)
        return []


def _score_candidates_by_context(
    context: str, mention: str, candidates: List[Dict[str, Any]]
) -> Tuple[List[tuple], bool]:
    """给候选实体排序：优先尝试向量语义相似度，失败时使用简单启发式得分。
    返回元组 `(scored_list, used_embedding)`，其中 `used_embedding` 表示是否使用了
    `sentence-transformers` 进行语义匹配。"""
    used_embedding = False
    if _EMBED_MODEL is not None and candidates:
        try:
            ctx_emb = _EMBED_MODEL.encode(context, convert_to_tensor=True)
            texts = [
                f"{c.get('label','')} {c.get('description','')}" for c in candidates
            ]
            cand_emb = _EMBED_MODEL.encode(texts, convert_to_tensor=True)
            sims = util.cos_sim(ctx_emb, cand_emb)[0].cpu().tolist()
            scored = [(c, float(s)) for c, s in zip(candidates, sims)]
            scored.sort(key=lambda x: x[1], reverse=True)
            used_embedding = True
            return scored, used_embedding
        except Exception as _e:  # pragma: no cover - model may fail at runtime
            logger.warning(
                "sentence-transformers scoring failed for mention %r: %s", mention, _e
            )

    # fallback heuristic
    scored = []
    mention_l = mention.lower()
    for c in candidates:
        score = 0.0
        lab = (c.get("label") or "").lower()
        desc = (c.get("description") or "").lower()
        if lab == mention_l:
            score += 1.0
        # token overlap with description
        common = sum(1 for w in mention_l.split() if w in desc)
        score += common * 0.1
        scored.append((c, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored, used_embedding


def link_mention(
    mention_text: str, context: str, top_k: int = 5, verbose: bool = False
) -> Dict[str, Any]:
    """对单个 mention 进行候选检索与排序，返回选中项与置信度等信息。"""
    try:
        candidates = search_wikidata(mention_text, limit=top_k)
    except Exception as e:
        logger.debug("Wikidata search failed for %s: %s", mention_text, e)
        candidates = []

    if not candidates:
        return {
            "mention": mention_text,
            "wikidata_qid": None,
            "candidates": [],
            "confidence": 0.0,
            "candidates_count": 0,
            "used_embedding": False,
            "search_success": False,
        }

    candidates_count = len(candidates)
    try:
        scored, used_embedding = _score_candidates_by_context(
            context or mention_text, mention_text, candidates
        )
    except Exception as _e:
        # Shouldn't reach here because helper already catches model errors,
        # but be defensive.
        logger.warning("Scoring failed for %r: %s", mention_text, _e)
        scored, used_embedding = [], False

    if not scored:
        return {
            "mention": mention_text,
            "wikidata_qid": None,
            "wikidata_label": None,
            "wikidata_description": None,
            "candidates": candidates,
            "confidence": 0.0,
            "candidates_count": candidates_count,
            "used_embedding": used_embedding,
            "search_success": candidates_count > 0,
        }

    best, best_score = scored[0]

    return {
        "mention": mention_text,
        "wikidata_qid": best.get("id"),
        "wikidata_label": best.get("label"),
        "wikidata_description": best.get("description"),
        "candidates": candidates,
        "confidence": float(best_score),
        "candidates_count": candidates_count,
        "used_embedding": used_embedding,
        "search_success": candidates_count > 0,
    }


def link_mentions(
    mentions: List[Dict[str, Any]],
    context: str,
    top_k: int = 5,
    verbose: bool = False,
    on_link=None,
) -> List[Dict[str, Any]]:
    """对多个 mention 批量进行消歧并返回增强后的实体描述。

    如果提供 `on_link` 回调函数，则在每处理完一个 mention 后立即调用
    `on_link(out)`，用于流式输出或监控。"""
    results = []
    for m in mentions:
        text = m.get("mention") if isinstance(m, dict) else str(m)
        linked = link_mention(text, context, top_k=top_k, verbose=verbose)
        out = dict(m) if isinstance(m, dict) else {"mention": text}
        out.update(
            {
                "wikidata_qid": linked.get("wikidata_qid"),
                "wikidata_label": linked.get("wikidata_label"),
                "wikidata_description": linked.get("wikidata_description"),
                "link_confidence": linked.get("confidence"),
                "link_candidates": linked.get("candidates"),
                "link_candidates_count": linked.get("candidates_count"),
                "used_embedding": linked.get("used_embedding"),
                "search_success": linked.get("search_success"),
            }
        )
        if on_link:
            try:
                on_link(out)
            except Exception:
                logger.exception("on_link callback raised an exception")
        results.append(out)
    return results


if __name__ == "__main__":
    demo = "Alan Turing"
    print(search_wikidata(demo, limit=3))
    print(
        link_mention(
            demo,
            "Alan Turing (1912–1954) was an English mathematician and computer scientist.",
        )
    )
