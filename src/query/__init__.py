"""图谱查询子包。

本子包负责在 ``knowledge_graph.json`` 之上提供关键词搜索、节点详情查询、
邻居关系浏览和局部子图提取等能力，服务于命令行查询和 Web 前端。

主要入口：
- ``GraphQueryService``：图谱加载、检索、节点详情和子图生成。
"""

from .graph_query import GraphQueryService

__all__ = ["GraphQueryService"]
