"""
NER 流水线：组织 spaCy NER 与 Wikidata 消歧并将结果写入文件。

提供简单的 `process_text` 与 `process_texts` 接口，便于在数据采集流程中集成。
"""

import os
import json
from typing import List, Dict, Any, Optional

from .spacy_ner import load_model, predict
from .entity_linker import link_mentions


def process_text(
    text: str, nlp=None, link: bool = True, top_k: int = 5
) -> Dict[str, Any]:
    """对单个文本执行 NER + 可选消歧，返回结构化结果。"""
    if nlp is None:
        nlp = load_model()
    ents = predict(text, nlp=nlp)
    # predict 返回单文档实体列表
    if link:
        linked = link_mentions(ents, text, top_k=top_k)
    else:
        linked = ents

    return {"text": text, "entities": linked}


def process_texts(
    texts: List[str],
    output_dir: Optional[str] = None,
    model_name: str = "en_core_web_sm",
    link: bool = True,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """批量处理文本并将每个文档结果保存到 `output_dir`。"""
    if output_dir is None:
        output_dir = "output/entities"
    os.makedirs(output_dir, exist_ok=True)

    nlp = load_model(model_name)
    results: List[Dict[str, Any]] = []
    for i, text in enumerate(texts):
        res = process_text(text, nlp=nlp, link=link, top_k=top_k)
        results.append(res)
        path = os.path.join(output_dir, f"doc_{i}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)

    return results


if __name__ == "__main__":
    demo_texts = [
        "Alan Turing was a mathematician and computer scientist born in London.",
        "The Enigma machine was used during World War II.",
    ]
    res = process_texts(demo_texts, output_dir="output/entities_demo")
    print("Wrote", len(res), "documents to output/entities_demo")
