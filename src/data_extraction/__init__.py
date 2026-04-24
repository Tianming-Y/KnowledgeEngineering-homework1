"""数据采集子包。

本文件导出数据采集阶段的核心公共接口，包括页面爬取、页面解析和文本清洗。
它主要服务于 ``src/data_extraction/run_extraction.py``，也便于其他脚本按需复用。

输入：
- 来自 ``config/settings.yaml`` 的 crawler 与路径配置。

输出：
- 导出 ``WikiCrawler``、``WikiParser``、``DataCleaner`` 三个类，分别对应
	``data/raw`` 生成和 ``data/processed`` 清洗产出。

与其他文件的关系：
- 是数据采集模块的导入门面。
- 下游 NER 与关系抽取阶段都直接消费本子包生成的 JSON 文档。
"""
from .wiki_crawler import WikiCrawler
from .wiki_parser import WikiParser
from .data_cleaner import DataCleaner

__all__ = ["WikiCrawler", "WikiParser", "DataCleaner"]
