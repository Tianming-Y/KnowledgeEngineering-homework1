"""
知识图谱可视化模块 (Knowledge Graph Visualizer)
利用 matplotlib + NetworkX 将图谱渲染为分层彩色图，
并按实体类型着色，边标注关系名称。
"""

from pathlib import Path
from typing import Dict, Optional

import networkx as nx


# ============================================================
#  内部工具
# ============================================================

def _node_colors(G: nx.DiGraph, color_map: Dict[str, str], default: str) -> list:
    return [
        color_map.get(G.nodes[n].get("type", ""), default)
        for n in G.nodes()
    ]


def _node_labels(G: nx.DiGraph) -> Dict[str, str]:
    return {n: G.nodes[n].get("label", n) for n in G.nodes()}


def _short_edge_labels(G: nx.DiGraph) -> Dict[tuple, str]:
    """提取边关系的括号内中文部分作为简短标签。"""
    labels = {}
    for s, t, d in G.edges(data=True):
        rel = d.get("relation", "")
        # 取括号前的中文部分
        short = rel.split("(")[0].strip()
        labels[(s, t)] = short
    return labels


# ============================================================
#  主绘图函数
# ============================================================

def draw_full_graph(
    G: nx.DiGraph,
    color_map: Dict[str, str],
    default_color: str,
    output_path: Optional[Path] = None,
    show: bool = True,
) -> None:
    """绘制完整知识图谱（所有节点和边）。"""
    try:
        import matplotlib
        matplotlib.use("Agg")          # 无显示器环境使用非交互后端
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  [可视化] matplotlib 未安装，跳过绘图。")
        return

    fig, ax = plt.subplots(figsize=(24, 18))
    ax.set_facecolor("#F8F8F8")
    fig.patch.set_facecolor("#F0F0F0")

    # 布局：spring 加 seed 保证可复现
    pos = nx.spring_layout(G, k=2.5, seed=42)

    colors = _node_colors(G, color_map, default_color)
    labels = _node_labels(G)
    edge_labels = _short_edge_labels(G)

    # 画边
    nx.draw_networkx_edges(
        G, pos, ax=ax,
        edge_color="#999999",
        arrows=True,
        arrowsize=15,
        arrowstyle="-|>",
        connectionstyle="arc3,rad=0.1",
        width=1.2,
        alpha=0.7,
    )
    # 画节点
    nx.draw_networkx_nodes(
        G, pos, ax=ax,
        node_color=colors,
        node_size=1800,
        alpha=0.92,
        linewidths=1.5,
        edgecolors="#555555",
    )
    # 节点标签
    nx.draw_networkx_labels(
        G, pos, labels, ax=ax,
        font_size=7.5,
        font_weight="bold",
        font_color="#1a1a1a",
    )
    # 边标签（只显示短中文部分）
    nx.draw_networkx_edge_labels(
        G, pos, edge_labels=edge_labels, ax=ax,
        font_size=6,
        font_color="#444444",
        bbox={"boxstyle": "round,pad=0.15", "fc": "white", "alpha": 0.6, "ec": "none"},
    )

    # 图例
    legend_handles = [
        mpatches.Patch(color=color, label=label)
        for label, color in [
            ("人物 PERSON",     color_map.get("PERSON",  default_color)),
            ("组织 ORG",        color_map.get("ORG",     default_color)),
            ("地点 GPE",        color_map.get("GPE",     default_color)),
            ("核心概念 CONCEPT", color_map.get("CONCEPT", default_color)),
            ("著作/系统 WORK",   color_map.get("WORK",    default_color)),
            ("装置 DEVICE",     color_map.get("DEVICE",  default_color)),
            ("事件 EVENT",      color_map.get("EVENT",   default_color)),
            ("奖项 AWARD",      color_map.get("AWARD",   default_color)),
        ]
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=9,
        framealpha=0.85,
        title="实体类型 (Entity Types)",
        title_fontsize=9,
    )

    ax.set_title("Alan Turing Knowledge Graph (图灵知识图谱)", fontsize=16, fontweight="bold", pad=20)
    ax.axis("off")
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"  ✓ 完整图谱已保存至 {output_path}")
    if show:
        plt.show()
    plt.close()


def draw_ego_graph(
    G: nx.DiGraph,
    center: str,
    color_map: Dict[str, str],
    default_color: str,
    radius: int = 1,
    output_path: Optional[Path] = None,
    show: bool = True,
) -> None:
    """以指定节点为中心，绘制其 radius 跳邻域子图。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  [可视化] matplotlib 未安装，跳过绘图。")
        return

    # 构建无向副本以获取 ego graph
    undirected = G.to_undirected()
    ego = nx.ego_graph(undirected, center, radius=radius)
    sub = G.subgraph(ego.nodes()).copy()

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_facecolor("#F8F8F8")
    fig.patch.set_facecolor("#F0F0F0")

    pos = nx.spring_layout(sub, k=3.0, seed=7)
    colors = _node_colors(sub, color_map, default_color)
    labels = _node_labels(sub)
    edge_labels = _short_edge_labels(sub)

    # 中心节点用更大尺寸
    node_sizes = [
        3600 if n == center else 1600 for n in sub.nodes()
    ]

    nx.draw_networkx_edges(
        sub, pos, ax=ax,
        edge_color="#888888",
        arrows=True,
        arrowsize=18,
        arrowstyle="-|>",
        connectionstyle="arc3,rad=0.1",
        width=1.5,
        alpha=0.8,
    )
    nx.draw_networkx_nodes(
        sub, pos, ax=ax,
        node_color=colors,
        node_size=node_sizes,
        alpha=0.93,
        linewidths=1.8,
        edgecolors="#333333",
    )
    nx.draw_networkx_labels(
        sub, pos, labels, ax=ax,
        font_size=8,
        font_weight="bold",
        font_color="#1a1a1a",
    )
    nx.draw_networkx_edge_labels(
        sub, pos, edge_labels=edge_labels, ax=ax,
        font_size=7,
        font_color="#333333",
        bbox={"boxstyle": "round,pad=0.2", "fc": "white", "alpha": 0.7, "ec": "none"},
    )

    center_label = G.nodes[center].get("label", center)
    ax.set_title(
        f"Ego Graph: {center_label}  (radius={radius})",
        fontsize=13, fontweight="bold", pad=15,
    )
    ax.axis("off")
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"  ✓ Ego 子图已保存至 {output_path}")
    if show:
        plt.show()
    plt.close()


def draw_type_subgraph(
    G: nx.DiGraph,
    types: list,
    color_map: Dict[str, str],
    default_color: str,
    title: str = "子图",
    output_path: Optional[Path] = None,
    show: bool = True,
) -> None:
    """只显示指定实体类型及其相互关系。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [可视化] matplotlib 未安装，跳过绘图。")
        return

    selected = [n for n, d in G.nodes(data=True) if d.get("type") in types]
    sub = G.subgraph(selected).copy()

    if sub.number_of_nodes() == 0:
        print(f"  [可视化] 指定类型 {types} 无节点，跳过。")
        return

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_facecolor("#F8F8F8")
    fig.patch.set_facecolor("#F0F0F0")

    pos = nx.circular_layout(sub)
    colors = _node_colors(sub, color_map, default_color)
    labels = _node_labels(sub)
    edge_labels = _short_edge_labels(sub)

    nx.draw_networkx_edges(sub, pos, ax=ax, edge_color="#777777",
                           arrows=True, arrowsize=15, width=1.2, alpha=0.7)
    nx.draw_networkx_nodes(sub, pos, ax=ax, node_color=colors,
                           node_size=2000, alpha=0.92,
                           linewidths=1.5, edgecolors="#555555")
    nx.draw_networkx_labels(sub, pos, labels, ax=ax,
                            font_size=8, font_weight="bold")
    nx.draw_networkx_edge_labels(sub, pos, edge_labels=edge_labels, ax=ax,
                                 font_size=7, font_color="#444444")

    ax.set_title(title, fontsize=13, fontweight="bold", pad=15)
    ax.axis("off")
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"  ✓ 子图已保存至 {output_path}")
    if show:
        plt.show()
    plt.close()


# ---------- 主程序入口 ----------
if __name__ == "__main__":
    from kg_builder import build_turing_kg, ENTITY_COLORS, DEFAULT_COLOR

    G = build_turing_kg()
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    draw_full_graph(G, ENTITY_COLORS, DEFAULT_COLOR,
                    output_path=out / "turing_kg_full.png", show=False)
    draw_ego_graph(G, "Alan_Turing", ENTITY_COLORS, DEFAULT_COLOR,
                   radius=1, output_path=out / "turing_ego.png", show=False)
    draw_type_subgraph(G, ["CONCEPT", "WORK"], ENTITY_COLORS, DEFAULT_COLOR,
                       title="Concepts & Works Subgraph",
                       output_path=out / "turing_concept_work.png", show=False)
