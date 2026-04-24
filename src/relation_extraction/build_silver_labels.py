"""基于远程监督的银标构建脚本。

本文件利用 Infobox 三元组作为弱监督信号，把 ``generate_candidates.py`` 生成的候选实体对
标注为具体关系或 ``none``，从而得到一份可分析、可训练、也可直接参与合并的银标数据。

使用方式：
- 直接执行 ``python src/relation_extraction/build_silver_labels.py``。

输入：
- ``data/relation/candidates.jsonl`` 中的候选对。
- ``output/graphs/infobox_triples.jsonl`` 中的高精度三元组。

输出：
- ``data/relation/silver.jsonl``，在原候选对基础上增加 ``relation`` 字段。

与其他文件的关系：
- 上游依赖 ``extract_infobox_triples.py`` 和 ``generate_candidates.py``。
- 下游 ``merge_triples.py`` 会把其中的正例转换成银标三元组参与最终合并。
"""

import json
import os
import re
import argparse
import yaml


def normalize(text: str) -> str:
    """标准化文本用于模糊匹配"""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_infobox_index(infobox_triples: list[dict]) -> dict:
    """
    构建 {normalized_head -> [(relation, normalized_tail, raw_tail)]}
    同时构建别名映射（如 "turing" -> "alan turing"）
    """
    index = {}
    aliases = {}  # short_name -> full_name
    for t in infobox_triples:
        key = normalize(t["head"])
        val = (t["relation"], normalize(t["tail"]), t["tail"])
        index.setdefault(key, []).append(val)

        # 为各个 head 建立别名
        parts = key.split()
        if len(parts) > 1:
            # 姓氏别名
            aliases[parts[-1]] = key
            # 全名也是自己的别名
            aliases[key] = key

    return index, aliases


def fuzzy_contains(needle: str, haystack: str, min_len: int = 3) -> bool:
    """模糊包含检查：needle 是否出现在 haystack 中，或 haystack 的某个子串包含 needle"""
    if len(needle) < min_len:
        return False
    return needle in haystack or haystack in needle


def match_candidate(candidate: dict, infobox_index: dict, aliases: dict) -> str:
    """
    如果候选 head 匹配 infobox 的主语，且候选 tail 匹配 infobox 的宾语，
    返回对应关系名；否则返回 'none'。
    """
    head_norm = normalize(candidate["head"])
    tail_norm = normalize(candidate["tail"])

    # 通过别名查找 head 在 infobox 中的完整键
    possible_keys = set()
    if head_norm in infobox_index:
        possible_keys.add(head_norm)
    if head_norm in aliases:
        possible_keys.add(aliases[head_norm])
    # 也检查 head 是否是某个 infobox head 的子串
    for ib_key in infobox_index:
        if head_norm in ib_key or ib_key in head_norm:
            possible_keys.add(ib_key)

    # 正向匹配
    for key in possible_keys:
        if key in infobox_index:
            for relation, ib_tail_norm, _ in infobox_index[key]:
                if fuzzy_contains(tail_norm, ib_tail_norm):
                    return relation

    # 反向匹配：tail 做主语
    possible_tail_keys = set()
    if tail_norm in infobox_index:
        possible_tail_keys.add(tail_norm)
    if tail_norm in aliases:
        possible_tail_keys.add(aliases[tail_norm])
    for ib_key in infobox_index:
        if tail_norm in ib_key or ib_key in tail_norm:
            possible_tail_keys.add(ib_key)

    for key in possible_tail_keys:
        if key in infobox_index:
            for relation, ib_tail_norm, _ in infobox_index[key]:
                if fuzzy_contains(head_norm, ib_tail_norm):
                    return relation

    return "none"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", default="data/relation/candidates.jsonl")
    parser.add_argument("--infobox", default="output/graphs/infobox_triples.jsonl")
    parser.add_argument("--out", default="data/relation/silver.jsonl")
    parser.add_argument("--mapping", default="config/relation_mapping.yaml")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    candidates = load_jsonl(args.candidates)
    infobox_triples = load_jsonl(args.infobox)
    infobox_index, aliases = build_infobox_index(infobox_triples)

    labeled = []
    pos_count = 0
    for cand in candidates:
        relation = match_candidate(cand, infobox_index, aliases)
        cand["relation"] = relation
        labeled.append(cand)
        if relation != "none":
            pos_count += 1

    with open(args.out, "w", encoding="utf-8") as f:
        for item in labeled:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(
        f"[Silver] 正例: {pos_count}, 负例: {len(labeled) - pos_count}, "
        f"总计: {len(labeled)} -> {args.out}"
    )


if __name__ == "__main__":
    main()
