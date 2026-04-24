"""PyTorch 与 CUDA 环境快速诊断脚本。

本文件专门检查深度学习相关环境是否满足 REBEL 推理要求，输出 torch 版本、
CUDA 是否可用以及当前 GPU 名称，适合在安装显卡驱动或切换 Python 环境后单独验证。

使用方式：
- 直接执行 ``python scripts/check_torch.py``。

输入与输出：
- 不读取项目业务数据，也不生成文件。
- 输出为标准输出中的诊断信息，方便用户判断 REBEL 是否可以走 GPU 路径。

与其他文件的关系：
- 常作为 ``scripts/check_deps.py`` 的补充。
- 结果可直接影响 ``src/relation_extraction/rebel_extract.py`` 的运行性能和配置判断。
"""

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
