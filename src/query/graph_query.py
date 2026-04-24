"""知识图谱查询服务。

本文件复用 ``output/graphs/knowledge_graph.json`` 中的图谱产物，提供以下能力：
- 根据关键词检索匹配节点
- 返回节点的属性、度数、入边与出边信息
- 提取以某个节点为中心的局部子图，便于前端动态展示

它不依赖关系抽取阶段的中间文件，只消费最终图谱 JSON，因此可以直接作为
“查询层”挂在 CLI 或 Web 服务之上。
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any

import networkx as nx


def normalize_text(text: str) -> str:
    """将字符串压平成便于比较的形式。"""
    collapsed = re.sub(r"\s+", " ", (text or "").strip())
    return collapsed.casefold()


class GraphQueryService:
    """围绕最终图谱 JSON 提供查询与子图提取能力。"""

    def __init__(self, graph_path: str = "output/graphs/knowledge_graph.json"):
        self.graph_path = graph_path
        self.graph = nx.DiGraph()
        self._node_index: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> dict[str, Any]:
        """从磁盘重新加载图谱文件，并返回最新概要信息。"""
        if not os.path.exists(self.graph_path):
            raise FileNotFoundError(self.graph_path)

        with open(self.graph_path, "r", encoding="utf-8") as handle:
            raw_graph = json.load(handle)

        graph = nx.DiGraph()
        for node in raw_graph.get("nodes", []):
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                continue
            attrs = {key: value for key, value in node.items() if key != "id"}
            graph.add_node(node_id, **attrs)

        for edge in raw_graph.get("edges", []):
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            if not source or not target:
                continue
            attrs = {
                key: value
                for key, value in edge.items()
                if key not in {"source", "target"}
            }
            graph.add_edge(source, target, **attrs)

        self.graph = graph
        self._node_index = self._build_node_index()
        return self.get_summary()

    def _build_node_index(self) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for node_id, attrs in self.graph.nodes(data=True):
            label = attrs.get("label", node_id)
            node_type = attrs.get("type", "UNKNOWN")
            qid = attrs.get("wikidata_qid", "")
            description = attrs.get("description", "")
            tokens = {
                token
                for token in re.split(r"[^\w]+", f"{label} {description}")
                if token
            }
            index[node_id] = {
                "label": normalize_text(label),
                "id": normalize_text(node_id),
                "type": normalize_text(node_type),
                "qid": normalize_text(qid),
                "description": normalize_text(description),
                "tokens": {normalize_text(token) for token in tokens},
            }
        return index

    def get_summary(self) -> dict[str, Any]:
        """返回图谱规模和类型分布概览。"""
        type_counter = Counter(
            attrs.get("type", "UNKNOWN") for _, attrs in self.graph.nodes(data=True)
        )
        relation_counter = Counter(
            attrs.get("relation", "unknown")
            for _, _, attrs in self.graph.edges(data=True)
        )
        return {
            "graph_path": self.graph_path,
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "top_node_types": [
                {"type": node_type, "count": count}
                for node_type, count in type_counter.most_common(8)
            ],
            "top_relations": [
                {"relation": relation, "count": count}
                for relation, count in relation_counter.most_common(8)
            ],
        }

    def search_nodes(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """基于关键词搜索匹配节点。"""
        query = normalize_text(keyword)
        if not query:
            return []

        query_tokens = {token for token in re.split(r"[^\w]+", query) if token}
        matches: list[dict[str, Any]] = []

        for node_id, attrs in self.graph.nodes(data=True):
            indexed = self._node_index[node_id]
            score = 0.0

            if query == indexed["label"]:
                score += 120
            elif query == indexed["id"]:
                score += 110
            elif indexed["qid"] and query == indexed["qid"]:
                score += 100

            if indexed["label"].startswith(query):
                score += 60
            if indexed["id"].startswith(query):
                score += 50
            if query in indexed["label"]:
                score += 40
            if query in indexed["id"]:
                score += 35
            if indexed["qid"] and query in indexed["qid"]:
                score += 30
            if query in indexed["type"]:
                score += 20
            if query in indexed["description"]:
                score += 10

            if query_tokens:
                token_overlap = len(query_tokens & indexed["tokens"])
                score += token_overlap * 8

            if score <= 0:
                continue

            matches.append(
                {
                    "id": node_id,
                    "label": attrs.get("label", node_id),
                    "type": attrs.get("type", "UNKNOWN"),
                    "wikidata_qid": attrs.get("wikidata_qid", ""),
                    "description": attrs.get("description", ""),
                    "degree": int(self.graph.degree(node_id)),
                    "score": round(score, 2),
                }
            )

        matches.sort(
            key=lambda item: (-item["score"], -item["degree"], item["label"].casefold())
        )
        return matches[:limit]

    def resolve_node_id(self, identifier: str) -> str | None:
        """按大小写不敏感方式解析节点 ID。"""
        if identifier in self.graph:
            return identifier

        normalized = normalize_text(identifier)
        for node_id in self.graph.nodes:
            indexed = self._node_index[node_id]
            if normalized in {indexed["id"], indexed["label"]}:
                return node_id
        return None

    def get_node_details(
        self, node_id: str, neighbor_limit: int = 20
    ) -> dict[str, Any]:
        """返回节点属性、邻居与边明细。"""
        resolved = self.resolve_node_id(node_id)
        if resolved is None:
            raise KeyError(node_id)

        attrs = self.graph.nodes[resolved]
        outgoing = []
        incoming = []
        neighbors: dict[str, dict[str, Any]] = {}

        for _, target, edge_attrs in self.graph.out_edges(resolved, data=True):
            row = self._edge_to_row(resolved, target, edge_attrs, direction="out")
            outgoing.append(row)
            neighbors.setdefault(target, self._neighbor_stub(target))
            neighbors[target]["outgoing_relations"].append(row)

        for source, _, edge_attrs in self.graph.in_edges(resolved, data=True):
            row = self._edge_to_row(source, resolved, edge_attrs, direction="in")
            incoming.append(row)
            neighbors.setdefault(source, self._neighbor_stub(source))
            neighbors[source]["incoming_relations"].append(row)

        outgoing.sort(
            key=lambda row: (row["target"].casefold(), row["relation"].casefold())
        )
        incoming.sort(
            key=lambda row: (row["source"].casefold(), row["relation"].casefold())
        )

        neighbor_rows = []
        for neighbor in neighbors.values():
            relation_count = len(neighbor["incoming_relations"]) + len(
                neighbor["outgoing_relations"]
            )
            neighbor_rows.append(
                {
                    "id": neighbor["id"],
                    "label": neighbor["label"],
                    "type": neighbor["type"],
                    "wikidata_qid": neighbor["wikidata_qid"],
                    "description": neighbor["description"],
                    "degree": int(self.graph.degree(neighbor["id"])),
                    "relation_count": relation_count,
                    "incoming_relations": neighbor["incoming_relations"][:5],
                    "outgoing_relations": neighbor["outgoing_relations"][:5],
                }
            )

        neighbor_rows.sort(
            key=lambda row: (
                -row["relation_count"],
                -row["degree"],
                row["label"].casefold(),
            )
        )

        return {
            "node": {
                "id": resolved,
                "label": attrs.get("label", resolved),
                "type": attrs.get("type", "UNKNOWN"),
                "wikidata_qid": attrs.get("wikidata_qid", ""),
                "description": attrs.get("description", ""),
                "degree": int(self.graph.degree(resolved)),
                "in_degree": int(self.graph.in_degree(resolved)),
                "out_degree": int(self.graph.out_degree(resolved)),
            },
            "incoming": incoming[:neighbor_limit],
            "outgoing": outgoing[:neighbor_limit],
            "neighbors": neighbor_rows[:neighbor_limit],
        }

    def _neighbor_stub(self, node_id: str) -> dict[str, Any]:
        attrs = self.graph.nodes[node_id]
        return {
            "id": node_id,
            "label": attrs.get("label", node_id),
            "type": attrs.get("type", "UNKNOWN"),
            "wikidata_qid": attrs.get("wikidata_qid", ""),
            "description": attrs.get("description", ""),
            "incoming_relations": [],
            "outgoing_relations": [],
        }

    def _edge_to_row(
        self, source: str, target: str, edge_attrs: dict[str, Any], direction: str
    ) -> dict[str, Any]:
        return {
            "source": source,
            "target": target,
            "relation": edge_attrs.get("relation", ""),
            "confidence": edge_attrs.get("confidence", 0),
            "provenance": edge_attrs.get("provenance", ""),
            "sentence": edge_attrs.get("sentence", ""),
            "direction": direction,
        }

    def get_subgraph(
        self,
        center_node: str,
        radius: int = 1,
        max_nodes: int = 80,
    ) -> dict[str, Any]:
        """返回指定中心节点的局部子图。"""
        resolved = self.resolve_node_id(center_node)
        if resolved is None:
            raise KeyError(center_node)

        ego_graph = nx.ego_graph(self.graph.to_undirected(), resolved, radius=radius)
        sub_nodes = list(ego_graph.nodes())
        if len(sub_nodes) > max_nodes:
            lengths = nx.single_source_shortest_path_length(
                self.graph.to_undirected(), resolved, cutoff=radius
            )
            sub_nodes.sort(
                key=lambda node_id: (
                    lengths.get(node_id, radius + 1),
                    -self.graph.degree(node_id),
                    self.graph.nodes[node_id].get("label", node_id).casefold(),
                )
            )
            selected = set(sub_nodes[:max_nodes])
            selected.add(resolved)
            ego_graph = self.graph.subgraph(selected).copy()
        else:
            ego_graph = self.graph.subgraph(sub_nodes).copy()

        return self._graph_to_payload(ego_graph, center_node=resolved)

    def get_full_graph(self) -> dict[str, Any]:
        """返回完整图谱，供前端初始化网络图。"""
        return self._graph_to_payload(self.graph)

    def query(self, keyword: str, limit: int = 10, radius: int = 1) -> dict[str, Any]:
        """执行关键词查询，并附带主结果的详情与子图。"""
        matches = self.search_nodes(keyword, limit=limit)
        if not matches:
            return {
                "keyword": keyword,
                "matches": [],
                "primary": None,
                "subgraph": {"nodes": [], "edges": [], "stats": {"center_node": None}},
            }

        primary_id = matches[0]["id"]
        return {
            "keyword": keyword,
            "matches": matches,
            "primary": self.get_node_details(primary_id),
            "subgraph": self.get_subgraph(primary_id, radius=radius),
        }

    def _graph_to_payload(
        self, graph: nx.DiGraph, center_node: str | None = None
    ) -> dict[str, Any]:
        nodes = []
        edges = []
        for node_id, attrs in graph.nodes(data=True):
            nodes.append(
                {
                    "id": node_id,
                    "label": attrs.get("label", node_id),
                    "type": attrs.get("type", "UNKNOWN"),
                    "wikidata_qid": attrs.get("wikidata_qid", ""),
                    "description": attrs.get("description", ""),
                    "degree": int(graph.degree(node_id)),
                    "is_center": node_id == center_node,
                }
            )
        for source, target, attrs in graph.edges(data=True):
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation": attrs.get("relation", ""),
                    "confidence": attrs.get("confidence", 0),
                    "provenance": attrs.get("provenance", ""),
                    "sentence": attrs.get("sentence", ""),
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "num_nodes": len(nodes),
                "num_edges": len(edges),
                "center_node": center_node,
            },
        }
