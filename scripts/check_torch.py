import sys

try:
    import torch

    print("TORCH", getattr(torch, "__version__", None))
    try:
        cuda_avail = torch.cuda.is_available()
    except Exception as _e:
        print("CUDA_CHECK_ERROR", type(_e).__name__, _e)
        cuda_avail = False
    print("CUDA_AVAILABLE", cuda_avail)
    if cuda_avail:
        try:
            print("CUDA_DEVICE_NAME", torch.cuda.get_device_name(0))
        except Exception as e:
            print("CUDA_DEVICE_ERROR", type(e).__name__, e)
except Exception as e:
    print("TORCH_IMPORT_ERROR", type(e).__name__, str(e)[:200])
