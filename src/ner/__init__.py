"""`src.ner` 包导出常用接口。"""

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
