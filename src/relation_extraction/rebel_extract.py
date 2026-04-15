"""
rebel_extract.py
使用 REBEL (Babelscape/rebel-large) 对候选对所在句子进行三元组抽取，
将 REBEL 输出与候选对对齐，产生正式的三元组。
"""

import json
import os
import re
import time
import logging
import argparse
from collections import defaultdict

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from tqdm import tqdm

# ── 日志 ──────────────────────────────────────────────
logger = logging.getLogger("rebel_extract")


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


# ── REBEL 输出解析 ────────────────────────────────────
def parse_rebel_output(text: str) -> list[dict]:
    """
    解析 REBEL 生成的文本为三元组列表。
    REBEL 输出格式: <triplet> subject <subj> object <obj> predicate ...
    注意: <subj> 后面是 object, <obj> 后面是 predicate/relation
    """
    triples = []
    # 拆分多个 triplet
    parts = text.split("<triplet>")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 提取 subject, object, predicate
        subj_match = re.match(r"(.+?)\s*<subj>\s*(.+?)\s*<obj>\s*(.+)", part)
        if subj_match:
            subject = subj_match.group(1).strip()
            obj = subj_match.group(2).strip()  # <subj> 后面是 object
            predicate = subj_match.group(3).strip()  # <obj> 后面是 predicate
            # 进一步清理尾部可能残留的特殊 token
            predicate = re.sub(r"\s*</?[a-z]+>.*", "", predicate).strip()
            if subject and predicate and obj:
                triples.append(
                    {
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                    }
                )
    return triples


# ── 实体对齐 ──────────────────────────────────────────
def normalize_for_match(text: str) -> str:
    """归一化文本用于模糊匹配"""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def entity_matches(rebel_entity: str, candidate_entity: str) -> bool:
    """检查 REBEL 输出的实体是否与候选实体匹配"""
    r_norm = normalize_for_match(rebel_entity)
    c_norm = normalize_for_match(candidate_entity)
    if not r_norm or not c_norm:
        return False
    # 精确匹配
    if r_norm == c_norm:
        return True
    # 子串匹配
    if r_norm in c_norm or c_norm in r_norm:
        return True
    return False


def align_rebel_triples_with_candidates(
    rebel_triples: list[dict],
    sentence_candidates: list[dict],
) -> list[dict]:
    """
    将 REBEL 产出的三元组与该句子下的候选对进行匹配。
    匹配成功时，用 NER/EL 的实体信息（mention、QID）替换 REBEL 的实体文本。
    """
    aligned = []
    for rt in rebel_triples:
        for cand in sentence_candidates:
            # 尝试正向匹配：REBEL subject -> candidate head, REBEL object -> candidate tail
            if entity_matches(rt["subject"], cand["head"]) and entity_matches(
                rt["object"], cand["tail"]
            ):
                aligned.append(
                    {
                        "head": cand["head"],
                        "head_qid": cand.get("head_qid", ""),
                        "tail": cand["tail"],
                        "tail_qid": cand.get("tail_qid", ""),
                        "relation": rt["predicate"],
                        "head_mention": rt["subject"],
                        "tail_mention": rt["object"],
                        "doc": cand["doc"],
                        "sentence": cand["sentence"],
                    }
                )
                break
            # 反向匹配：REBEL subject -> candidate tail, REBEL object -> candidate head
            if entity_matches(rt["subject"], cand["tail"]) and entity_matches(
                rt["object"], cand["head"]
            ):
                aligned.append(
                    {
                        "head": cand["tail"],
                        "head_qid": cand.get("tail_qid", ""),
                        "tail": cand["head"],
                        "tail_qid": cand.get("head_qid", ""),
                        "relation": rt["predicate"],
                        "head_mention": rt["subject"],
                        "tail_mention": rt["object"],
                        "doc": cand["doc"],
                        "sentence": cand["sentence"],
                    }
                )
                break
    return aligned


# ── 主流程 ────────────────────────────────────────────
def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def group_candidates_by_sentence(candidates: list[dict]) -> dict[str, list[dict]]:
    """按句子分组候选对"""
    groups = defaultdict(list)
    for c in candidates:
        groups[c["sentence"]].append(c)
    return groups


def run_rebel_inference(
    sentences: list[str],
    tokenizer,
    model,
    device: torch.device,
    batch_size: int = 4,
    use_fp16: bool = True,
) -> dict[str, list[dict]]:
    """
    对句子列表批量运行 REBEL 推理。
    返回 {sentence: [triple_dict, ...]}
    """
    results = {}
    total = len(sentences)
    logger.info(
        f"REBEL 推理: {total} 个唯一句子, batch_size={batch_size}, fp16={use_fp16}"
    )

    for start_idx in tqdm(range(0, total, batch_size), desc="REBEL 推理"):
        batch = sentences[start_idx : start_idx + batch_size]
        inputs = tokenizer(
            batch,
            max_length=512,
            padding=True,
            truncation=True,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            if use_fp16 and device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    outputs = model.generate(
                        **inputs,
                        max_length=256,
                        num_beams=3,
                        num_return_sequences=1,
                    )
            else:
                outputs = model.generate(
                    **inputs,
                    max_length=256,
                    num_beams=3,
                    num_return_sequences=1,
                )

        decoded = tokenizer.batch_decode(outputs, skip_special_tokens=False)
        for sent, dec_text in zip(batch, decoded):
            # 清理特殊 token
            dec_text = (
                dec_text.replace("<s>", "")
                .replace("</s>", "")
                .replace("<pad>", "")
                .strip()
            )
            triples = parse_rebel_output(dec_text)
            results[sent] = triples

    return results


def main():
    parser = argparse.ArgumentParser(description="REBEL 三元组抽取与候选对对齐")
    parser.add_argument("--candidates", default="data/relation/candidates.jsonl")
    parser.add_argument("--out", default="output/graphs/rebel_triples.jsonl")
    parser.add_argument("--model-name", default="Babelscape/rebel-large")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--log", default="output/logs/rebel_run.log")
    parser.add_argument(
        "--doc-ids", nargs="*", default=None, help="仅处理指定 doc_id 的候选"
    )
    args = parser.parse_args()

    setup_logging(args.log)
    logger.info("=" * 60)
    logger.info("REBEL 三元组抽取 开始")
    logger.info(f"  model: {args.model_name}")
    logger.info(f"  candidates: {args.candidates}")
    logger.info(f"  output: {args.out}")

    start_time = time.time()

    # ── 环境检查 ──
    use_gpu = torch.cuda.is_available()
    device = torch.device("cuda" if use_gpu else "cpu")
    if use_gpu:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        logger.info(f"  GPU: {gpu_name} ({gpu_mem:.1f} GB)")
    else:
        logger.info("  GPU 不可用, 使用 CPU")
    use_fp16 = use_gpu
    logger.info(f"  fp16: {use_fp16}")
    logger.info(f"  batch_size: {args.batch_size}")

    # ── 加载候选对 ──
    candidates = load_jsonl(args.candidates)
    if args.doc_ids:
        allowed = set(args.doc_ids)
        candidates = [c for c in candidates if c["doc"] in allowed]
    logger.info(f"  候选对总数(过滤后): {len(candidates)}")

    if not candidates:
        logger.warning("无候选对, 退出")
        return

    # ── 按句子分组 ──
    sent_groups = group_candidates_by_sentence(candidates)
    unique_sentences = list(sent_groups.keys())
    logger.info(f"  唯一句子数: {len(unique_sentences)}")

    # ── 加载模型 ──
    logger.info(f"加载 REBEL 模型: {args.model_name} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model_name)
    model.eval()
    model.to(device)
    logger.info("REBEL 模型加载完成")

    # ── 推理（带 OOM 自动降级）──
    batch_size = args.batch_size
    rebel_results = None
    for attempt in range(4):
        try:
            rebel_results = run_rebel_inference(
                unique_sentences,
                tokenizer,
                model,
                device,
                batch_size=batch_size,
                use_fp16=use_fp16,
            )
            break
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            old_bs = batch_size
            batch_size = max(1, batch_size // 2)
            logger.warning(
                f"OOM! batch_size {old_bs}->{batch_size} (第 {attempt+1} 次降级)"
            )
            if attempt == 3:
                logger.error("多次 OOM 后仍失败, 退出")
                raise

    inference_time = time.time() - start_time
    logger.info(f"推理耗时: {inference_time:.1f}s")

    # ── 对齐 ──
    all_triples = []
    for sent, rebel_triples in rebel_results.items():
        cands = sent_groups[sent]
        aligned = align_rebel_triples_with_candidates(rebel_triples, cands)
        for a in aligned:
            a["confidence"] = 1.0  # REBEL 未给出置信度, 默认 1.0
            a["provenance"] = "rebel"
        all_triples.extend(aligned)

    # ── 去重 ──
    seen = {}
    for t in all_triples:
        key = (t["head"], t["relation"], t["tail"])
        if key not in seen:
            seen[key] = t
    deduped = list(seen.values())

    # ── 保存 ──
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for t in deduped:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    total_time = time.time() - start_time
    logger.info(f"REBEL 抽取完成:")
    logger.info(
        f"  REBEL 原始三元组总数: {sum(len(v) for v in rebel_results.values())}"
    )
    logger.info(f"  对齐后三元组: {len(all_triples)}")
    logger.info(f"  去重后三元组: {len(deduped)}")
    logger.info(f"  总耗时: {total_time:.1f}s")
    logger.info(f"  输出: {args.out}")

    print(f"\n[REBEL] 原始三元组: {sum(len(v) for v in rebel_results.values())}")
    print(f"[REBEL] 对齐后: {len(all_triples)}, 去重后: {len(deduped)} -> {args.out}")


if __name__ == "__main__":
    main()
