"""图谱可视化子包。

本子包负责把图谱 JSON 渲染为静态图片与交互式网页，并支持围绕核心实体
生成 Ego 子图。它处于完整流水线的最后一环，直接面向结果展示与分析。

输入：
- ``src/kg_construction/build_graph.py`` 生成的 ``knowledge_graph.json``。

输出：
- ``output/visualizations`` 下的 PNG 与 HTML 文件。
"""
