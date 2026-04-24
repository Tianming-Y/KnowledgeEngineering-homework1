import json

import pytest

pytest.importorskip("flask")

from src.webapp import create_app


def write_sample_graph(path):
    payload = {
        "nodes": [
            {
                "id": "Alan Turing",
                "label": "Alan Turing",
                "type": "PERSON",
                "wikidata_qid": "Q7251",
                "description": "English mathematician",
            },
            {
                "id": "Bletchley Park",
                "label": "Bletchley Park",
                "type": "FAC",
                "wikidata_qid": "Q10108",
                "description": "Codebreaking site",
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
            }
        ],
        "stats": {"num_nodes": 2, "num_edges": 1},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture()
def client(tmp_path):
    graph_path = tmp_path / "knowledge_graph.json"
    write_sample_graph(graph_path)
    app = create_app(graph_path=str(graph_path), project_root=str(tmp_path))
    app.config.update(TESTING=True)
    return app.test_client()


def test_graph_summary(client):
    response = client.get("/api/graph/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["num_nodes"] == 2
    assert payload["num_edges"] == 1


def test_query_endpoint(client):
    response = client.get("/api/query?keyword=Alan")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["matches"][0]["id"] == "Alan Turing"


def test_scripts_endpoint(client):
    response = client.get("/api/scripts")
    assert response.status_code == 200
    payload = response.get_json()
    assert any(row["id"] == "run_pipeline" for row in payload["scripts"])
