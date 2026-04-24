#!/usr/bin/env python3
"""项目依赖与运行环境自检脚本。

本文件用于在正式运行 NER、REBEL、图谱构建和 Web 前端之前，快速检查当前
Python 环境中关键依赖是否已经安装，并补充输出 PyTorch、CUDA 和 spaCy 模型状态。

使用方式：
- 直接执行 ``python scripts/check_deps.py``。
- 常用于新环境搭建完成后，或执行 ``scripts/run_pipeline.py``、``scripts/run_webapp.py``
  之前做预检查。
"""

from __future__ import annotations

import importlib
import sys


PACKAGE_SPECS = [
    ("spacy", "spacy", False),
    ("networkx", "networkx", False),
    ("yaml", "pyyaml", False),
    ("tqdm", "tqdm", False),
    ("transformers", "transformers", False),
    ("torch", "torch", False),
    ("sentence_transformers", "sentence-transformers", False),
    ("requests", "requests", False),
    ("bs4", "beautifulsoup4", False),
    ("lxml", "lxml", False),
    ("pyvis", "pyvis", False),
    ("flask", "flask", True),
    ("pytest", "pytest", True),
]


def check_package(module_name: str) -> str:
    try:
        importlib.import_module(module_name)
        return "OK"
    except Exception as exc:
        return f"FAIL: {exc.__class__.__name__}: {str(exc)[:200]}"


def main() -> None:
    for module_name, display_name, optional in PACKAGE_SPECS:
        status = check_package(module_name)
        prefix = f"{display_name} (optional)" if optional else display_name
        print(f"{prefix}: {status}")

    print("\nPython:", sys.version)

    try:
        import torch

        print("torch version:", torch.__version__)
        try:
            print("CUDA available:", torch.cuda.is_available())
            if torch.cuda.is_available():
                try:
                    print("CUDA device name:", torch.cuda.get_device_name(0))
                except Exception:
                    pass
        except Exception as exc:
            print("CUDA check failed:", exc)
    except Exception:
        print("torch not installed")

    try:
        import spacy

        try:
            spacy.load("en_core_web_sm")
            print("spacy_model_en_core_web_sm: OK")
        except Exception as exc:
            print("spacy_model_en_core_web_sm: FAIL:", repr(exc)[:200])
    except Exception:
        print("spacy not installed")

    print("\nDone")


if __name__ == "__main__":
    main()
