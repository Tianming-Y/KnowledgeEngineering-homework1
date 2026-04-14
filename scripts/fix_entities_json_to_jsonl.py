"""Fix entities_all.jsonl when it's written as a JSON array.
Backs up original to output/entities_all.jsonl.bak and writes JSONL lines.
"""

import json
import shutil
import sys
from pathlib import Path

p = Path("output/entities_all.jsonl")
if not p.exists():
    print("file not found:", p)
    sys.exit(1)

bak = p.with_suffix(p.suffix + ".bak")
shutil.copyfile(p, bak)
print("backup ->", bak)

with p.open("r", encoding="utf-8") as fh:
    text = fh.read()

text_stripped = text.lstrip()
if not text_stripped.startswith("["):
    print("file does not start with '['; assumed already JSONL. No change.")
    sys.exit(0)

# parse as JSON array
data = json.loads(text)
with p.open("w", encoding="utf-8") as fh:
    for obj in data:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
print("converted", len(data), "items to JSONL")
