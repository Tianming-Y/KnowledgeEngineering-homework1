"""spaCy 命名实体识别封装。

本文件提供 NER 阶段最轻量的公共能力：加载 spaCy 模型，并把单条或多条文本
转换为统一的实体列表格式。它只负责“识别实体”，不处理实体消歧、文件读写
或项目级批处理。

使用方式：
- 其他模块通过 ``load_model`` 获取 ``nlp`` 对象，再调用 ``predict`` 处理字符串或字符串列表。
- ``src/ner/ner_pipeline.py`` 和 ``src/ner/batch_process.py`` 都把本文件作为底层识别组件。

输入：
- 单个文本字符串或字符串列表。
- 可选模型名、禁用的 spaCy pipeline 组件和 batch 大小。

输出：
- 返回实体字典列表，字段包含 ``mention``、``type``、``start``、``end``、``source``。

与其他文件的关系：
- 是 ``entity_linker.py`` 的直接上游。
- 其输出会在 ``ner_pipeline.py`` 中被进一步补上 Wikidata 链接结果。
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
