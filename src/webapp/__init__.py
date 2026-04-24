"""项目 Web 前端子包。

本子包提供用于课程演示的轻量 Web 应用，整合图谱动态展示、关键词查询、
可视化结果下载和白名单脚本执行。

主要入口：
- ``create_app``：构造 Flask 应用；若环境缺少 Flask 会抛出异常。
- ``run_simple_server``：基于标准库 ``http.server`` 的无依赖回退实现。
"""

from .app import create_app, run_simple_server

__all__ = ["create_app", "run_simple_server"]
