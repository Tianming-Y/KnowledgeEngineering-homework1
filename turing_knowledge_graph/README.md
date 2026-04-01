# 图灵知识图谱 Demo
# Alan Turing Knowledge Graph Demo

## 项目简介

本项目是一个以**艾伦·图灵（Alan Turing）** 为主题的知识图谱演示程序，重点展示以下知识工程核心技术：

| 技术模块 | 说明 |
|---|---|
| **实体识别（NER）** | 融合 spaCy 神经网络模型与领域规则词典，从文本中自动识别人物、组织、地点、概念、著作、装置等多类实体 |
| **知识体系建构** | 以结构化三元组 `(实体, 关系, 实体)` 构建有向知识图谱，覆盖图灵的学术生涯、人际关系、核心贡献及历史影响 |
| **图谱查询** | 提供邻居查询、最短路径查询等接口，支持知识推理与关联分析 |
| **图谱可视化** | 利用 NetworkX + Matplotlib 生成彩色节点图，按实体类型着色，直观展示知识结构 |
| **结构化导出** | 将图谱导出为 JSON 格式，便于与其他系统对接 |

---

## 项目结构

```
turing_knowledge_graph/
├── main.py           # 主程序入口，依次执行 NER→构建→查询→可视化→导出
├── ner_demo.py       # 实体识别模块（spaCy + 规则融合）
├── kg_builder.py     # 知识图谱构建模块（NetworkX DiGraph）
├── visualizer.py     # 可视化模块（matplotlib）
├── data/
│   └── turing_text.txt   # 英文图灵简介文本，作为 NER 输入
├── output/           # 运行后自动生成
│   ├── turing_kg_full.png        # 完整图谱可视化
│   ├── turing_ego.png            # 以图灵为中心的 1 跳 Ego 子图
│   ├── turing_concept_work.png   # 概念与著作关系子图
│   └── turing_kg.json            # JSON 格式导出
└── requirements.txt
```

---

## 环境安装

```bash
pip install -r turing_knowledge_graph/requirements.txt
# 下载 spaCy 英文模型（可选，若不安装则自动降级为规则匹配）
python -m spacy download en_core_web_sm
```

---

## 运行方式

```bash
cd turing_knowledge_graph
python main.py
```

也可单独运行各模块：

```bash
# 仅运行实体识别
python ner_demo.py

# 仅构建并导出图谱
python kg_builder.py

# 仅生成可视化图片
python visualizer.py
```

---

## 知识图谱概览

### 实体类型（Entity Types）

| 类型 | 颜色 | 示例节点 |
|---|---|---|
| PERSON（人物） | 蓝色 | Alan Turing, Alonzo Church, Max Newman |
| ORG（组织） | 沙棕色 | Cambridge, Bletchley Park, ACM |
| GPE（地点） | 浅绿色 | London, Manchester, Princeton |
| CONCEPT（概念） | 兰花紫 | Turing Machine, Turing Test, AI |
| WORK（著作/系统） | 金色 | On Computable Numbers, ACE, Manchester Mark 1 |
| DEVICE（装置） | 珊瑚红 | Enigma, Bombe |
| EVENT（事件） | 青绿色 | World War II |
| AWARD（奖项） | 浅棕色 | OBE, FRS, ACM Turing Award |

### 关系类型（Relation Types，部分）

- 就读于 / 工作于 / 师从
- 提出了 / 发表了 / 设计了 / 证明了
- 合作者 / 影响了 / 等价于
- 贡献于 / 奠定了 / 当选

### 图谱规模

- **节点**：39 个
- **边**：48 条
- **覆盖维度**：学术成就、人际关系、历史事件、荣誉奖项

---

## 技术说明

### 实体识别策略

```
输入文本
    │
    ├─► spaCy en_core_web_sm → {PERSON, ORG, GPE, DATE, ...}
    │
    └─► 领域规则词典匹配   → {CONCEPT, WORK, DEVICE}
             │
             ▼
         融合去重 → 最终实体列表
```

领域词典覆盖 spaCy 难以识别的计算机科学专有名词（如"Turing Machine"、"Halting Problem"），两路结果融合时规则结果优先，避免重叠。

### 知识图谱构建

采用 **NetworkX `DiGraph`（有向图）** 存储三元组，每个节点携带 `label / type / desc` 属性，每条边携带 `relation` 属性（中英双语标注）。

### 可视化

- **完整图谱**：Spring Layout，节点按实体类型着色，边附短中文标签
- **Ego 子图**：以指定节点为中心，展示 1 跳邻域，中心节点放大显示
- **类型子图**：只展示 CONCEPT + WORK 类型节点及其关系，使用 Circular Layout

---

## 示例输出

运行后在 `output/` 目录生成：

- `turing_kg_full.png` — 完整知识图谱
- `turing_ego.png` — 图灵 Ego 子图（直接关联节点）
- `turing_concept_work.png` — 概念与著作关系
- `turing_kg.json` — 结构化 JSON 数据
