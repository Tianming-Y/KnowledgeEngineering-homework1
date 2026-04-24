"""NER 与实体链接的轻量流水线封装。

本文件把 ``spacy_ner.py`` 的实体识别能力和 ``entity_linker.py`` 的 Wikidata 消歧能力
组合为两个更接近业务使用的接口：``process_text`` 处理单条文本，``process_texts``
批量处理多条文本并可直接落盘。

使用方式：
- 开发调试时可直接调用 ``process_text`` 或 ``process_texts``。
- 当需要对少量字符串快速试运行 NER + 链接时，本文件比 ``batch_process.py`` 更合适。

输入：
- 文本字符串或文本列表。
- 可选的 spaCy 模型名、是否启用链接、候选数 ``top_k`` 和日志开关。

输出：
- 返回形如 ``{"text": ..., "entities": [...]}`` 的结构化结果。
- 若提供 ``output_dir``，会写出多个 ``doc_*.json`` 文件。

与其他文件的关系：
- 复用 ``spacy_ner.py`` 和 ``entity_linker.py``。
- 与 ``batch_process.py`` 相比，本文件偏向函数接口和小规模调用，后者负责目录级批处理。
"""

import os
import json
from typing import List, Dict, Any, Optional

from .spacy_ner import load_model, predict
from .entity_linker import link_mentions


def process_text(
    text: str,
    nlp=None,
    link: bool = True,
    top_k: int = 5,
    link_verbose: bool = False,
    link_stream=None,
) -> Dict[str, Any]:
    """对单个文本执行 NER + 可选消歧，返回结构化结果。"""
    if nlp is None:
        nlp = load_model()
    ents = predict(text, nlp=nlp)
    # predict 返回单文档实体列表
    if link:
        linked = link_mentions(
            ents, text, top_k=top_k, verbose=link_verbose, on_link=link_stream
        )
    else:
        linked = ents

    return {"text": text, "entities": linked}


def process_texts(
    texts: List[str],
    output_dir: Optional[str] = None,
    model_name: str = "en_core_web_sm",
    link: bool = True,
    top_k: int = 5,
    link_verbose: bool = False,
) -> List[Dict[str, Any]]:
    """批量处理文本并将每个文档结果保存到 `output_dir`。"""
    if output_dir is None:
        output_dir = "output/entities"
    os.makedirs(output_dir, exist_ok=True)

    nlp = load_model(model_name)
    results: List[Dict[str, Any]] = []
    for i, text in enumerate(texts):
        res = process_text(
            text, nlp=nlp, link=link, top_k=top_k, link_verbose=link_verbose
        )
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
