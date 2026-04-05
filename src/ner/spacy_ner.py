"""
spaCy NER helpers

提供加载模型与批量预测的简易接口。
"""

from typing import List, Dict, Union, Optional
import spacy


def load_model(model_name: str = "en_core_web_sm", disable: Optional[List[str]] = None):
    """加载并返回 spaCy `nlp` 对象。

    参数:
        model_name: spaCy 模型名（默认 en_core_web_sm）。
        disable: 要禁用的 pipeline 组件列表。
    """
    if disable is None:
        disable = []
    return spacy.load(model_name, disable=disable)


def predict(
    texts: Union[str, List[str]], nlp=None, batch_size: int = 32
) -> Union[List[List[Dict]], List[Dict]]:
    """对单个文本或文本列表执行 NER，返回实体列表。

    返回每个文档的实体列表，实体字段包含: `mention`, `type`, `start`, `end`, `source`。
    如果输入为单字符串，则返回单个文档的实体列表。
    """
    single = False
    if isinstance(texts, str):
        texts = [texts]
        single = True
    if nlp is None:
        nlp = load_model()

    results: List[List[Dict]] = []
    for doc in nlp.pipe(texts, batch_size=batch_size):
        doc_ents: List[Dict] = []
        for ent in doc.ents:
            doc_ents.append(
                {
                    "mention": ent.text,
                    "type": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "source": "spacy",
                }
            )
        results.append(doc_ents)

    return results[0] if single else results


if __name__ == "__main__":
    nlp = load_model()
    demo = "Alan Turing was born in London. He worked on the Enigma machine."
    print(predict(demo, nlp=nlp))
