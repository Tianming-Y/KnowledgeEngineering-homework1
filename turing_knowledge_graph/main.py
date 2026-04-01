"""
图灵知识图谱 Demo 主程序
=========================
运行本程序将依次执行：
  1. 命名实体识别 (NER) — 从文本中识别人物、组织、地点、概念等实体
  2. 知识图谱构建   — 定义结构化三元组，构建有向知识图谱
  3. 图谱查询       — 邻居查询、最短路径查询等
  4. 可视化         — 生成三张图并保存至 output/ 目录
  5. JSON 导出      — 将图谱导出为 output/turing_kg.json

用法：
    cd turing_knowledge_graph
    python main.py
"""

import sys
from pathlib import Path

# 确保模块可被导入
sys.path.insert(0, str(Path(__file__).parent))

from ner_demo import recognize_entities, print_ner_report, group_by_label
from kg_builder import (
    build_turing_kg,
    print_graph_stats,
    get_neighbors,
    query_relation_path,
    export_json,
    ENTITY_COLORS,
    DEFAULT_COLOR,
)
from visualizer import draw_full_graph, draw_ego_graph, draw_type_subgraph


# ============================================================
#  步骤 1 — 命名实体识别
# ============================================================

def step_ner() -> None:
    print("\n" + "█" * 60)
    print("  步骤 1：命名实体识别 (Named Entity Recognition)")
    print("█" * 60)

    data_path = Path(__file__).parent / "data" / "turing_text.txt"
    text = data_path.read_text(encoding="utf-8")
    print(f"\n  输入文本：{len(text)} 个字符，{len(text.splitlines())} 行")

    entities = recognize_entities(text)
    print_ner_report(entities)

    groups = group_by_label(entities)
    total_types = len(groups)
    total_unique = sum(len(v) for v in groups.values())
    print(f"\n  识别到 {total_types} 种实体类型，共 {total_unique} 个唯一实体。")


# ============================================================
#  步骤 2 — 知识图谱构建
# ============================================================

def step_build_kg():
    print("\n" + "█" * 60)
    print("  步骤 2：知识图谱构建 (Knowledge Graph Construction)")
    print("█" * 60)

    G = build_turing_kg()
    print_graph_stats(G)

    # 展示一条三元组示例
    print("\n  三元组示例（前 10 条）：")
    for i, (s, t, d) in enumerate(G.edges(data=True)):
        if i >= 10:
            break
        sl = G.nodes[s].get("label", s)
        tl = G.nodes[t].get("label", t)
        print(f"    ({sl})  --[{d['relation']}]-->  ({tl})")

    return G


# ============================================================
#  步骤 3 — 知识图谱查询
# ============================================================

def step_query(G) -> None:
    print("\n" + "█" * 60)
    print("  步骤 3：知识图谱查询 (Graph Querying)")
    print("█" * 60)

    # 3.1 邻居查询
    query_node = "Alan_Turing"
    info = get_neighbors(G, query_node)
    print(f"\n  ▶ 节点「{info['label']}」的直接关联：")
    print(f"    类型: {info['type']}  |  描述: {info['desc']}")
    print(f"    出边 ({len(info['out_edges'])} 条):")
    for e in info["out_edges"][:8]:
        tl = G.nodes[e["target"]].get("label", e["target"])
        print(f"      → {tl}  [{e['relation']}]")
    print(f"    入边 ({len(info['in_edges'])} 条):")
    for e in info["in_edges"][:5]:
        sl = G.nodes[e["source"]].get("label", e["source"])
        print(f"      ← {sl}  [{e['relation']}]")

    # 3.2 最短路径查询
    pairs = [
        ("Alan_Turing", "AI"),
        ("Alonzo_Church", "AI"),
        ("WWII", "Computability"),
    ]
    print("\n  ▶ 最短路径查询：")
    for src, tgt in pairs:
        path = query_relation_path(G, src, tgt)
        sl = G.nodes[src].get("label", src)
        tl = G.nodes[tgt].get("label", tgt)
        if path:
            path_labels = " → ".join(G.nodes[n].get("label", n) for n in path)
            print(f"    {sl} → {tl}：{path_labels}（{len(path)-1} 跳）")
        else:
            print(f"    {sl} → {tl}：无路径")

    # 3.3 按类型统计概念节点
    concepts = [
        (n, d.get("label", n))
        for n, d in G.nodes(data=True)
        if d.get("type") == "CONCEPT"
    ]
    print(f"\n  ▶ 核心概念节点（共 {len(concepts)} 个）：")
    for nid, lbl in concepts:
        desc = G.nodes[nid].get("desc", "")
        print(f"    • {lbl}：{desc}")


# ============================================================
#  步骤 4 — 可视化
# ============================================================

def step_visualize(G) -> None:
    print("\n" + "█" * 60)
    print("  步骤 4：知识图谱可视化 (Visualization)")
    print("█" * 60)

    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    print("\n  正在生成完整图谱图像……")
    draw_full_graph(
        G, ENTITY_COLORS, DEFAULT_COLOR,
        output_path=out / "turing_kg_full.png",
        show=False,
    )

    print("  正在生成图灵 Ego 子图……")
    draw_ego_graph(
        G, "Alan_Turing", ENTITY_COLORS, DEFAULT_COLOR,
        radius=1,
        output_path=out / "turing_ego.png",
        show=False,
    )

    print("  正在生成概念与著作子图……")
    draw_type_subgraph(
        G, ["CONCEPT", "WORK"], ENTITY_COLORS, DEFAULT_COLOR,
        title="Concepts & Works Subgraph (概念与著作关系子图)",
        output_path=out / "turing_concept_work.png",
        show=False,
    )


# ============================================================
#  步骤 5 — JSON 导出
# ============================================================

def step_export(G) -> None:
    print("\n" + "█" * 60)
    print("  步骤 5：JSON 导出 (JSON Export)")
    print("█" * 60)

    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)
    export_json(G, out / "turing_kg.json")


# ============================================================
#  主入口
# ============================================================

def main() -> None:
    print("=" * 60)
    print("  图灵知识图谱 Demo")
    print("  Alan Turing Knowledge Graph Demo")
    print("  知识工程 作业1")
    print("=" * 60)

    step_ner()
    G = step_build_kg()
    step_query(G)
    step_visualize(G)
    step_export(G)

    print("\n" + "=" * 60)
    print("  ✓ 所有步骤执行完毕！")
    print("  输出文件位于 output/ 目录：")
    out = Path(__file__).parent / "output"
    for f in sorted(out.iterdir()):
        print(f"    • {f.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
