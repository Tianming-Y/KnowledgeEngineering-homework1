"""实体识别与消歧子包。

本文件统一导出 NER 阶段的常用接口，包括 spaCy 模型加载、实体识别、
Wikidata 实体链接以及简单的端到端文本处理函数。

使用方式：
- 其他模块可直接从 ``src.ner`` 导入 ``load_model``、``predict``、
    ``process_text``、``link_mentions`` 等函数，避免感知底层文件拆分。

与其他文件的关系：
- ``src/ner/batch_process.py`` 和 ``src/ner/ner_pipeline.py`` 直接依赖这里导出的能力。
- 本子包输出的实体结果会进入关系抽取与知识图谱构建模块。
"""

from .ner_pipeline import process_text, process_texts
from .spacy_ner import load_model, predict
from .entity_linker import link_mentions, link_mention, search_wikidata

__all__ = [
    "process_text",
    "process_texts",
    "load_model",
    "predict",
    "link_mentions",
    "link_mention",
    "search_wikidata",
]
