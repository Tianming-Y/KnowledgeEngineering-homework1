import sys

sys.path.insert(0, ".")
try:
    import sentence_transformers as st

    print("__ST_OK__", st.__version__)
except Exception as e:
    print("__ST_ERROR__", repr(e))
