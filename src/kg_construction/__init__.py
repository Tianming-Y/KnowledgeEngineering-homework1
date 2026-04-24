"""知识图谱构建子包。

本子包负责把关系抽取阶段输出的 JSONL 三元组转换为 NetworkX 有向图，
并导出为 GraphML、GEXF、JSON 等可持久化格式。

输入：
- ``output/graphs/relation_triples*.jsonl``。
- 可选的 ``output/entities_all.jsonl``，用于补全节点属性。

输出：
- 图谱文件和统计信息，供可视化模块和外部图工具继续使用。
"""
