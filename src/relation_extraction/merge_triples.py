"""三元组归一化与多源融合脚本。

本文件负责关系抽取阶段的收口工作：先把 REBEL 产生的自由谓词归一化到项目的标准关系集，
再按 ``Infobox > Silver > REBEL`` 的优先级合并三类三元组，并输出统一格式的最终结果。

使用方式：
- 直接执行 ``python src/relation_extraction/merge_triples.py``。
- 可通过 ``--st-model`` 指定谓词 embedding 映射模型，通过 ``--qc-out`` 输出抽样质检文件。

输入：
- ``output/graphs/rebel_triples.jsonl``。
- ``output/graphs/infobox_triples.jsonl``。
- ``data/relation/silver.jsonl``。
- ``config/relation_mapping.yaml``。

输出：
- ``output/graphs/relation_triples.jsonl``。
- ``output/logs`` 下的模糊谓词文件、抽样质检文件和合并日志。

与其他文件的关系：
- 上游依赖关系抽取子包的前四个步骤。
- 下游 ``apply_aliases.py`` 和 ``build_graph.py`` 会直接消费它的输出。
"""

import json
import os
import re
import logging
import argparse
import time
from collections import Counter

import yaml
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

logger = logging.getLogger("merge_triples")


def setup_logging(log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(ch)


def load_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def save_jsonl(rows: list[dict], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def normalize_for_dedup(text: str) -> str:
    """归一化实体文本用于去重"""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def apply_hardcoded_aliases_for_dedup(text: str) -> str:
    """
    最小范围别名规则：把常见的 'Turing' 形式规范为 'Alan Turing'，仅用于去重键。
    该函数只做最小侵入的硬编码修正，不改变原始三元组字段。
    """
    if not text:
        return text
    norm = re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()
    aliases = {
        "turing": "Alan Turing",
        "alan turing": "Alan Turing",
        "alan mathison turing": "Alan Turing",
    }
    return aliases.get(norm, text)


# ── 谓词映射 ─────────────────────────────────────────
def load_relation_mapping(mapping_path: str) -> dict:
    with open(mapping_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_literal_map(mapping: dict) -> dict[str, str]:
    """
    构建字面映射：
    - 原始 yaml key -> canonical relation
    - canonical relation (下划线替换为空格) -> canonical relation
    """
    literal = {}
    for raw_key, relation in mapping.items():
        literal[raw_key.lower()] = relation
        literal[relation.lower()] = relation
        # 下划线替换为空格
        literal[relation.lower().replace("_", " ")] = relation
    return literal


def map_predicates_with_embeddings(
    predicates: list[str],
    target_labels: list[str],
    st_model: SentenceTransformer,
    threshold_accept: float = 0.65,
    threshold_ambiguous: float = 0.55,
) -> tuple[dict[str, str], list[dict]]:
    """
    使用 embedding 相似度将 REBEL 谓词映射到目标关系标签。
    返回: (mapped_dict, ambiguous_list)
    """
    if not predicates or not target_labels:
        return {}, []

    pred_embs = st_model.encode(predicates, show_progress_bar=False)
    target_embs = st_model.encode(target_labels, show_progress_bar=False)

    # 归一化
    pred_embs = pred_embs / np.linalg.norm(pred_embs, axis=1, keepdims=True)
    target_embs = target_embs / np.linalg.norm(target_embs, axis=1, keepdims=True)

    sims = pred_embs @ target_embs.T  # (n_preds, n_targets)

    mapped = {}
    ambiguous = []
    for i, pred in enumerate(predicates):
        best_idx = int(np.argmax(sims[i]))
        best_sim = float(sims[i, best_idx])
        best_label = target_labels[best_idx]

        if best_sim >= threshold_accept:
            mapped[pred] = best_label
        elif best_sim >= threshold_ambiguous:
            ambiguous.append(
                {
                    "predicate": pred,
                    "best_match": best_label,
                    "similarity": round(best_sim, 4),
                }
            )
            # 不映射，保留原谓词
        # else: 不映射，保留原谓词

    return mapped, ambiguous


def map_rebel_predicates(
    rebel_triples: list[dict],
    mapping_path: str,
    st_model: SentenceTransformer,
    log_dir: str = "output/logs",
) -> list[dict]:
    """
    对 REBEL 三元组的 relation 进行映射。
    1. 字面映射
    2. Embedding 相似度映射（>=0.65）
    3. 不能映射的保留原文本
    """
    mapping = load_relation_mapping(mapping_path)
    literal_map = build_literal_map(mapping)

    # 目标关系标签集合
    target_labels = sorted(set(mapping.values()))
    # 加上带空格的可读版
    target_labels_readable = [l.replace("_", " ") for l in target_labels]

    # 收集需要 embedding 映射的谓词
    unmapped_predicates = set()
    for t in rebel_triples:
        rel_lower = t["relation"].lower().strip()
        if rel_lower not in literal_map:
            unmapped_predicates.add(t["relation"])

    # Embedding 映射
    embed_mapped = {}
    ambiguous_all = []
    if unmapped_predicates:
        unmapped_list = sorted(unmapped_predicates)
        logger.info(f"  字面未映射谓词: {len(unmapped_list)}, 尝试 embedding 映射...")
        embed_mapped, ambiguous_all = map_predicates_with_embeddings(
            unmapped_list,
            target_labels_readable,
            st_model,
        )
        # 将 readable 映射回下划线形式
        for k, v in embed_mapped.items():
            embed_mapped[k] = v.replace(" ", "_")
        for a in ambiguous_all:
            a["best_match"] = a["best_match"].replace(" ", "_")

    # 导出模糊谓词
    if ambiguous_all:
        amb_path = os.path.join(log_dir, "rebel_ambiguous_predicates.jsonl")
        save_jsonl(ambiguous_all, amb_path)
        logger.info(f"  模糊谓词({len(ambiguous_all)}条) -> {amb_path}")

    # 应用映射
    literal_count = 0
    embed_count = 0
    unmapped_count = 0
    for t in rebel_triples:
        rel_lower = t["relation"].lower().strip()
        if rel_lower in literal_map:
            t["mapped_relation"] = literal_map[rel_lower]
            literal_count += 1
        elif t["relation"] in embed_mapped:
            t["mapped_relation"] = embed_mapped[t["relation"]]
            embed_count += 1
        else:
            t["mapped_relation"] = t["relation"]
            unmapped_count += 1

    logger.info(
        f"  谓词映射结果: 字面={literal_count}, embedding={embed_count}, 未映射={unmapped_count}"
    )
    return rebel_triples


# ── Silver 三元组转换 ─────────────────────────────────
def convert_silver_to_triples(silver: list[dict]) -> list[dict]:
    """将 silver.jsonl 中 relation != 'none' 的条目转为三元组格式"""
    triples = []
    for s in silver:
        if s.get("relation", "none") == "none":
            continue
        triples.append(
            {
                "head": s["head"],
                "head_qid": s.get("head_qid", ""),
                "relation": s["relation"],
                "tail": s["tail"],
                "tail_qid": s.get("tail_qid", ""),
                "confidence": s.get("confidence", 0.8),
                "sentence": s.get("sentence", ""),
                "doc": s.get("doc", ""),
                "provenance": "silver",
            }
        )
    return triples


# ── 合并 ─────────────────────────────────────────────
PROVENANCE_PRIORITY = {"infobox": 3, "silver": 2, "rebel": 1}


def merge_triples(
    infobox: list[dict],
    silver: list[dict],
    rebel: list[dict],
) -> list[dict]:
    """
    合并三来源三元组（优先级：Infobox > Silver > REBEL）。
    按 (head_normalized, mapped_relation, tail_normalized) 去重，
    保留置信度最高的一条，合并 provenance 列表。
    """
    all_triples = []
    for t in infobox:
        t.setdefault("provenance", "infobox")
        t.setdefault("confidence", 1.0)
        all_triples.append(t)
    for t in silver:
        t.setdefault("provenance", "silver")
        all_triples.append(t)
    for t in rebel:
        t.setdefault("provenance", "rebel")
        # 使用 mapped_relation 作为最终关系
        if "mapped_relation" in t:
            t["relation"] = t["mapped_relation"]
        all_triples.append(t)

    # 去重
    merged = {}
    for t in all_triples:
        # 对去重键先应用最小化的硬编码别名修正（只针对 Turing -> Alan Turing），
        # 再做常规归一化以生成稳定的去重 key。
        head_for_key = normalize_for_dedup(
            apply_hardcoded_aliases_for_dedup(t.get("head", ""))
        )
        tail_for_key = normalize_for_dedup(
            apply_hardcoded_aliases_for_dedup(t.get("tail", ""))
        )
        key = (
            head_for_key,
            t["relation"].lower().strip(),
            tail_for_key,
        )
        prov = t.get("provenance", "unknown")
        conf = t.get("confidence", 0)
        pri = PROVENANCE_PRIORITY.get(prov, 0)

        if key not in merged:
            merged[key] = {
                **t,
                "provenance_list": [prov],
                "doc_ids": [t.get("doc", "")],
            }
        else:
            existing = merged[key]
            # 合并 provenance
            if prov not in existing["provenance_list"]:
                existing["provenance_list"].append(prov)
            # 合并 doc_ids
            doc = t.get("doc", "")
            if doc and doc not in existing["doc_ids"]:
                existing["doc_ids"].append(doc)
            # 保留优先级更高或置信度更高的
            ex_pri = PROVENANCE_PRIORITY.get(existing.get("provenance", ""), 0)
            ex_conf = existing.get("confidence", 0)
            if pri > ex_pri or (pri == ex_pri and conf > ex_conf):
                prov_list = existing["provenance_list"]
                doc_ids = existing["doc_ids"]
                merged[key] = {**t, "provenance_list": prov_list, "doc_ids": doc_ids}

    # 整理输出格式
    result = []
    for t in merged.values():
        out = {
            "head": t["head"],
            "head_qid": t.get("head_qid", ""),
            "relation": t["relation"],
            "tail": t["tail"],
            "tail_qid": t.get("tail_qid", ""),
            "confidence": t.get("confidence", 0),
            "provenance": ",".join(t["provenance_list"]),
            "doc_ids": t["doc_ids"],
            "sentence": t.get("sentence", ""),
        }
        result.append(out)

    return result


# ── QC 抽样 ──────────────────────────────────────────
def sample_qc(
    rebel_triples: list[dict],
    n: int = 50,
    out_path: str = "output/logs/rebel_sample_qc.jsonl",
):
    """抽样检查 REBEL 输出的对齐质量"""
    import random

    random.seed(42)
    sample = random.sample(rebel_triples, min(n, len(rebel_triples)))
    qc_rows = []
    for t in sample:
        qc_rows.append(
            {
                "head": t.get("head", ""),
                "tail": t.get("tail", ""),
                "relation": t.get("relation", ""),
                "mapped_relation": t.get("mapped_relation", ""),
                "head_mention": t.get("head_mention", ""),
                "tail_mention": t.get("tail_mention", ""),
                "sentence": t.get("sentence", ""),
                "doc": t.get("doc", ""),
            }
        )
    save_jsonl(qc_rows, out_path)
    logger.info(f"QC 抽样 {len(qc_rows)} 条 -> {out_path}")


# ── 主函数 ────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="谓词归一化与三元组合并")
    parser.add_argument("--rebel", default="output/graphs/rebel_triples.jsonl")
    parser.add_argument("--infobox", default="output/graphs/infobox_triples.jsonl")
    parser.add_argument("--silver", default="data/relation/silver.jsonl")
    parser.add_argument("--mapping", default="config/relation_mapping.yaml")
    parser.add_argument("--out", default="output/graphs/relation_triples.jsonl")
    parser.add_argument("--st-model", default="all-MiniLM-L6-v2")
    parser.add_argument("--log", default="output/logs/rebel_run.log")
    parser.add_argument("--qc-out", default="output/logs/rebel_sample_qc.jsonl")
    args = parser.parse_args()

    setup_logging(args.log)
    logger.info("=" * 60)
    logger.info("谓词归一化 & 三元组合并")
    start_time = time.time()

    # ── 加载 REBEL 三元组 ──
    logger.info(f"加载 REBEL 三元组: {args.rebel}")
    rebel_triples = load_jsonl(args.rebel)
    logger.info(f"  REBEL 三元组数: {len(rebel_triples)}")

    # ── 谓词映射 ──
    logger.info("谓词映射...")
    st_model = SentenceTransformer(args.st_model)
    rebel_triples = map_rebel_predicates(
        rebel_triples,
        args.mapping,
        st_model,
        log_dir=os.path.dirname(args.log),
    )

    # ── QC 抽样 ──
    if rebel_triples:
        sample_qc(rebel_triples, n=50, out_path=args.qc_out)

    # ── 加载 Infobox 与 Silver ──
    logger.info(f"加载 Infobox 三元组: {args.infobox}")
    infobox_triples = load_jsonl(args.infobox)
    logger.info(f"  Infobox 三元组数: {len(infobox_triples)}")

    logger.info(f"加载 Silver 标注: {args.silver}")
    silver_raw = load_jsonl(args.silver)
    silver_triples = convert_silver_to_triples(silver_raw)
    logger.info(f"  Silver 正例三元组数: {len(silver_triples)}")

    # ── 合并 ──
    logger.info("合并三元组（Infobox > Silver > REBEL）...")
    merged = merge_triples(infobox_triples, silver_triples, rebel_triples)

    # ── 保存 ──
    save_jsonl(merged, args.out)
    total_time = time.time() - start_time
    logger.info(f"合并完成: {len(merged)} 条 -> {args.out}")
    logger.info(f"耗时: {total_time:.1f}s")

    # ── 统计报告 ──
    prov_counter = Counter()
    rel_counter = Counter()
    for t in merged:
        for p in t["provenance"].split(","):
            prov_counter[p.strip()] += 1
        rel_counter[t["relation"]] += 1

    logger.info("三元组 provenance 分布:")
    for p, c in prov_counter.most_common():
        logger.info(f"  {p}: {c}")

    logger.info("Top-10 关系类型:")
    for r, c in rel_counter.most_common(10):
        logger.info(f"  {r}: {c}")

    print(f"\n[Merge] 合并后三元组: {len(merged)} -> {args.out}")
    print(f"  Provenance 分布: {dict(prov_counter)}")
    print(f"  Top-10 关系: {dict(rel_counter.most_common(10))}")


if __name__ == "__main__":
    main()
