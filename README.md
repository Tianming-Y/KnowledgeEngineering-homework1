# 图灵知识图谱 — Turing Knowledge Graph

> 知识工程课程作业：以艾伦·图灵（Alan Turing）为核心，从网络采集数据并构建领域知识图谱。

---

## 一、项目简介

本项目旨在围绕"计算机科学之父"**艾伦·图灵**，端到端地完成知识图谱的构建流程，覆盖以下核心环节：

| 模块               | 说明                                                                         |
| ------------------ | ---------------------------------------------------------------------------- |
| **数据采集**       | 从维基百科（Wikipedia）自动爬取图灵及其关联页面的结构化 / 非结构化信息       |
| **实体识别与消歧** | 基于 `spaCy` 预训练 NER 模型识别多类型实体，并通过 Wikidata 实体链接完成消歧 |
| **关系抽取**       | 从文本中抽取实体间的语义关系，形成三元组                                     |
| **知识图谱构建**   | 将三元组存储为有向图结构，支持增量更新与持久化                               |
| **可视化**         | 生成多视角的图谱可视化图片及交互式页面                                       |
| **图谱查询**       | 提供邻居查询、路径查询等接口，支持基础知识推理                               |



---

## 二、项目结构

```
KG-Turing/
├── README.md                        # 项目说明文档（本文件）
├── requirements.txt                 # Python 依赖清单
├── config/
│   └── settings.yaml                # 全局配置（爬取范围、模型参数等）
│
├── src/                             # 源代码主目录
│   ├── __init__.py
│   │
│   ├── data_extraction/             #   模块 1：数据采集
│   │   ├── __init__.py
│   │   ├── wiki_crawler.py          #    Wikipedia 页面爬取（多跳 BFS）
│   │   ├── wiki_parser.py           #    HTML / Infobox / 段落解析
│   │   ├── data_cleaner.py          #    文本清洗与去噪
│   │   └── run_extraction.py        #    数据采集全流程运行脚本
│   │
│   ├── ner/                         #   模块 2：实体识别与消歧
│   │   ├── __init__.py
│   │   ├── ner_pipeline.py          #    NER 主流程（使用 spaCy）
│   │   ├── spacy_ner.py             #    spaCy 预训练 / 微调 NER
│   │   ├── entity_linker.py         #    实体消歧与 Wikidata 链接
│   │
│   ├── relation_extraction/         #   模块 3：关系抽取（待完善）
│   │   ├── __init__.py
│   │   └── ...
│   │
│   ├── kg_construction/             #   模块 4：知识图谱构建与存储（待完善）
│   │   ├── __init__.py
│   │   └── ...
│   │
│   ├── visualization/               #   模块 5：图谱可视化（待完善）
│   │   ├── __init__.py
│   │   └── ...
│   │
│   └── query/                       #   模块 6：图谱查询（待完善）
│       ├── __init__.py
│       └── ...
│
├── data/
│   ├── raw/                         # 爬取的原始数据（HTML / JSON）
│   └── processed/                   # 清洗后的结构化文本
│
├── output/                          # 运行输出
│   ├── entities/                    #    NER 识别结果
│   ├── graphs/                      #    图谱数据文件
│   └── visualizations/              #    可视化图片
│
└── tests/                           # 单元测试
    ├── test_crawler.py
    ├── test_ner.py
    └── ...
```

---

## 三、技术方案

### 3.1 数据采集模块（Data Extraction）

#### 3.1.1 目标

从英文维基百科出发，以 **Alan Turing** 页面为种子，按广度优先（BFS）策略爬取图灵本人及其关联实体（人物、机构、著作、事件等）的页面，提取 **非结构化文本** 与 **半结构化数据**。

#### 3.1.2 技术选型

| 组件          | 技术                         | 说明                                                                    |
| ------------- | ---------------------------- | ----------------------------------------------------------------------- |
| HTTP 请求     | `requests`                   | 稳定的 HTTP 客户端，配合 `User-Agent` 和速率限制遵守 Wikipedia 爬虫协议 |
| HTML 解析     | `BeautifulSoup4`             | 解析 wiki 页面 DOM，提取正文段落、Infobox、分类等                       |
| Wikipedia API | `wikipedia-api`（Python 库） | 通过 MediaWiki API 获取页面摘要、链接列表、分类等结构化数据             |
| 数据存储      | JSON 文件                    | 每个页面保存为一个 JSON 文件，包含标题、摘要、正文、Infobox、出链等字段 |

#### 3.1.3 爬取流程

```
种子页面 "Alan Turing"
        │
        ▼
   ┌──────────────────────────┐
   │  wiki_crawler.py (BFS)   │
   │  ① 获取当前页面 HTML/API  │
   │  ② 提取页面内出链         │
   │  ③ 按相关性过滤出链       │
   │  ④ 入队，重复至 max_depth │
   └──────────────────────────┘
        │
        ▼
   ┌──────────────────────────┐
   │  wiki_parser.py          │
   │  ① 解析正文段落文本       │
   │  ② 提取 Infobox 键值对   │
   │  ③ 提取分类 (Categories)  │
   │  ④ 提取内部链接锚文本     │
   └──────────────────────────┘
        │
        ▼
   ┌──────────────────────────┐
   │  data_cleaner.py         │
   │  ① 去除引用标记 [1][2]   │
   │  ② 去除 HTML 残留标签    │
   │  ③ Unicode 规范化         │
   │  ④ 分句并保存             │
   └──────────────────────────┘
        │
        ▼
   data/raw/  →  data/processed/
```

#### 3.1.4 关键设计

- **多跳 BFS 爬取**：`max_depth` 默认设为 2（即图灵 → 直接关联页面 → 二级关联页面），通过 `settings.yaml` 可配置。
- **相关性过滤**：仅保留与计算机科学 / 图灵相关的出链页面，过滤策略包括：
  - 排除"消歧义"、"文件:"、"模板:"等 Wikipedia 系统页面；
  - 基于种子关键词列表（Turing, computation, cryptography, AI, Bletchley Park 等）进行标题过滤；
  - 对超出关键词范围的链接可通过分类标签 (Category) 进行二次筛选。
- **请求速率限制**：遵循 Wikipedia `robots.txt`，每次请求间隔 ≥ 1 秒，设置合理的 `User-Agent`。
- **增量爬取**：已爬取页面记录在 `data/raw/` 中，再次运行时跳过已存在页面，支持断点续爬。
- **Infobox 提取**：从 Infobox 表格中提取键值对（如出生日期、国籍、母校、领域等），作为实体属性的重要来源。

#### 3.1.5 输出格式

每个页面对应一个 JSON 文件 `data/raw/{page_title}.json`：

```json
{
  "title": "Alan Turing",
  "url": "https://en.wikipedia.org/wiki/Alan_Turing",
  "summary": "Alan Mathison Turing was an English mathematician...",
  "sections": [
    {
      "heading": "Early life and education",
      "text": "Turing was born on 23 June 1912..."
    }
  ],
  "infobox": {
    "Born": "23 June 1912, Maida Vale, London",
    "Alma mater": "King's College, Cambridge; Princeton University",
    "Fields": "Mathematics, Computer science, Cryptanalysis"
  },
  "categories": ["British computer scientists", "Bletchley Park people"],
  "outlinks": ["Alonzo Church", "Bletchley Park", "Enigma machine"]
}
```

#### 3.1.6 数据采集结果概况

以 `max_depth=2`、`max_pages=80` 运行后，实际采集数据如下：

| 指标         | 数值                                         |
| ------------ | -------------------------------------------- |
| 爬取页面数   | 80                                           |
| 爬取层级分布 | depth 0: 1 页, depth 1: 78 页, depth 2: 1 页 |
| 总章节数     | 961                                          |
| 总句子数     | 11,570                                       |
| 总出链数     | 27,728                                       |
| 清洗后数据量 | 4.3 MB                                       |

覆盖页面示例：Alan Turing、Turing Machine、Turing Test、Enigma machine、Bombe、Bletchley Park、Church–Turing thesis、Halting problem、Artificial intelligence、University of Cambridge、Princeton University 等。

---

### 3.2 实体识别与消歧模块（NER & Entity Disambiguation）

#### 3.2.1 目标

从采集到的文本中自动识别实体（人物、地点、组织、概念、著作、装置等），并将同一现实世界实体的不同提及（mention）映射到唯一标识，消除歧义。

#### 3.2.2 技术选型

| 组件     | 技术                                | 说明                                                                 |
| -------- | ----------------------------------- | -------------------------------------------------------------------- |
| 基础 NER | `spaCy`                             | Transformer / CNN 预训练模型，识别 PERSON、ORG、GPE、DATE 等通用实体 |
| 实体消歧 | `spaCy EntityLinker` + Wikidata API | 将候选实体链接至 Wikidata QID，实现跨文档统一标识                    |
| 指代消解 | `coreferee` 或 `spaCy` 实验性组件   | 将代词 (he/his/it) 还原为对应实体，提高下游召回率                    |

#### 3.2.3 实体消歧策略

1. **候选实体生成**：对每个识别出的 mention，调用 Wikidata Search API (`wbsearchentities`) 获取 Top-K 候选 QID。
2. **上下文相似度排序**：将 mention 的上下文窗口文本与各候选 QID 的 Wikidata 描述 (description) 计算余弦相似度（使用 `sentence-transformers` 或 TF-IDF），选取得分最高者。
3. **Infobox 属性辅助**：若 mention 来自 Infobox 字段（如 `Alma mater: King's College, Cambridge`），利用字段名语义直接约束候选类型。
4. **一致性约束**：同一文档中相同表面形式的 mention 映射到同一 QID。

#### 3.2.4 实体类型体系

| 类型        | 标签      | 示例                                                     |
| ----------- | --------- | -------------------------------------------------------- |
| 人物        | `PERSON`  | Alan Turing, Alonzo Church, Max Newman                   |
| 组织 / 机构 | `ORG`     | University of Cambridge, Bletchley Park, ACM             |
| 地点        | `GPE`     | London, Manchester, Princeton                            |
| 概念 / 理论 | `CONCEPT` | Turing Machine, Halting Problem, Artificial Intelligence |
| 著作 / 系统 | `WORK`    | *On Computable Numbers*, ACE, Manchester Mark 1          |
| 装置        | `DEVICE`  | Enigma, Bombe                                            |
| 事件        | `EVENT`   | World War II                                             |
| 奖项 / 荣誉 | `AWARD`   | OBE, FRS, ACM Turing Award                               |
| 日期        | `DATE`    | 23 June 1912                                             |

#### 3.2.5 输出格式

```json
[
  {
    "mention": "Alan Turing",
    "type": "PERSON",
    "start": 0,
    "end": 11,
    "wikidata_qid": "Q7251",
    "confidence": 0.98,
    "source": "spacy"
  },
  {
    "mention": "Turing Machine",
    "type": "CONCEPT",
    "start": 156,
    "end": 170,
    "wikidata_qid": "Q163310",
    "confidence": 1.0,
    "source": "rule"
  }
]
```

---

### 3.3 关系抽取（Relation Extraction）— *待完善*

计划从文本中抽取实体间的语义关系，形成 `(头实体, 关系, 尾实体)` 三元组。初步考虑：
- **基于依存句法的规则模板**：利用 spaCy 依存树提取常见句式（如 "X was born in Y"、"X proposed Y"）。
- **预训练关系抽取模型**：如基于 BERT 的关系分类器，对候选实体对进行关系预测。
- **Wikidata 远程监督**：利用 Wikidata 已有三元组作为弱标注，自动构造训练数据。

具体技术方案将在课程关系抽取章节后确定。

---

### 3.4 知识图谱构建与存储（KG Construction）— *待完善*

计划使用 **NetworkX** 在内存中构建有向知识图谱，后续可迁移至图数据库（如 Neo4j）。
- 节点属性：`label`、`type`、`wikidata_qid`、`description`。
- 边属性：`relation`、`confidence`、`source_sentence`。
- 支持从三元组 JSON 文件批量加载、增量合并、冲突检测。

---

### 3.5 可视化（Visualization）— *待完善*

- **静态可视化**：NetworkX + Matplotlib，按实体类型着色，输出 PNG 图片。
- **交互式可视化**：计划引入 `pyvis` 或 `D3.js`，支持节点拖拽、过滤、搜索。
- **子图视图**：Ego 子图（以某节点为中心）、类型子图（仅展示特定类型节点）。

---

### 3.6 图谱查询（Query）— *待完善*

- 邻居查询：给定实体，返回其直接关联的实体与关系。
- 路径查询：查找两实体之间的最短路径。
- 类型查询：按实体类型或关系类型筛选子图。
- 后续可对接 SPARQL 或 Cypher 查询语言。

---

## 四、环境要求

- **Python** 3.10
- **Conda** 环境名：`KG-Turing`

```bash
# 创建并激活环境
conda create -n KG-Turing python=3.10 -y
conda activate KG-Turing

# 安装依赖
pip install -r requirements.txt

# 下载 spaCy 英文模型
python -m spacy download en_core_web_sm
# （可选）下载 Transformer 模型以获得更好的 NER 效果
# python -m spacy download en_core_web_trf
```

---

## 五、主要依赖

| 包名                            | 用途                     |
| ------------------------------- | ------------------------ |
| `requests`                      | HTTP 请求                |
| `beautifulsoup4`                | HTML 解析                |
| `wikipedia-api`                 | Wikipedia 结构化数据获取 |
| `spacy`                         | NER、依存解析、实体链接  |
| `networkx`                      | 图结构构建与算法         |
| `matplotlib`                    | 静态图谱可视化           |
| `pyyaml`                        | 配置文件解析             |
| `sentence-transformers`（可选） | 实体消歧上下文相似度计算 |

---

## 六、开发进度

| 阶段    | 模块           | 状态     |
| ------- | -------------- | -------- |
| Phase 1 | 数据采集       | ✅ 已完成 |
| Phase 1 | 实体识别与消歧 | 🔲 进行中 |
| Phase 2 | 关系抽取       | ⬜ 待开始 |
| Phase 3 | 知识图谱构建   | ⬜ 待开始 |
| Phase 4 | 可视化 & 查询  | ⬜ 待开始 |

---

## 七、参考资料

- [Alan Turing - Wikipedia](https://en.wikipedia.org/wiki/Alan_Turing)
- [Wikidata - Alan Turing (Q7251)](https://www.wikidata.org/wiki/Q7251)
- [spaCy Documentation](https://spacy.io/)
- [NetworkX Documentation](https://networkx.org/)
- [Wikipedia API (MediaWiki)](https://www.mediawiki.org/wiki/API:Main_page)
