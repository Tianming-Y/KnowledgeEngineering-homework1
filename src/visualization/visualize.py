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
import math
from collections import Counter
import networkx as nx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
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

RELATION_COLORS = [
    "#c95b38",
    "#1d7f77",
    "#4d8a4f",
    "#9b4f7d",
    "#ae6831",
    "#42516f",
    "#d7a63c",
    "#7a5db8",
    "#3286a8",
    "#8e6c35",
    "#7b5f52",
    "#2f7c64",
]


def get_color(node_type: str) -> str:
    return TYPE_COLORS.get(node_type, TYPE_COLORS["UNKNOWN"])


def get_relation_color(relation: str) -> str:
    normalized = (relation or "unknown").strip().lower()
    color_key = sum((index + 1) * ord(char) for index, char in enumerate(normalized))
    return RELATION_COLORS[color_key % len(RELATION_COLORS)]


def _layout_extent(positions: dict) -> tuple[float, float]:
    if not positions:
        return 0.0, 0.0
    xs = [float(value[0]) for value in positions.values()]
    ys = [float(value[1]) for value in positions.values()]
    return max(xs) - min(xs), max(ys) - min(ys)


def _center_layout(positions: dict) -> dict:
    if not positions:
        return {}
    avg_x = sum(float(value[0]) for value in positions.values()) / len(positions)
    avg_y = sum(float(value[1]) for value in positions.values()) / len(positions)
    return {
        node: (float(value[0]) - avg_x, float(value[1]) - avg_y)
        for node, value in positions.items()
    }


def _scale_layout_to_span(positions: dict, target_span: float) -> dict:
    centered = _center_layout(positions)
    width, height = _layout_extent(centered)
    current_span = max(width, height, 1e-6)
    scale = target_span / current_span
    return {node: (x * scale, y * scale) for node, (x, y) in centered.items()}


def _even_out_radial_density(positions: dict) -> dict:
    centered = _center_layout(positions)
    max_radius = max((math.hypot(x, y) for x, y in centered.values()), default=0.0)
    if max_radius <= 1e-6:
        return centered

    redistributed = {}
    for node, (x, y) in centered.items():
        radius = math.hypot(x, y)
        if radius <= 1e-9:
            redistributed[node] = (0.0, 0.0)
            continue
        normalized = min(1.0, radius / max_radius)
        adjusted = min(1.0, 0.58 * normalized + 0.42 * math.pow(normalized, 0.72))
        factor = (adjusted * max_radius) / radius
        redistributed[node] = (x * factor, y * factor)
    return redistributed


def _layout_connected_component(component_graph: nx.Graph, seed: int) -> dict:
    nodes = list(component_graph.nodes())
    node_count = component_graph.number_of_nodes()
    if node_count == 1:
        return {nodes[0]: (0.0, 0.0)}
    if node_count == 2:
        return {nodes[0]: (-1.2, 0.0), nodes[1]: (1.2, 0.0)}

    base_graph = component_graph.to_undirected()
    initial = nx.spectral_layout(base_graph, scale=1.0)
    local_k = max(0.9, min(2.6, 2.2 / max(1.0, math.sqrt(node_count / 2.0))))
    positions = nx.spring_layout(
        base_graph,
        pos=initial,
        seed=seed,
        k=local_k,
        iterations=350,
        scale=1.0,
    )
    positions = _even_out_radial_density(positions)
    target_span = max(4.0, math.sqrt(node_count) * 3.0)
    return _scale_layout_to_span(positions, target_span)


def build_static_layout(G: nx.DiGraph) -> dict:
    if G.number_of_nodes() == 0:
        return {}

    components = [
        G.subgraph(nodes).copy() for nodes in nx.connected_components(G.to_undirected())
    ]
    components.sort(key=lambda graph: graph.number_of_nodes(), reverse=True)

    prepared_layouts = []
    max_component_span = 0.0
    for index, component in enumerate(components):
        local_positions = _layout_connected_component(component, seed=42 + index)
        width, height = _layout_extent(local_positions)
        span = max(width, height, 2.4)
        prepared_layouts.append((local_positions, span))
        max_component_span = max(max_component_span, span)

    if len(prepared_layouts) == 1:
        return prepared_layouts[0][0]

    columns = math.ceil(math.sqrt(len(prepared_layouts)))
    rows = math.ceil(len(prepared_layouts) / columns)
    center_row = (rows - 1) / 2
    center_col = (columns - 1) / 2
    slots = sorted(
        [(row, col) for row in range(rows) for col in range(columns)],
        key=lambda slot: (
            (slot[0] - center_row) ** 2 + (slot[1] - center_col) ** 2,
            abs(slot[0] - center_row),
            abs(slot[1] - center_col),
        ),
    )

    cell_span = max_component_span + 5.0
    merged_positions = {}
    for (local_positions, _), (row, col) in zip(prepared_layouts, slots):
        offset_x = (col - center_col) * cell_span
        offset_y = (center_row - row) * cell_span
        for node, (x, y) in local_positions.items():
            merged_positions[node] = (x + offset_x, y + offset_y)

    target_span = max(
        20.0,
        math.sqrt(G.number_of_nodes() + len(prepared_layouts) * 4) * 5.0,
    )
    return _scale_layout_to_span(merged_positions, target_span)


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
    node_count = max(1, G.number_of_nodes())
    edge_count = max(1, G.number_of_edges())
    pos = build_static_layout(G)
    layout_width, layout_height = _layout_extent(pos)
    scene_span = max(layout_width, layout_height, math.sqrt(node_count) * 4.0)
    canvas_width = max(30, min(56, 22 + scene_span * 0.4))
    canvas_height = max(24, min(44, 18 + scene_span * 0.33))
    fig, ax = plt.subplots(1, 1, figsize=(canvas_width, canvas_height))

    # 按类型着色
    node_colors = [get_color(G.nodes[n].get("type", "UNKNOWN")) for n in G.nodes()]

    # 节点大小按度数
    degrees = dict(G.degree())
    max_deg = max(degrees.values()) if degrees else 1
    node_sizes = [420 + 1900 * (degrees[n] / max_deg) for n in G.nodes()]

    # 绘制边
    edgelist = list(G.edges(data=True))
    edge_colors = [
        get_relation_color(data.get("relation", "unknown")) for _, _, data in edgelist
    ]
    edge_widths = [
        1.4 + 1.6 * float(data.get("confidence", 0) or 0) for _, _, data in edgelist
    ]
    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        edgelist=[(source, target) for source, target, _ in edgelist],
        alpha=0.76,
        arrows=True,
        arrowsize=14,
        edge_color=edge_colors,
        width=edge_widths,
        connectionstyle="arc3,rad=0.05",
    )

    # 绘制节点
    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.85,
        linewidths=0.9,
        edgecolors="#f8f4ed",
    )

    # 标签 — 为所有节点绘制标签，避免静态图在较小缩放下丢失节点信息
    labels = {n: n for n in G.nodes()}
    label_font_size = max(6, min(10, 10 - node_count // 40))
    nx.draw_networkx_labels(
        G,
        pos,
        labels,
        ax=ax,
        font_size=label_font_size,
        font_weight="bold",
        bbox={
            "facecolor": "#fffaf2",
            "edgecolor": "#d7d0c0",
            "boxstyle": "round,pad=0.2",
            "alpha": 0.9,
        },
    )

    # 边标签（关系）— 只标注非 none 的
    edge_labels = {}
    for u, v, d in G.edges(data=True):
        rel = d.get("relation", "")
        if rel and rel != "none":
            edge_labels[(u, v)] = rel
    if len(edge_labels) <= 80:
        nx.draw_networkx_edge_labels(
            G,
            pos,
            edge_labels,
            ax=ax,
            font_size=max(5, min(7, label_font_size - 1)),
            alpha=0.7,
        )

    # 图例
    legend_elements = []
    used_types = set(G.nodes[n].get("type", "UNKNOWN") for n in G.nodes())
    for t in sorted(used_types):
        color = get_color(t)
        legend_elements.append(plt.scatter([], [], c=color, s=100, label=t))
    node_legend = ax.legend(
        handles=legend_elements, loc="upper left", fontsize=8, framealpha=0.94
    )
    ax.add_artist(node_legend)

    relation_counts = Counter(
        data.get("relation", "unknown")
        for _, _, data in edgelist
        if data.get("relation")
    )
    relation_handles = [
        Line2D(
            [0],
            [0],
            color=get_relation_color(relation),
            lw=3,
            label=f"{relation} ({count})",
        )
        for relation, count in relation_counts.most_common(8)
    ]
    if relation_handles:
        ax.legend(
            handles=relation_handles,
            loc="upper right",
            fontsize=8,
            title="Top Relations",
            framealpha=0.94,
        )

    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.axis("off")
    ax.margins(0.12)

    plt.tight_layout()
    export_dpi = max(220, min(340, int(220 + node_count * 0.5 + edge_count * 0.2)))
    plt.savefig(output_path, dpi=export_dpi, bbox_inches="tight", pad_inches=0.45)
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
        relation_color = get_relation_color(rel)
        tooltip = f"<b>{rel}</b><br>Confidence: {conf:.2f}<br>Source: {prov}"

        net.add_edge(
            u,
            v,
            title=tooltip,
            label=rel,
            font={
                "size": 9,
                "align": "middle",
                "color": relation_color,
                "strokeWidth": 3,
                "strokeColor": "#ffffff",
            },
            arrows="to",
            color={
                "color": relation_color,
                "highlight": relation_color,
                "hover": relation_color,
                "opacity": 0.85,
            },
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
