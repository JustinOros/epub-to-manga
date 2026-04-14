
import os

def make_output_name(path, override=None):
    if override:
        return override
    base = os.path.splitext(os.path.basename(path))[0]
    return f"manga-{base}.epub"
