"""
实体识别模块 (Named Entity Recognition Module)
使用 spaCy 对图灵相关文本进行命名实体识别，并在此基础上叠加
针对计算机科学领域的自定义规则匹配，扩展识别出领域专有名词。
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

# ---------- 领域专有实体词典 ----------
DOMAIN_ENTITIES: Dict[str, List[str]] = {
    "CONCEPT": [
        "Turing Machine",
        "Universal Turing Machine",
        "Halting Problem",
        "Computability",
        "Turing Test",
        "Artificial Intelligence",
        "Morphogenesis",
        "Lambda Calculus",
        "reaction-diffusion",
        "stored-program",
        "computability theory",
        "mathematical biology",
    ],
    "WORK": [
        "On Computable Numbers, with an Application to the Entscheidungsproblem",
        "On Computable Numbers",
        "Computing Machinery and Intelligence",
        "The Chemical Basis of Morphogenesis",
        "Automatic Computing Engine",
        "ACE",
    ],
    "DEVICE": [
        "Enigma",
        "Bombe",
        "Manchester Mark 1",
    ],
}

# 将词典展开为 (text, label) 列表，按长度降序，保证长短语优先匹配
_DOMAIN_PATTERNS: List[Tuple[str, str]] = sorted(
    [(text, label) for label, items in DOMAIN_ENTITIES.items() for text in items],
    key=lambda x: len(x[0]),
    reverse=True,
)


def _rule_based_ner(text: str) -> List[Dict]:
    """对文本应用领域词典规则，返回识别到的实体列表。"""
    found: List[Dict] = []
    lower = text.lower()
    for phrase, label in _DOMAIN_PATTERNS:
        start = 0
        phrase_lower = phrase.lower()
        while True:
            idx = lower.find(phrase_lower, start)
            if idx == -1:
                break
            found.append(
                {
                    "text": text[idx: idx + len(phrase)],
                    "label": label,
                    "start": idx,
                    "end": idx + len(phrase),
                    "source": "rule",
                }
            )
            start = idx + 1
    return found


def _spacy_ner(text: str) -> List[Dict]:
    """使用 spaCy 的英文模型提取命名实体。"""
    try:
        import spacy  # type: ignore

        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            import subprocess, sys  # noqa: E401

            subprocess.run(
                [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
                check=True,
                capture_output=True,
            )
            nlp = spacy.load("en_core_web_sm")

        doc = nlp(text)
        return [
            {
                "text": ent.text,
                "label": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char,
                "source": "spacy",
            }
            for ent in doc.ents
        ]
    except Exception as exc:
        print(f"  [NER] spaCy 不可用，仅使用规则匹配：{exc}")
        return []


def _merge_entities(
    spacy_ents: List[Dict], rule_ents: List[Dict]
) -> List[Dict]:
    """合并两路实体列表，去除重叠，规则实体优先保留。"""
    merged = list(rule_ents)
    rule_spans = {(e["start"], e["end"]) for e in rule_ents}

    for ent in spacy_ents:
        # 若 spaCy 实体与任何规则实体重叠则丢弃
        overlaps = any(
            not (ent["end"] <= rs or ent["start"] >= re_)
            for rs, re_ in rule_spans
        )
        if not overlaps:
            merged.append(ent)

    merged.sort(key=lambda x: x["start"])
    return merged


def recognize_entities(text: str) -> List[Dict]:
    """
    对输入文本执行实体识别，融合 spaCy 与领域规则两路结果。

    返回:
        实体列表，每个元素包含 text / label / start / end / source 字段。
    """
    spacy_ents = _spacy_ner(text)
    rule_ents = _rule_based_ner(text)
    return _merge_entities(spacy_ents, rule_ents)


def group_by_label(entities: List[Dict]) -> Dict[str, List[str]]:
    """按实体类型分组，去重。"""
    groups: Dict[str, List[str]] = {}
    seen = set()
    for ent in entities:
        key = (ent["label"], ent["text"].strip())
        if key not in seen:
            seen.add(key)
            groups.setdefault(ent["label"], []).append(ent["text"].strip())
    return groups


def print_ner_report(entities: List[Dict]) -> None:
    """格式化打印实体识别报告。"""
    groups = group_by_label(entities)

    label_zh = {
        "PERSON": "人物 (PERSON)",
        "ORG": "组织机构 (ORG)",
        "GPE": "地缘政治实体 (GPE)",
        "LOC": "地点 (LOC)",
        "DATE": "日期 (DATE)",
        "NORP": "国籍/宗教/政治 (NORP)",
        "CONCEPT": "核心概念 (CONCEPT)",
        "WORK": "著作/系统 (WORK)",
        "DEVICE": "装置/设备 (DEVICE)",
        "EVENT": "事件 (EVENT)",
        "LANGUAGE": "语言 (LANGUAGE)",
        "CARDINAL": "数字 (CARDINAL)",
        "ORDINAL": "序数 (ORDINAL)",
    }

    print("\n" + "=" * 60)
    print("  命名实体识别结果 (Named Entity Recognition Results)")
    print("=" * 60)
    for label, items in sorted(groups.items()):
        display = label_zh.get(label, label)
        print(f"\n【{display}】")
        for item in items:
            print(f"    • {item}")
    print("=" * 60)


# ---------- 主程序入口 ----------
if __name__ == "__main__":
    data_path = Path(__file__).parent / "data" / "turing_text.txt"
    text = data_path.read_text(encoding="utf-8")

    print("正在对图灵文本进行实体识别……")
    entities = recognize_entities(text)
    print_ner_report(entities)
    print(f"\n共识别出 {len(entities)} 个实体（含重复位置）。")
