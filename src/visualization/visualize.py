"""知识图谱可视化脚本。

本文件负责把 ``build_graph.py`` 生成的图谱 JSON 渲染成可直接展示和分析的结果，
包括静态 PNG、交互式 HTML，以及围绕某个核心节点生成的 Ego 子图。它是项目流水线的
最后一环，面向结果解释、汇报展示和局部结构观察。

使用方式：
- 直接执行 ``python src/visualization/visualize.py``。
- 可通过 ``--ego-center`` 和 ``--ego-radius`` 指定局部子图中心与半径。

输入：
- ``output/graphs/knowledge_graph.json``。

输出：
- ``output/visualizations/full_graph.png``。
- ``output/visualizations/full_graph.html``。
- ``output/visualizations/ego_<center>.png/.html``。

与其他文件的关系：
- 上游依赖 ``src/kg_construction/build_graph.py`` 生成的图结构文件。
- 常由 ``scripts/run_pipeline.py`` 自动调用，也可以独立运行做不同中心实体的可视化。
"""

import json
import os
import argparse
import networkx as nx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pyvis.network import Network

# 实体类型 -> 颜色映射
TYPE_COLORS = {
    "PERSON": "#e74c3c",
    "ORG": "#3498db",
    "GPE": "#2ecc71",
    "LOC": "#27ae60",
    "DATE": "#f39c12",
    "EVENT": "#9b59b6",
    "WORK_OF_ART": "#e67e22",
    "FAC": "#1abc9c",
    "NORP": "#95a5a6",
    "LAW": "#34495e",
    "LANGUAGE": "#16a085",
    "PRODUCT": "#d35400",
    "CONCEPT": "#8e44ad",
    "DEVICE": "#c0392b",
    "AWARD": "#f1c40f",
    "UNKNOWN": "#bdc3c7",
}


def get_color(node_type: str) -> str:
    return TYPE_COLORS.get(node_type, TYPE_COLORS["UNKNOWN"])


def load_graph(graph_path: str) -> nx.DiGraph:
    """从 JSON 格式加载图"""
    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    G = nx.DiGraph()
    for node in data["nodes"]:
        nid = node.pop("id")
        G.add_node(nid, **node)
    for edge in data["edges"]:
        src = edge.pop("source")
        tgt = edge.pop("target")
        G.add_edge(src, tgt, **edge)
    return G


def visualize_static(
    G: nx.DiGraph, output_path: str, title: str = "Turing Knowledge Graph"
):
    """静态可视化 — Matplotlib"""
    fig, ax = plt.subplots(1, 1, figsize=(20, 16))

    # 使用 spring layout
    pos = nx.spring_layout(G, k=2.0, iterations=50, seed=42)

    # 按类型着色
    node_colors = [get_color(G.nodes[n].get("type", "UNKNOWN")) for n in G.nodes()]

    # 节点大小按度数
    degrees = dict(G.degree())
    max_deg = max(degrees.values()) if degrees else 1
    node_sizes = [300 + 1500 * (degrees[n] / max_deg) for n in G.nodes()]

    # 绘制边
    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        alpha=0.3,
        arrows=True,
        arrowsize=10,
        edge_color="#cccccc",
        width=0.8,
    )

    # 绘制节点
    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.85,
    )

    # 标签 — 只标注度数较高的节点
    degree_threshold = max(2, max_deg * 0.15) if max_deg > 1 else 1
    labels = {n: n for n in G.nodes() if degrees[n] >= degree_threshold}
    nx.draw_networkx_labels(
        G,
        pos,
        labels,
        ax=ax,
        font_size=8,
        font_weight="bold",
    )

    # 边标签（关系）— 只标注非 none 的
    edge_labels = {}
    for u, v, d in G.edges(data=True):
        rel = d.get("relation", "")
        if rel and rel != "none":
            edge_labels[(u, v)] = rel
    if len(edge_labels) < 100:  # 边标签太多会很乱
        nx.draw_networkx_edge_labels(
            G,
            pos,
            edge_labels,
            ax=ax,
            font_size=6,
            alpha=0.7,
        )

    # 图例
    legend_elements = []
    used_types = set(G.nodes[n].get("type", "UNKNOWN") for n in G.nodes())
    for t in sorted(used_types):
        color = get_color(t)
        legend_elements.append(plt.scatter([], [], c=color, s=100, label=t))
    ax.legend(handles=legend_elements, loc="upper left", fontsize=8)

    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Vis] 静态图 -> {output_path}")


def visualize_interactive(
    G: nx.DiGraph, output_path: str, title: str = "Turing Knowledge Graph"
):
    """交互式可视化 — pyvis"""
    net = Network(
        height="900px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#333333",
        directed=True,
        notebook=False,
    )

    # 物理引擎设置
    net.set_options(
        """
    {
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -100,
                "centralGravity": 0.01,
                "springLength": 200,
                "springConstant": 0.08
            },
            "solver": "forceAtlas2Based",
            "stabilization": {
                "iterations": 150
            }
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 200
        }
    }
    """
    )

    # 添加节点
    degrees = dict(G.degree())
    max_deg = max(degrees.values()) if degrees else 1
    for node in G.nodes():
        attrs = G.nodes[node]
        node_type = attrs.get("type", "UNKNOWN")
        color = get_color(node_type)
        size = 15 + 35 * (degrees[node] / max_deg)
        desc = attrs.get("description", "")
        qid = attrs.get("wikidata_qid", "")

        tooltip = f"<b>{node}</b><br>Type: {node_type}"
        if qid:
            tooltip += f"<br>QID: {qid}"
        if desc:
            tooltip += f"<br>{desc}"
        tooltip += f"<br>Degree: {degrees[node]}"

        net.add_node(
            node,
            label=node,
            color=color,
            size=size,
            title=tooltip,
            font={"size": 12},
        )

    # 添加边
    for u, v, d in G.edges(data=True):
        rel = d.get("relation", "")
        conf = d.get("confidence", 0)
        prov = d.get("provenance", "")
        tooltip = f"<b>{rel}</b><br>Confidence: {conf:.2f}<br>Source: {prov}"

        net.add_edge(
            u,
            v,
            title=tooltip,
            label=rel,
            font={"size": 9, "align": "middle"},
            arrows="to",
            color={"color": "#aaaaaa", "highlight": "#333333"},
            width=1 + conf * 2,
        )

    net.save_graph(output_path)
    print(f"[Vis] 交互式图 -> {output_path}")


def visualize_ego(G: nx.DiGraph, center: str, output_dir: str, radius: int = 2):
    """Ego 子图可视化"""
    if center not in G:
        print(f"[Vis] 节点 '{center}' 不在图中")
        return

    # 提取 ego 子图
    ego = nx.ego_graph(G.to_undirected(), center, radius=radius)
    # 保留有向边
    sub_nodes = set(ego.nodes())
    sub_G = G.subgraph(sub_nodes).copy()

    # 静态
    static_path = os.path.join(output_dir, f"ego_{center.replace(' ', '_')}.png")
    visualize_static(sub_G, static_path, title=f"Ego Graph: {center}")

    # 交互式
    html_path = os.path.join(output_dir, f"ego_{center.replace(' ', '_')}.html")
    visualize_interactive(sub_G, html_path, title=f"Ego Graph: {center}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", default="output/graphs/knowledge_graph.json")
    parser.add_argument("--output-dir", default="output/visualizations")
    parser.add_argument("--ego-center", default="Alan Turing", help="Ego 子图中心节点")
    parser.add_argument("--ego-radius", type=int, default=2)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("[Vis] 加载图谱...")
    G = load_graph(args.graph)
    print(f"[Vis] 节点: {G.number_of_nodes()}, 边: {G.number_of_edges()}")

    # 全图静态
    print("[Vis] 生成全图静态可视化...")
    visualize_static(
        G,
        os.path.join(args.output_dir, "full_graph.png"),
        title="Turing Knowledge Graph (Full)",
    )

    # 全图交互式
    print("[Vis] 生成全图交互式可视化...")
    visualize_interactive(
        G,
        os.path.join(args.output_dir, "full_graph.html"),
        title="Turing Knowledge Graph",
    )

    # Ego 子图
    print(f"[Vis] 生成 Ego 子图: {args.ego_center}...")
    visualize_ego(G, args.ego_center, args.output_dir, args.ego_radius)

    print("[Vis] 可视化完成!")


if __name__ == "__main__":
    main()
