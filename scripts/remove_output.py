import os

p = "output/entities_all.jsonl"
if os.path.exists(p):
    os.remove(p)
    print("Removed", p)
else:
    print("Not found", p)
