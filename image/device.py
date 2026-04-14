
import torch
import platform

def detect_device():
    if torch.cuda.is_available():
        return "cuda"
    if platform.system() == "Darwin":
        try:
            if torch.backends.mps.is_available():
                return "mps"
        except:
            pass
    return "cpu"
