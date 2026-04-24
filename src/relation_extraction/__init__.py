"""关系抽取子包。

本文件标记 ``src.relation_extraction`` 为关系抽取阶段的命令行脚本集合。
该子包当前没有统一的门面函数，而是按步骤拆分为 Infobox 抽取、候选对生成、
银标构建、REBEL 抽取、三元组合并和别名标准化等独立脚本。

输入：
- 上游 ``data/processed`` 与 ``output/entities_all.jsonl`` 的文档和实体结果。

输出：
- ``data/relation`` 和 ``output/graphs`` 下的多份中间 JSONL/最终三元组文件。

与其他文件的关系：
- ``scripts/run_pipeline.py`` 会按固定顺序调用本子包中的多个脚本。
- ``src/kg_construction/build_graph.py`` 直接消费这里生成的最终三元组文件。
"""
