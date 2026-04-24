"""知识图谱构建与持久化脚本。

本文件负责把最终关系三元组转换成 ``networkx.DiGraph``，并把实体与关系补充为节点、边属性，
随后导出为 GraphML、GEXF 和 JSON 三种格式。它是项目从“文本关系”过渡到“图结构数据”的关键节点。

使用方式：
- 直接执行 ``python src/kg_construction/build_graph.py``。
- 一般由 ``scripts/run_pipeline.py`` 在关系抽取结束后自动调用。

输入：
- ``output/graphs/relation_triples_aliased.jsonl`` 或兼容结构的三元组文件。
- 可选 ``output/entities_all.jsonl``，用于补全节点类型、QID 与描述。

输出：
- ``output/graphs/knowledge_graph.graphml``。
- ``output/graphs/knowledge_graph.gexf``。
- ``output/graphs/knowledge_graph.json``。
- 终端打印图谱统计信息。

与其他文件的关系：
- 上游依赖 ``merge_triples.py`` 和 ``apply_aliases.py``。
- 下游 ``src/visualization/visualize.py`` 直接加载这里生成的 JSON 图文件。
"""

import json
import os
import argparse
import re
import networkx as nx


def load_triples(path: str) -> list[dict]:
    triples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                triples.append(json.loads(line))
    return triples


def load_entities(path: str) -> dict:
    """加载实体信息，构建 {mention -> entity_info}"""
    entity_map = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for ent in row.get("entities", []):
                mention = ent["mention"]
                if mention not in entity_map:
                    entity_map[mention] = {
                        "type": ent.get("type", "UNKNOWN"),
                        "wikidata_qid": ent.get("wikidata_qid", ""),
                        "wikidata_label": ent.get("wikidata_label", ""),
                        "wikidata_description": ent.get("wikidata_description", ""),
                    }
    return entity_map


def apply_hardcoded_aliases_for_node(text: str) -> str:
    """
    最小范围别名映射：把常见的 'Turing' 及变体规范为 'Alan Turing'，
    仅用于构建图谱时的节点合并，不改变原始三元组文件。
    """
    if not text:
        return text
    norm = re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()
    aliases = {
        "turing": "Alan Turing",
        "alan turing": "Alan Turing",
        "alan mathison turing": "Alan Turing",
    }
    return aliases.get(norm, text)


def build_knowledge_graph(
    triples: list[dict],
    entity_map: dict | None = None,
) -> nx.DiGraph:
    """从三元组构建知识图谱"""
    G = nx.DiGraph()

    for t in triples:
        head = apply_hardcoded_aliases_for_node(t.get("head", ""))
        tail = apply_hardcoded_aliases_for_node(t.get("tail", ""))
        relation = t.get("relation", "")

        # 添加节点
        if not G.has_node(head):
            info = entity_map.get(head, {}) if entity_map else {}
            G.add_node(
                head,
                **{
                    "label": head,
                    "type": info.get("type", "UNKNOWN"),
                    "wikidata_qid": info.get("wikidata_qid", ""),
                    "description": info.get("wikidata_description", ""),
                },
            )

        if not G.has_node(tail):
            info = entity_map.get(tail, {}) if entity_map else {}
            G.add_node(
                tail,
                **{
                    "label": tail,
                    "type": info.get("type", "UNKNOWN"),
                    "wikidata_qid": info.get("wikidata_qid", ""),
                    "description": info.get("wikidata_description", ""),
                },
            )

        # 添加边（如果已存在相同关系的边，取置信度更高的）
        edge_key = (head, tail, relation)
        if G.has_edge(head, tail):
            existing = G[head][tail]
            if existing.get("relation") == relation:
                if t.get("confidence", 0) > existing.get("confidence", 0):
                    G[head][tail].update(
                        {
                            "confidence": t.get("confidence", 0),
                            "sentence": t.get("sentence", ""),
                            "provenance": t.get("provenance", ""),
                        }
                    )
                continue

        G.add_edge(
            head,
            tail,
            relation=relation,
            confidence=t.get("confidence", 0),
            sentence=t.get("sentence", ""),
            doc=t.get("doc", ""),
            provenance=t.get("provenance", ""),
        )

    return G


def save_graph(G: nx.DiGraph, output_dir: str):
    """保存图谱为多种格式"""
    os.makedirs(output_dir, exist_ok=True)

    # 清理属性中的 None 值，GraphML 不支持 NoneType
    for n, attrs in list(G.nodes(data=True)):
        for k, v in list(attrs.items()):
            if v is None:
                G.nodes[n][k] = ""
    for u, v, attrs in list(G.edges(data=True)):
        for k, val in list(attrs.items()):
            if val is None:
                G[u][v][k] = ""

    # GraphML 格式（推荐，保留所有属性）
    graphml_path = os.path.join(output_dir, "knowledge_graph.graphml")
    nx.write_graphml(G, graphml_path)
    print(f"[KG] GraphML -> {graphml_path}")

    # GEXF 格式（Gephi 兼容）
    gexf_path = os.path.join(output_dir, "knowledge_graph.gexf")
    nx.write_gexf(G, gexf_path)
    print(f"[KG] GEXF -> {gexf_path}")

    # JSON 格式（节点+边列表）
    graph_data = {
        "nodes": [],
        "edges": [],
        "stats": {
            "num_nodes": G.number_of_nodes(),
            "num_edges": G.number_of_edges(),
        },
    }
    for node, attrs in G.nodes(data=True):
        graph_data["nodes"].append(
            {
                "id": node,
                **{k: v for k, v in attrs.items()},
            }
        )
    for u, v, attrs in G.edges(data=True):
        graph_data["edges"].append(
            {
                "source": u,
                "target": v,
                **{k: v2 for k, v2 in attrs.items()},
            }
        )

    json_path = os.path.join(output_dir, "knowledge_graph.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)
    print(f"[KG] JSON -> {json_path}")


def print_graph_stats(G: nx.DiGraph):
    """打印图谱统计信息"""
    print(f"\n{'='*50}")
    print(f"知识图谱统计:")
    print(f"  节点数: {G.number_of_nodes()}")
    print(f"  边数:   {G.number_of_edges()}")

    # 节点类型分布
    type_counts = {}
    for _, attrs in G.nodes(data=True):
        t = attrs.get("type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  节点类型分布:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # 关系类型分布
    rel_counts = {}
    for _, _, attrs in G.edges(data=True):
        r = attrs.get("relation", "unknown")
        rel_counts[r] = rel_counts.get(r, 0) + 1
    print(f"  关系类型分布:")
    for r, c in sorted(rel_counts.items(), key=lambda x: -x[1]):
        print(f"    {r}: {c}")

    # 度数最高的节点
    top_nodes = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:10]
    print(f"  度数最高的10个节点:")
    for node, deg in top_nodes:
        print(f"    {node}: {deg}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--triples", default="output/graphs/relation_triples.jsonl")
    parser.add_argument("--entities", default="output/entities_all.jsonl")
    parser.add_argument("--output-dir", default="output/graphs")
    args = parser.parse_args()

    print("[KG] 加载三元组...")
    triples = load_triples(args.triples)
    print(f"[KG] 三元组数: {len(triples)}")

    print("[KG] 加载实体信息...")
    entity_map = load_entities(args.entities) if os.path.exists(args.entities) else {}

    print("[KG] 构建知识图谱...")
    G = build_knowledge_graph(triples, entity_map)

    print_graph_stats(G)

    print("[KG] 保存图谱...")
    save_graph(G, args.output_dir)

    print("[KG] 完成!")


if __name__ == "__main__":
    main()
