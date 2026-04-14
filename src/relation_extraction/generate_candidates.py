"""
generate_candidates.py
对每个文档的每个句子，生成实体对候选（head, tail），排除自身配对和双DATE配对。
"""

import json
import os
import argparse
from itertools import combinations


def load_entities(entities_path: str) -> dict:
    """加载 entities_all.jsonl，返回 {doc_name: [entity_list]}"""
    doc_entities = {}
    with open(entities_path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            doc_entities[row["doc"]] = row["entities"]
    return doc_entities


def load_doc_sentences(doc_path: str) -> list[dict]:
    """加载文档所有句子，返回 [{section, sent_idx, text, start, end}]"""
    with open(doc_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    sentences = []
    # 先收集 summary_sentences，再收集 sections 中的 sentences
    full_text = doc.get("summary", "")
    for sec in doc.get("sections", []):
        full_text += "\n" + sec.get("text", "")

    # 构建句子列表，使用 sections 中的 sentences，同时跟踪全局 offset
    offset = 0
    if doc.get("summary_sentences"):
        for i, sent in enumerate(doc["summary_sentences"]):
            start = full_text.find(sent, offset)
            if start == -1:
                start = offset
            end = start + len(sent)
            sentences.append(
                {
                    "section": "Summary",
                    "sent_idx": i,
                    "text": sent,
                    "start": start,
                    "end": end,
                }
            )
            offset = max(offset, end)

    for sec in doc.get("sections", []):
        for i, sent in enumerate(sec.get("sentences", [])):
            start = full_text.find(sent, offset)
            if start == -1:
                start = offset
            end = start + len(sent)
            sentences.append(
                {
                    "section": sec.get("heading", ""),
                    "sent_idx": i,
                    "text": sent,
                    "start": start,
                    "end": end,
                }
            )
            offset = max(offset, end)

    return sentences


def find_entities_in_sentence(entities: list, sent_start: int, sent_end: int) -> list:
    """找到落在句子范围内的实体"""
    result = []
    for ent in entities:
        if ent["start"] >= sent_start and ent["end"] <= sent_end:
            result.append(ent)
    return result


def generate_candidates_for_doc(
    doc_name: str,
    entities: list,
    doc_path: str,
    max_pairs_per_sent: int = 10,
) -> list[dict]:
    """为单个文档生成所有候选对"""
    sentences = load_doc_sentences(doc_path)
    candidates = []

    for sent_info in sentences:
        sent_ents = find_entities_in_sentence(
            entities, sent_info["start"], sent_info["end"]
        )
        # 去重（同一mention同一位置只保留一次）
        seen = set()
        unique_ents = []
        for e in sent_ents:
            key = (e["mention"], e["start"], e["end"])
            if key not in seen:
                seen.add(key)
                unique_ents.append(e)

        # 过滤掉 CARDINAL, ORDINAL 等低价值类型
        filtered = [
            e
            for e in unique_ents
            if e.get("type")
            not in ("CARDINAL", "ORDINAL", "QUANTITY", "MONEY", "PERCENT")
        ]

        # 生成所有有序对
        pairs = list(combinations(filtered, 2))
        count = 0
        for head, tail in pairs:
            # 排除 head==tail
            if head["mention"] == tail["mention"]:
                continue
            # 排除双 DATE
            if head.get("type") == "DATE" and tail.get("type") == "DATE":
                continue
            candidates.append(
                {
                    "doc": doc_name,
                    "sentence": sent_info["text"],
                    "section": sent_info["section"],
                    "head": head["mention"],
                    "head_type": head.get("type", ""),
                    "head_start": head["start"],
                    "head_end": head["end"],
                    "head_qid": head.get("wikidata_qid", ""),
                    "tail": tail["mention"],
                    "tail_type": tail.get("type", ""),
                    "tail_start": tail["start"],
                    "tail_end": tail["end"],
                    "tail_qid": tail.get("wikidata_qid", ""),
                }
            )
            count += 1
            if count >= max_pairs_per_sent:
                break

    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", default="output/entities_all.jsonl")
    parser.add_argument("--docs", default="data/processed")
    parser.add_argument("--out", default="data/relation/candidates.jsonl")
    parser.add_argument("--max-pairs", type=int, default=10)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    doc_entities = load_entities(args.entities)

    all_candidates = []
    for doc_name, entities in doc_entities.items():
        doc_path = os.path.join(args.docs, doc_name)
        if not os.path.exists(doc_path):
            print(f"[WARN] 文档未找到: {doc_path}")
            continue
        cands = generate_candidates_for_doc(
            doc_name, entities, doc_path, args.max_pairs
        )
        all_candidates.extend(cands)

    with open(args.out, "w", encoding="utf-8") as f:
        for c in all_candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"[Candidates] 共生成 {len(all_candidates)} 个候选对 -> {args.out}")


if __name__ == "__main__":
    main()
