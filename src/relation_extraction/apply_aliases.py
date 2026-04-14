"""
src/relation_extraction/apply_aliases.py
把合并后三元组里的指定别名（当前仅 Turing 及其变体）标准化为 `Alan Turing`，供后续构建图谱使用。

设计：
- 提供 `apply_aliases_file(in_path, out_path, backup=False)` 以便在其他脚本中调用。
- 提供 CLI 接口以便在流水线中执行。
"""

import argparse
import json
import os
import re
from typing import Optional


def apply_aliases_text(text: Optional[str]) -> str:
    if not text:
        return text or ""
    norm = re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()
    aliases = {
        "turing": "Alan Turing",
        "alan turing": "Alan Turing",
        "alan mathison turing": "Alan Turing",
    }
    return aliases.get(norm, text)


def apply_aliases_file(
    in_path: str, out_path: str, backup: bool = False
) -> tuple[int, int]:
    """读取 JSONL 三元组文件，替换 head/tail 中的别名并写入新文件。

    返回 (total_lines, replacements) 统计。
    """
    if not os.path.exists(in_path):
        raise FileNotFoundError(in_path)

    if backup:
        bak = in_path + ".bak"
        if not os.path.exists(bak):
            os.rename(in_path, bak)
            in_path = bak
        else:
            # 如果备份已存在，仍从原文件读取
            pass

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    total = 0
    replaced = 0
    with open(in_path, "r", encoding="utf-8") as fin, open(
        out_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            if not line.strip():
                continue
            total += 1
            obj = json.loads(line)
            old_head = obj.get("head", "")
            old_tail = obj.get("tail", "")
            new_head = apply_aliases_text(old_head)
            new_tail = apply_aliases_text(old_tail)
            if new_head != old_head:
                replaced += 1
            if new_tail != old_tail:
                replaced += 1
            obj["head"] = new_head
            obj["tail"] = new_tail
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return total, replaced


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in", dest="in_path", default="output/graphs/relation_triples.jsonl"
    )
    parser.add_argument(
        "--out", dest="out_path", default="output/graphs/relation_triples_aliased.jsonl"
    )
    parser.add_argument(
        "--backup", action="store_true", help="将原文件重命名为 .bak 再读取"
    )
    args = parser.parse_args()

    total, replaced = apply_aliases_file(args.in_path, args.out_path, args.backup)
    print(
        f"[apply_aliases] 处理完成: 共 {total} 行, 替换 {replaced} 处 -> {args.out_path}"
    )


if __name__ == "__main__":
    main()
