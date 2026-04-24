"""KG-Turing Web 应用。

该服务复用项目现有图谱文件与脚本，向前端提供：
- 图谱概览与动态图数据
- 关键词查询、节点详情和局部子图
- 受控的脚本运行接口
- 生成结果与可视化文件的下载接口
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

try:  # pragma: no cover - optional dependency
    from flask import (
        Flask,
        jsonify,
        render_template,
        request,
        send_file,
        send_from_directory,
    )
except Exception:  # pragma: no cover - optional dependency
    Flask = None
    jsonify = None
    render_template = None
    request = None
    send_file = None
    send_from_directory = None

from src.query import GraphQueryService


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GRAPH_PATH = os.path.join(PROJECT_ROOT, "output", "graphs", "knowledge_graph.json")
TEMPLATE_ROOT = os.path.join(PROJECT_ROOT, "src", "webapp", "templates")
STATIC_ROOT = os.path.join(PROJECT_ROOT, "src", "webapp", "static")


SCRIPT_CATALOG = {
    "check_deps": {
        "label": "检查依赖",
        "description": "检查关键 Python 依赖、torch、CUDA 和 spaCy 模型。",
        "command": ["scripts/check_deps.py"],
    },
    "check_torch": {
        "label": "检查 Torch",
        "description": "检查 PyTorch 与 CUDA 环境。",
        "command": ["scripts/check_torch.py"],
    },
    "run_extraction": {
        "label": "数据采集",
        "description": "运行 Wikipedia 抓取与文本清洗流程。",
        "command": ["src/data_extraction/run_extraction.py"],
    },
    "run_ner": {
        "label": "实体识别与消歧",
        "description": "批量处理 data/processed，输出 entities_all.jsonl。",
        "command": ["src/ner/batch_process.py", "--link", "True"],
    },
    "run_pipeline": {
        "label": "关系抽取流水线",
        "description": "运行关系抽取、图谱构建和可视化的一键脚本。",
        "command": ["scripts/run_pipeline.py"],
    },
    "build_graph": {
        "label": "重建图谱",
        "description": "从最终三元组重新构建 knowledge_graph.* 文件。",
        "command": [
            "src/kg_construction/build_graph.py",
            "--triples",
            "output/graphs/relation_triples_aliased.jsonl",
            "--entities",
            "output/entities_all.jsonl",
            "--output-dir",
            "output/graphs",
        ],
    },
    "visualize_graph": {
        "label": "重建可视化",
        "description": "从 knowledge_graph.json 重新生成 PNG 和 HTML 可视化。",
        "command": [
            "src/visualization/visualize.py",
            "--graph",
            "output/graphs/knowledge_graph.json",
            "--output-dir",
            "output/visualizations",
            "--ego-center",
            "Alan Turing",
            "--ego-radius",
            "2",
        ],
    },
}


DOWNLOAD_CATALOG = {
    "knowledge_graph_json": {
        "label": "图谱 JSON",
        "path": os.path.join(PROJECT_ROOT, "output", "graphs", "knowledge_graph.json"),
    },
    "knowledge_graph_graphml": {
        "label": "GraphML",
        "path": os.path.join(
            PROJECT_ROOT, "output", "graphs", "knowledge_graph.graphml"
        ),
    },
    "knowledge_graph_gexf": {
        "label": "GEXF",
        "path": os.path.join(PROJECT_ROOT, "output", "graphs", "knowledge_graph.gexf"),
    },
    "full_graph_png": {
        "label": "静态全图 PNG",
        "path": os.path.join(
            PROJECT_ROOT, "output", "visualizations", "full_graph.png"
        ),
    },
    "full_graph_html": {
        "label": "交互全图 HTML",
        "path": os.path.join(
            PROJECT_ROOT, "output", "visualizations", "full_graph.html"
        ),
    },
    "ego_alan_turing_png": {
        "label": "Alan Turing Ego PNG",
        "path": os.path.join(
            PROJECT_ROOT, "output", "visualizations", "ego_Alan_Turing.png"
        ),
    },
    "ego_alan_turing_html": {
        "label": "Alan Turing Ego HTML",
        "path": os.path.join(
            PROJECT_ROOT, "output", "visualizations", "ego_Alan_Turing.html"
        ),
    },
}


@dataclass
class ScriptTask:
    task_id: str
    script_id: str
    label: str
    command: list[str]
    status: str = "queued"
    output: str = ""
    exit_code: int | None = None
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "script_id": self.script_id,
            "label": self.label,
            "command": " ".join(self.command),
            "status": self.status,
            "output": self.output,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class ScriptTaskManager:
    """只允许执行预定义脚本的后台任务管理器。"""

    def __init__(self, project_root: str, query_service: GraphQueryService):
        self.project_root = project_root
        self.query_service = query_service
        self._tasks: dict[str, ScriptTask] = {}
        self._lock = threading.Lock()

    def list_scripts(self) -> list[dict[str, Any]]:
        rows = []
        for script_id, spec in SCRIPT_CATALOG.items():
            rows.append(
                {
                    "id": script_id,
                    "label": spec["label"],
                    "description": spec["description"],
                    "command_preview": " ".join([sys.executable, *spec["command"]]),
                }
            )
        return rows

    def start(self, script_id: str) -> dict[str, Any]:
        if script_id not in SCRIPT_CATALOG:
            raise KeyError(script_id)

        spec = SCRIPT_CATALOG[script_id]
        task = ScriptTask(
            task_id=uuid.uuid4().hex,
            script_id=script_id,
            label=spec["label"],
            command=[sys.executable, *spec["command"]],
        )
        with self._lock:
            self._tasks[task.task_id] = task

        thread = threading.Thread(
            target=self._run_task, args=(task.task_id,), daemon=True
        )
        thread.start()
        return task.to_dict()

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "running"
            task.started_at = time.time()

        try:
            result = subprocess.run(
                task.command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            output = result.stdout or ""
            if result.stderr:
                output = f"{output}\n[stderr]\n{result.stderr}".strip()

            with self._lock:
                task.output = output.strip()
                task.exit_code = result.returncode
                task.status = "completed" if result.returncode == 0 else "failed"
                task.finished_at = time.time()

            if result.returncode == 0 and os.path.exists(self.query_service.graph_path):
                try:
                    self.query_service.reload()
                except Exception:
                    pass
        except Exception as exc:  # pragma: no cover - defensive runtime path
            with self._lock:
                task.output = f"任务执行异常: {type(exc).__name__}: {exc}"
                task.status = "failed"
                task.exit_code = -1
                task.finished_at = time.time()


class WebAppController:
    """为 Flask 和标准库 HTTP 服务共用的控制层。"""

    def __init__(self, graph_path: str, project_root: str):
        self.graph_path = graph_path
        self.project_root = project_root
        self.query_service = GraphQueryService(graph_path=graph_path)
        self.task_manager = ScriptTaskManager(project_root, self.query_service)

    def health(self) -> tuple[dict[str, Any], int]:
        return {"status": "ok", "graph_exists": os.path.exists(self.graph_path)}, 200

    def graph_summary(self) -> tuple[dict[str, Any], int]:
        return self.query_service.get_summary(), 200

    def full_graph(self) -> tuple[dict[str, Any], int]:
        return self.query_service.get_full_graph(), 200

    def reload_graph(self) -> tuple[dict[str, Any], int]:
        return self.query_service.reload(), 200

    def query_nodes(
        self, keyword: str, limit: int, radius: int
    ) -> tuple[dict[str, Any], int]:
        return self.query_service.query(keyword, limit=limit, radius=radius), 200

    def node_details(self, node_id: str, radius: int) -> tuple[dict[str, Any], int]:
        try:
            payload = {
                "details": self.query_service.get_node_details(node_id),
                "subgraph": self.query_service.get_subgraph(node_id, radius=radius),
            }
            return payload, 200
        except KeyError:
            return {"error": f"节点不存在: {node_id}"}, 404

    def scripts(self) -> tuple[dict[str, Any], int]:
        return {"scripts": self.task_manager.list_scripts()}, 200

    def run_script(self, script_id: str) -> tuple[dict[str, Any], int]:
        try:
            task = self.task_manager.start(script_id)
            return task, 202
        except KeyError:
            return {"error": f"不支持的脚本: {script_id}"}, 400

    def get_task(self, task_id: str) -> tuple[dict[str, Any], int]:
        task = self.task_manager.get(task_id)
        if task is None:
            return {"error": f"任务不存在: {task_id}"}, 404
        return task, 200

    def downloads(self) -> tuple[dict[str, Any], int]:
        items = []
        for download_id, spec in DOWNLOAD_CATALOG.items():
            items.append(
                {
                    "id": download_id,
                    "label": spec["label"],
                    "available": os.path.exists(spec["path"]),
                }
            )
        return {"downloads": items}, 200

    def get_download_path(
        self, download_id: str
    ) -> tuple[str | None, dict[str, Any] | None, int]:
        spec = DOWNLOAD_CATALOG.get(download_id)
        if spec is None:
            return None, {"error": f"下载项不存在: {download_id}"}, 404
        if not os.path.exists(spec["path"]):
            return None, {"error": f"文件不存在: {spec['path']}"}, 404
        return spec["path"], None, 200


def create_app(
    graph_path: str = GRAPH_PATH,
    project_root: str = PROJECT_ROOT,
) -> Flask:
    if Flask is None:
        raise RuntimeError("Flask 未安装，无法创建 Flask 应用。")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    controller = WebAppController(graph_path=graph_path, project_root=project_root)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/vendor/vis/<path:filename>")
    def vendor_vis(filename: str):
        return send_from_directory(
            os.path.join(project_root, "lib", "vis-9.1.2"), filename
        )

    @app.get("/vendor/tom-select/<path:filename>")
    def vendor_tom_select(filename: str):
        return send_from_directory(
            os.path.join(project_root, "lib", "tom-select"), filename
        )

    @app.get("/api/health")
    def health():
        payload, status = controller.health()
        return jsonify(payload), status

    @app.get("/api/graph/summary")
    def graph_summary():
        payload, status = controller.graph_summary()
        return jsonify(payload), status

    @app.get("/api/graph/full")
    def full_graph():
        payload, status = controller.full_graph()
        return jsonify(payload), status

    @app.post("/api/graph/reload")
    def reload_graph():
        payload, status = controller.reload_graph()
        return jsonify(payload), status

    @app.get("/api/query")
    def query_nodes():
        keyword = request.args.get("keyword", "")
        limit = int(request.args.get("limit", 10))
        radius = int(request.args.get("radius", 1))
        payload, status = controller.query_nodes(keyword, limit=limit, radius=radius)
        return jsonify(payload), status

    @app.get("/api/node/<path:node_id>")
    def node_details(node_id: str):
        radius = int(request.args.get("radius", 1))
        payload, status = controller.node_details(node_id, radius=radius)
        return jsonify(payload), status

    @app.get("/api/scripts")
    def scripts():
        payload, status = controller.scripts()
        return jsonify(payload), status

    @app.post("/api/scripts/run")
    def run_script():
        body = request.get_json(silent=True) or {}
        script_id = body.get("script_id", "")
        payload, status = controller.run_script(script_id)
        return jsonify(payload), status

    @app.get("/api/tasks/<task_id>")
    def get_task(task_id: str):
        payload, status = controller.get_task(task_id)
        return jsonify(payload), status

    @app.get("/api/downloads")
    def downloads():
        payload, status = controller.downloads()
        return jsonify(payload), status

    @app.get("/api/download/<download_id>")
    def download(download_id: str):
        path, error_payload, status = controller.get_download_path(download_id)
        if error_payload is not None:
            return jsonify(error_payload), status
        return send_file(path, as_attachment=True)

    return app


def run_simple_server(
    graph_path: str = GRAPH_PATH,
    project_root: str = PROJECT_ROOT,
    host: str = "127.0.0.1",
    port: int = 5000,
) -> None:
    """在缺少 Flask 时使用标准库 HTTP 服务运行前端。"""

    controller = WebAppController(graph_path=graph_path, project_root=project_root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                self._serve_file(
                    os.path.join(TEMPLATE_ROOT, "index.html"),
                    "text/html; charset=utf-8",
                )
                return
            if path.startswith("/static/"):
                rel = path.removeprefix("/static/")
                self._serve_file(os.path.join(STATIC_ROOT, rel))
                return
            if path.startswith("/vendor/vis/"):
                rel = path.removeprefix("/vendor/vis/")
                self._serve_file(os.path.join(project_root, "lib", "vis-9.1.2", rel))
                return
            if path.startswith("/vendor/tom-select/"):
                rel = path.removeprefix("/vendor/tom-select/")
                self._serve_file(os.path.join(project_root, "lib", "tom-select", rel))
                return
            if path == "/api/health":
                self._json_response(*controller.health())
                return
            if path == "/api/graph/summary":
                self._json_response(*controller.graph_summary())
                return
            if path == "/api/graph/full":
                self._json_response(*controller.full_graph())
                return
            if path == "/api/query":
                keyword = query.get("keyword", [""])[0]
                limit = int(query.get("limit", [10])[0])
                radius = int(query.get("radius", [1])[0])
                self._json_response(
                    *controller.query_nodes(keyword, limit=limit, radius=radius)
                )
                return
            if path.startswith("/api/node/"):
                node_id = unquote(path.removeprefix("/api/node/"))
                radius = int(query.get("radius", [1])[0])
                self._json_response(*controller.node_details(node_id, radius=radius))
                return
            if path == "/api/scripts":
                self._json_response(*controller.scripts())
                return
            if path.startswith("/api/tasks/"):
                task_id = unquote(path.removeprefix("/api/tasks/"))
                self._json_response(*controller.get_task(task_id))
                return
            if path == "/api/downloads":
                self._json_response(*controller.downloads())
                return
            if path.startswith("/api/download/"):
                download_id = unquote(path.removeprefix("/api/download/"))
                file_path, error_payload, status = controller.get_download_path(
                    download_id
                )
                if error_payload is not None:
                    self._json_response(error_payload, status)
                    return
                self._serve_file(file_path, as_attachment=True)
                return

            self._json_response({"error": f"未知路径: {path}"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                payload = {}

            if parsed.path == "/api/graph/reload":
                self._json_response(*controller.reload_graph())
                return
            if parsed.path == "/api/scripts/run":
                script_id = payload.get("script_id", "")
                self._json_response(*controller.run_script(script_id))
                return

            self._json_response({"error": f"未知路径: {parsed.path}"}, 404)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _json_response(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_file(
            self,
            file_path: str,
            content_type: str | None = None,
            as_attachment: bool = False,
        ) -> None:
            if not os.path.exists(file_path):
                self._json_response({"error": f"文件不存在: {file_path}"}, 404)
                return

            guessed_type, _ = mimetypes.guess_type(file_path)
            ctype = content_type or guessed_type or "application/octet-stream"
            with open(file_path, "rb") as handle:
                body = handle.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if as_attachment:
                filename = os.path.basename(file_path)
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[Web] 使用标准库 HTTP 服务启动: http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
