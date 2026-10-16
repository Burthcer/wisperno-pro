"""
Wisperno - Offline Desktop Dictation & Contextual Transformation Daemon.
"""

import os
import sys

# Make the CUDA runtime DLLs (cuBLAS, cudart) findable before any engine loads - see src/cuda_runtime.py.
from src.cuda_runtime import add_cuda_dll_dirs

add_cuda_dll_dirs()

__version__ = "1.3.0"
