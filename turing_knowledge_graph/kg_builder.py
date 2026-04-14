"""
知识图谱构建模块 (Knowledge Graph Builder)
以 NetworkX 有向图为基础，定义图灵相关的实体节点与关系边，
并提供查询接口和 JSON 导出功能。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx


# ============================================================
#  实体类型颜色映射（供可视化模块使用）
# ============================================================
ENTITY_COLORS: Dict[str, str] = {
    "PERSON":       "#4C9BE8",   # 蓝色  - 人物
    "ORG":          "#F4A460",   # 沙棕色 - 组织
    "GPE":          "#90EE90",   # 浅绿色 - 地点
    "CONCEPT":      "#DA70D6",   # 兰花紫 - 概念
    "WORK":         "#FFD700",   # 金色  - 著作/系统
    "DEVICE":       "#FF6B6B",   # 珊瑚红 - 装置
    "EVENT":        "#20B2AA",   # 青绿色 - 事件
    "AWARD":        "#DEB887",   # 浅棕色 - 奖项
}

DEFAULT_COLOR = "#CCCCCC"


def build_turing_kg() -> nx.DiGraph:
    """
    构建图灵知识图谱并返回 NetworkX 有向图。

    节点属性:
        label (str)  — 显示名称
        type  (str)  — 实体类型
        desc  (str)  — 简短描述

    边属性:
        relation (str) — 关系类型（中英双语）
    """
    G = nx.DiGraph()

    # ----------------------------------------------------------
    #  节点定义：(node_id, {label, type, desc})
    # ----------------------------------------------------------
    nodes: List[Tuple[str, Dict[str, str]]] = [
        # 人物
        ("Alan_Turing",    {"label": "Alan Turing",    "type": "PERSON",  "desc": "英国数学家、计算机科学先驱 (1912–1954)"}),
        ("Alonzo_Church",  {"label": "Alonzo Church",  "type": "PERSON",  "desc": "美国数学家，λ演算创始人"}),
        ("John_von_Neumann",{"label": "John von Neumann","type": "PERSON","desc": "匈牙利裔美国数学家，冯·诺依曼架构提出者"}),
        ("Claude_Shannon", {"label": "Claude Shannon", "type": "PERSON",  "desc": "美国数学家，信息论创始人"}),
        ("Max_Newman",     {"label": "Max Newman",     "type": "PERSON",  "desc": "英国数学家，图灵的导师与同事"}),
        ("Gordon_Welchman",{"label": "Gordon Welchman","type": "PERSON",  "desc": "英国数学家，Bombe 协同设计者"}),
        ("Hugh_Alexander", {"label": "Hugh Alexander", "type": "PERSON",  "desc": "英国国际象棋冠军，布莱切利园密码学家"}),
        ("Christopher_Morcom",{"label": "Christopher Morcom","type":"PERSON","desc": "图灵的挚友，早年去世对其影响深远"}),

        # 组织机构
        ("Cambridge",      {"label": "University of Cambridge","type": "ORG","desc": "英国顶尖研究型大学"}),
        ("Princeton",      {"label": "Princeton University",   "type": "ORG","desc": "美国常青藤大学"}),
        ("Bletchley_Park", {"label": "Bletchley Park",         "type": "ORG","desc": "二战期间英国密码破译中心"}),
        ("GCCS",           {"label": "GC&CS",                  "type": "ORG","desc": "英国政府密码与电报学校"}),
        ("NPL",            {"label": "NPL",                    "type": "ORG","desc": "英国国家物理实验室"}),
        ("Univ_Manchester",{"label": "Univ. of Manchester",    "type": "ORG","desc": "英国研究型大学，Manchester Mark 1 发源地"}),
        ("Royal_Society",  {"label": "Royal Society",          "type": "ORG","desc": "英国皇家学会，世界最古老科学学会之一"}),
        ("ACM",            {"label": "ACM",                    "type": "ORG","desc": "美国计算机协会"}),

        # 地点
        ("London",         {"label": "London",    "type": "GPE", "desc": "英国首都，图灵出生地"}),
        ("Manchester",     {"label": "Manchester","type": "GPE", "desc": "英国大城市，图灵晚年工作地"}),
        ("Princeton_City", {"label": "Princeton", "type": "GPE", "desc": "美国新泽西州城市"}),

        # 核心概念
        ("Turing_Machine", {"label": "Turing Machine","type": "CONCEPT","desc": "理论计算模型，可模拟任何算法过程"}),
        ("Halting_Problem",{"label": "Halting Problem","type": "CONCEPT","desc": "图灵证明不可判定的经典问题"}),
        ("Computability",  {"label": "Computability Theory","type": "CONCEPT","desc": "研究哪些问题可被算法解决的理论"}),
        ("Turing_Test",    {"label": "Turing Test","type": "CONCEPT","desc": "判断机器是否表现出人类智能的测试"}),
        ("AI",             {"label": "Artificial Intelligence","type": "CONCEPT","desc": "使计算机展现智能行为的研究领域"}),
        ("Morphogenesis",  {"label": "Morphogenesis","type": "CONCEPT","desc": "生物形态发生的数学模型（反应-扩散）"}),
        ("Lambda_Calculus",{"label": "Lambda Calculus","type": "CONCEPT","desc": "Church 提出的形式化计算模型"}),
        ("Cryptanalysis",  {"label": "Cryptanalysis","type": "CONCEPT","desc": "密码分析学，研究破解密码的方法"}),

        # 著作 / 系统
        ("Paper_Computable",{"label": "On Computable Numbers","type": "WORK","desc": "1936年论文，引入图灵机概念"}),
        ("Paper_CMI",       {"label": "Computing Machinery and Intelligence","type": "WORK","desc": "1950年论文，提出图灵测试"}),
        ("Paper_Morpho",    {"label": "The Chemical Basis of Morphogenesis","type": "WORK","desc": "1952年论文，创立数学生物学分支"}),
        ("ACE_Computer",    {"label": "Automatic Computing Engine","type": "WORK","desc": "图灵在NPL设计的早期存储程序计算机"}),
        ("Manchester_Mark1",{"label": "Manchester Mark 1","type": "WORK","desc": "世界上最早的存储程序计算机之一"}),

        # 装置
        ("Enigma",{"label": "Enigma Machine","type": "DEVICE","desc": "德军在二战中使用的加密机器"}),
        ("Bombe",  {"label": "Bombe","type": "DEVICE","desc": "图灵等人设计的电机解密装置，用于破解 Enigma"}),

        # 事件
        ("WWII",  {"label": "World War II","type": "EVENT","desc": "1939–1945年全球规模战争"}),

        # 奖项
        ("OBE",          {"label": "OBE","type": "AWARD","desc": "大英帝国勋章，因二战贡献而授予"}),
        ("FRS",          {"label": "Fellow of Royal Society","type": "AWARD","desc": "英国皇家学会会士，1951年"}),
        ("ACM_Award",    {"label": "ACM Turing Award","type": "AWARD","desc": "计算机领域最高奖，以图灵命名"}),
        ("Royal_Pardon", {"label": "Royal Pardon","type": "AWARD","desc": "2013年英王室对图灵的追授赦免"}),
    ]

    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)

    # ----------------------------------------------------------
    #  边定义：(source, target, relation)
    # ----------------------------------------------------------
    edges: List[Tuple[str, str, str]] = [
        # 人物 - 出生地
        ("Alan_Turing",   "London",          "出生于 (born in)"),

        # 人物 - 求学
        ("Alan_Turing",   "Cambridge",       "就读于 (studied at)"),
        ("Alan_Turing",   "Princeton",       "获博士学位于 (PhD at)"),
        ("Alan_Turing",   "Alonzo_Church",   "师从 (supervised by)"),

        # 人物 - 工作
        ("Alan_Turing",   "Bletchley_Park",  "工作于 (worked at)"),
        ("Alan_Turing",   "GCCS",            "所属机构 (member of)"),
        ("Alan_Turing",   "NPL",             "工作于 (worked at)"),
        ("Alan_Turing",   "Univ_Manchester", "工作于 (worked at)"),

        # 人物 - 合作
        ("Alan_Turing",   "Max_Newman",       "合作者 (collaborated with)"),
        ("Alan_Turing",   "Gordon_Welchman",  "合作者 (collaborated with)"),
        ("Alan_Turing",   "Hugh_Alexander",   "合作者 (collaborated with)"),
        ("Alan_Turing",   "Christopher_Morcom","挚友 (close friend)"),

        # 人物 - 影响
        ("Alonzo_Church", "Alan_Turing",      "影响了 (influenced)"),
        ("Lambda_Calculus","Turing_Machine",  "等价于/启发了 (equivalent/inspired)"),
        ("Alan_Turing",   "John_von_Neumann", "影响了 (influenced)"),
        ("Alan_Turing",   "Claude_Shannon",   "影响了 (influenced)"),

        # 人物 - 提出概念/创作
        ("Alan_Turing",   "Turing_Machine",   "提出了 (proposed)"),
        ("Alan_Turing",   "Halting_Problem",  "证明了 (proved)"),
        ("Alan_Turing",   "Turing_Test",      "提出了 (proposed)"),
        ("Alan_Turing",   "Morphogenesis",    "创立了 (founded)"),
        ("Alan_Turing",   "Cryptanalysis",    "贡献于 (contributed to)"),

        # 人物 - 著作
        ("Alan_Turing",   "Paper_Computable", "发表了 (published)"),
        ("Alan_Turing",   "Paper_CMI",        "发表了 (published)"),
        ("Alan_Turing",   "Paper_Morpho",     "发表了 (published)"),
        ("Alan_Turing",   "ACE_Computer",     "设计了 (designed)"),

        # 论文 - 概念
        ("Paper_Computable", "Turing_Machine",  "引入了 (introduced)"),
        ("Paper_Computable", "Halting_Problem", "证明了 (proved)"),
        ("Paper_Computable", "Computability",   "奠定了 (laid foundation of)"),
        ("Paper_CMI",        "Turing_Test",     "提出了 (proposed)"),
        ("Paper_CMI",        "AI",              "奠定了 (laid foundation of)"),
        ("Paper_Morpho",     "Morphogenesis",   "描述了 (described)"),

        # 概念关系
        ("Turing_Machine",   "Computability",  "是基础 (foundation of)"),
        ("Turing_Test",      "AI",             "是评估标准 (metric for)"),

        # 二战 - Enigma - Bombe
        ("Alan_Turing",   "Bombe",            "设计了 (designed)"),
        ("Gordon_Welchman","Bombe",            "协同设计 (co-designed)"),
        ("Bombe",         "Enigma",            "用于破解 (used to break)"),
        ("WWII",          "Bletchley_Park",    "催生了 (led to establishment of)"),
        ("Alan_Turing",   "WWII",             "为...做出贡献 (contributed to)"),

        # 计算机
        ("Alan_Turing",   "Manchester_Mark1", "参与研发 (contributed to)"),
        ("ACE_Computer",  "Manchester_Mark1", "先于/启发了 (preceded/inspired)"),

        # 组织关系
        ("Bletchley_Park","GCCS",             "隶属于 (part of)"),
        ("Cambridge",     "Royal_Society",    "关联机构 (affiliated with)"),
        ("Alan_Turing",   "Royal_Society",    "当选会士 (elected FRS)"),

        # 奖项
        ("Alan_Turing",   "OBE",              "荣获 (awarded)"),
        ("Alan_Turing",   "FRS",              "当选 (elected)"),
        ("Alan_Turing",   "Royal_Pardon",     "获得 (received)"),
        ("ACM",           "ACM_Award",        "设立 (established)"),
        ("ACM_Award",     "Alan_Turing",      "以...命名 (named after)"),
    ]

    for src, tgt, rel in edges:
        G.add_edge(src, tgt, relation=rel)

    return G


# ============================================================
#  查询接口
# ============================================================

def get_neighbors(G: nx.DiGraph, node_id: str) -> Dict[str, Any]:
    """返回某节点的所有入边和出边邻居及关系。"""
    out_edges = [
        {"target": t, "relation": d["relation"]}
        for _, t, d in G.out_edges(node_id, data=True)
    ]
    in_edges = [
        {"source": s, "relation": d["relation"]}
        for s, _, d in G.in_edges(node_id, data=True)
    ]
    return {
        "node": node_id,
        "label": G.nodes[node_id].get("label", node_id),
        "type": G.nodes[node_id].get("type", "UNKNOWN"),
        "desc": G.nodes[node_id].get("desc", ""),
        "out_edges": out_edges,
        "in_edges": in_edges,
    }


def query_relation_path(
    G: nx.DiGraph, source: str, target: str
) -> Optional[List[str]]:
    """返回两个节点之间的最短路径（节点 ID 列表）。"""
    try:
        return nx.shortest_path(G, source=source, target=target)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def print_graph_stats(G: nx.DiGraph) -> None:
    """打印知识图谱统计信息。"""
    type_counts: Dict[str, int] = {}
    for _, attrs in G.nodes(data=True):
        t = attrs.get("type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1

    rel_counts: Dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        r = d.get("relation", "unknown")
        rel_counts[r] = rel_counts.get(r, 0) + 1

    print("\n" + "=" * 60)
    print("  知识图谱统计 (Knowledge Graph Statistics)")
    print("=" * 60)
    print(f"  节点总数: {G.number_of_nodes()}")
    print(f"  边总数:   {G.number_of_edges()}")
    print("\n  节点类型分布:")
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:<20} {cnt} 个")
    print("\n  关系类型数量:", len(rel_counts))
    print("=" * 60)


# ============================================================
#  JSON 导出
# ============================================================

def export_json(G: nx.DiGraph, output_path: Path) -> None:
    """将知识图谱导出为 JSON 格式（节点 + 边）。"""
    data = {
        "nodes": [
            {"id": n, **attrs} for n, attrs in G.nodes(data=True)
        ],
        "edges": [
            {"source": s, "target": t, "relation": d.get("relation", "")}
            for s, t, d in G.edges(data=True)
        ],
    }
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ 知识图谱已导出至 {output_path}")


# ---------- 主程序入口 ----------
if __name__ == "__main__":
    G = build_turing_kg()
    print_graph_stats(G)

    print("\n图灵节点邻居查询示例：")
    info = get_neighbors(G, "Alan_Turing")
    print(f"  出边数: {len(info['out_edges'])}, 入边数: {len(info['in_edges'])}")

    print("\nAlan_Turing → AI 最短路径：")
    path = query_relation_path(G, "Alan_Turing", "AI")
    if path:
        print("  " + " → ".join(path))

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    export_json(G, out_dir / "turing_kg.json")
