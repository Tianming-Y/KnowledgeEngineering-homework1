import pytest

from src.ner import load_model, predict, search_wikidata, link_mentions


def test_spacy_predict_basic():
    nlp = load_model()
    res = predict("Alan Turing was born in London.", nlp=nlp)
    assert isinstance(res, list)
    # 至少识别到一个实体（人名）
    assert any("Alan" in e["mention"] or "Turing" in e["mention"] for e in res)


def test_wikidata_search_smoke():
    # 这是一个轻量级的 smoke 测试，网络不可用时也不致命
    cands = search_wikidata("Alan Turing", limit=3)
    assert isinstance(cands, list)


def test_link_mentions_smoke():
    text = "Alan Turing worked at Bletchley Park."
    nlp = load_model()
    ents = predict(text, nlp=nlp)
    linked = link_mentions(ents, text, top_k=3)
    assert isinstance(linked, list)
