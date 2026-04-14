"""
extract_infobox_triples.py
从 data/processed/*.json 的 infobox 字段中抽取高置信三元组。
"""

import json
import re
import os
import argparse
import yaml


def normalize_key(key: str) -> str:
    """将 infobox key 标准化：小写、替换空格/nbsp 为下划线"""
    key = key.replace("\u00a0", " ").strip().lower()
    key = re.sub(r"\s+", "_", key)
    return key


def split_value(value: str, relation: str = "") -> list[str]:
    """将 infobox value 按常见分隔符拆分为多个实体"""
    # 某些关系不应拆分（如 birth_place, cause_of_death, publication_date 应作为整体）
    no_split_relations = {
        "birth_place",
        "death_place",
        "cause_of_death",
        "publication_date",
        "genre",
        "language",
    }
    if relation in no_split_relations:
        cleaned = re.sub(r"\([^)]*\)", "", value).strip()
        # 清理日期前缀（如 "Alan Mathison Turing  23 June 1912 Maida Vale"）
        if relation == "birth_place":
            # 移除人名和日期，只保留地名
            cleaned = re.sub(r"^[A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+\s*", "", cleaned)
            cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", "", cleaned)
            cleaned = re.sub(r"\d{1,2} \w+ \d{4}", "", cleaned).strip(" ,")
        if relation == "death_place":
            cleaned = re.sub(r"\d{1,2} \w+ \d{4}", "", cleaned)
            cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", "", cleaned)
            cleaned = re.sub(r"aged \d+", "", cleaned).strip(" ,")
        return [cleaned] if cleaned and len(cleaned) > 1 else []

    # 按换行、分号拆分，也尝试按多个空格拆分（infobox 中常见的连续实体）
    parts = re.split(r"[;\n]", value)
    result = []
    for p in parts:
        p = re.sub(r"\([^)]*\)", "", p).strip()
        if not p:
            continue
        # 如果是长字符串且包含多个大写开头词（连续实体），进一步拆分
        # 例如 "Robin Gandy Beatrice Worsley" -> ["Robin Gandy", "Beatrice Worsley"]
        # 对于已知的多实体关系，用大写单词边界拆分
        multi_entity_rels = {
            "doctoral_student",
            "doctoral_advisor",
            "educated_at",
            "worked_at",
            "known_for",
            "field_of_work",
        }
        if relation in multi_entity_rels and len(p) > 20:
            # 按已知分隔模式：换行符在 JSON 中变成空格，这里用大写开头词拆分不太靠谱
            # 更好的方案：按2+空格拆分
            sub_parts = re.split(r"\s{2,}", p)
            if len(sub_parts) > 1:
                result.extend(s.strip() for s in sub_parts if s.strip())
            else:
                result.append(p)
        else:
            result.append(p)
    return result


def load_mapping(mapping_path: str) -> dict:
    with open(mapping_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_triples(doc_path: str, mapping: dict) -> list[dict]:
    """从单个文件的 infobox 抽取三元组"""
    with open(doc_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    title = doc.get("title", os.path.basename(doc_path).replace(".json", ""))
    infobox = doc.get("infobox", {})
    if not infobox:
        return []

    triples = []
    for raw_key, raw_value in infobox.items():
        norm_key = normalize_key(raw_key)
        relation = mapping.get(norm_key)
        if not relation:
            continue

        values = split_value(str(raw_value), relation)
        for val in values:
            if len(val) < 2 or len(val) > 200:
                continue
            triples.append(
                {
                    "head": title,
                    "head_qid": "",
                    "relation": relation,
                    "tail": val,
                    "tail_qid": "",
                    "confidence": 1.0,
                    "sentence": f"{raw_key}: {raw_value}",
                    "doc": os.path.basename(doc_path),
                    "provenance": "infobox",
                }
            )
    return triples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default="data/processed")
    parser.add_argument("--out", default="output/graphs/infobox_triples.jsonl")
    parser.add_argument("--mapping", default="config/relation_mapping.yaml")
    parser.add_argument(
        "--doc-list", nargs="*", default=None, help="Only process these doc filenames"
    )
    args = parser.parse_args()

    mapping = load_mapping(args.mapping)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    all_triples = []
    if args.doc_list:
        files = [os.path.join(args.docs, f) for f in args.doc_list]
    else:
        files = sorted(
            os.path.join(args.docs, f)
            for f in os.listdir(args.docs)
            if f.endswith(".json")
        )

    for fpath in files:
        if not os.path.exists(fpath):
            continue
        triples = extract_triples(fpath, mapping)
        all_triples.extend(triples)

    with open(args.out, "w", encoding="utf-8") as f:
        for t in all_triples:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    print(f"[Infobox] 共抽取 {len(all_triples)} 条三元组 -> {args.out}")


if __name__ == "__main__":
    main()
