#!/usr/bin/env python3
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
