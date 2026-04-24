"""KG-Turing 源码包。

本文件标记 ``src`` 为项目顶层 Python 包，统一承载数据采集、实体识别与消歧、
关系抽取、知识图谱构建和可视化等业务模块。

使用方式：
- 运行脚本时通常直接执行 ``scripts`` 或 ``src`` 下的 CLI 文件。
- 开发时可通过 ``src.<module>`` 的方式导入具体能力。

与其他文件的关系：
- ``scripts/run_pipeline.py``、``src/data_extraction/run_extraction.py`` 等入口脚本
	会基于这里的包结构导入各子模块。
- 各子包之间通过 JSON/JSONL 文件与函数调用共同串联端到端流程。
"""
