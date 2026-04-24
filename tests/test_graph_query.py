import json

from src.query import GraphQueryService


def write_sample_graph(path):
    payload = {
        "nodes": [
            {
                "id": "Alan Turing",
                "label": "Alan Turing",
                "type": "PERSON",
                "wikidata_qid": "Q7251",
                "description": "English mathematician and computer scientist",
            },
            {
                "id": "Bletchley Park",
                "label": "Bletchley Park",
                "type": "FAC",
                "wikidata_qid": "Q10108",
                "description": "British codebreaking centre during World War II",
            },
            {
                "id": "Princeton University",
                "label": "Princeton University",
                "type": "ORG",
                "wikidata_qid": "Q8358",
                "description": "Private Ivy League research university",
            },
        ],
        "edges": [
            {
                "source": "Alan Turing",
                "target": "Bletchley Park",
                "relation": "worked_at",
                "confidence": 1.0,
                "provenance": "infobox",
                "sentence": "Alan Turing worked at Bletchley Park.",
            },
            {
                "source": "Alan Turing",
                "target": "Princeton University",
                "relation": "educated_at",
                "confidence": 1.0,
                "provenance": "infobox",
                "sentence": "Alan Turing studied at Princeton University.",
            },
        ],
        "stats": {"num_nodes": 3, "num_edges": 2},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_search_nodes_returns_best_match(tmp_path):
    graph_path = tmp_path / "knowledge_graph.json"
    write_sample_graph(graph_path)

    service = GraphQueryService(graph_path=str(graph_path))
    matches = service.search_nodes("turing")

    assert matches
    assert matches[0]["id"] == "Alan Turing"
    assert matches[0]["type"] == "PERSON"


def test_get_node_details_includes_relations(tmp_path):
    graph_path = tmp_path / "knowledge_graph.json"
    write_sample_graph(graph_path)

    service = GraphQueryService(graph_path=str(graph_path))
    details = service.get_node_details("Alan Turing")

    assert details["node"]["degree"] == 2
    assert any(edge["relation"] == "worked_at" for edge in details["outgoing"])
    assert any(neighbor["id"] == "Bletchley Park" for neighbor in details["neighbors"])


def test_query_returns_subgraph(tmp_path):
    graph_path = tmp_path / "knowledge_graph.json"
    write_sample_graph(graph_path)

    service = GraphQueryService(graph_path=str(graph_path))
    payload = service.query("Princeton")

    assert payload["matches"]
    assert payload["primary"]["node"]["label"] == "Princeton University"
    assert payload["subgraph"]["stats"]["num_nodes"] >= 1
