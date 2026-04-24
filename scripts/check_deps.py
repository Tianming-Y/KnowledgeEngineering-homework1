#!/usr/bin/env python3
"""项目依赖与运行环境自检脚本。

本文件用于在正式运行爬虫、NER、REBEL 和图谱构建流程之前，快速检查当前
Python 环境中关键依赖是否已经安装，并补充输出 PyTorch、CUDA 和 spaCy 模型状态。

使用方式：
- 直接执行 ``python scripts/check_deps.py``。
- 常用于新环境搭建完成后，或执行 ``scripts/run_pipeline.py`` 之前做预检查。

输入与输出：
- 不接收命令行参数，也不读写项目数据文件。
- 输出为终端中的依赖检查结果，包含包级 OK/FAIL、Python 版本、torch 版本、
    CUDA 可用性和 ``en_core_web_sm`` 模型是否可加载。

与其他文件的关系：
- 是诊断脚本，不参与主流水线产物生成。
- 与 ``scripts/check_torch.py`` 形成互补：本文件面向全量依赖检查，后者聚焦 GPU。
"""
import sys
import traceback

pkgs = [
    "spacy",
    "networkx",
    "yaml",
    "tqdm",
    "transformers",
    "torch",
    "sentence_transformers",
    "requests",
    "bs4",
]
results = {}
for p in pkgs:
    try:
        __import__(p)
        results[p] = "OK"
    except Exception as e:
        results[p] = f"FAIL: {e.__class__.__name__}: {str(e)[:200]}"

for k, v in results.items():
    print(f"{k}: {v}")

print("\nPython:", sys.version)
# torch cuda
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
    except Exception as e:
        print("CUDA check failed:", e)
except Exception:
    print("torch not installed")

# spaCy model check
try:
    import spacy

    try:
        spacy.load("en_core_web_sm")
        print("spacy_model_en_core_web_sm: OK")
    except Exception as e:
        print("spacy_model_en_core_web_sm: FAIL:", repr(e)[:200])
except Exception:
    print("spacy not installed")

print("\nDone")
