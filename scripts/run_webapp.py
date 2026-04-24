"""启动 KG-Turing Web 前端。

若环境中已安装 Flask，则优先启动 Flask 服务；否则自动退回到标准库
``http.server`` 实现，仍可提供图谱动态展示、关键词查询、产物下载和
白名单脚本执行界面。

默认访问地址：
- http://127.0.0.1:5000
"""

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.webapp import create_app, run_simple_server


def main() -> None:
    try:
        app = create_app()
    except RuntimeError:
        run_simple_server(host="127.0.0.1", port=5000)
        return

    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
