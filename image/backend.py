import os
import sys
from image.sd_launcher import read_config, write_config

def get_backend_type(sd_path):
    if not sd_path:
        return None
    if os.path.exists(os.path.join(sd_path, "webui.sh")):
        return "a1111"
    if os.path.exists(os.path.join(sd_path, "comfy_extras")) or "ComfyUI" in sd_path:
        return "comfyui"
    if "InvokeAI" in sd_path:
        return "invokeai"
    return "a1111"

def get_base_url(backend_type):
    if backend_type == "comfyui":
        return "http://127.0.0.1:8188"
    return "http://127.0.0.1:7860"

def is_ready(backend_type, base_url):
    if backend_type == "comfyui":
        from image.comfy_api import is_ready as comfy_ready
        return comfy_ready()
    from image.a1111_api import is_ready as a1111_ready
    return a1111_ready(base_url)

def ensure_model(backend_type, sd_path, style="manga"):
    if backend_type == "comfyui":
        from image import comfy_api
        model = comfy_api.ensure_model_for_style(sd_path, style=style)
        write_config("comfy-model", model)
        return model
    return None

def setup(sd_path):
    backend_type = get_backend_type(sd_path)
    write_config("sd-backend", backend_type)
    if backend_type == "comfyui":
        from image import comfy_api
        comfy_api.install_dependencies(sd_path)
    return backend_type

def _force_bw(img_bytes):
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(img_bytes)).convert("L").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_image(positive, negative, steps=20, width=768, height=1024, cfg=4.5, force_bw=True, style="manga"):
    config = read_config()
    sd_path = config.get("sd-path", "")
    backend_type = config.get("sd-backend") or get_backend_type(sd_path)
    base_url = get_base_url(backend_type)

    if backend_type == "comfyui":
        from image import comfy_api
        model = comfy_api.ensure_model_for_style(sd_path, style=style)
        write_config("comfy-model", model)
        if not model:
            print("\nError: no model found. Re-run to trigger model download.")
            sys.exit(1)
        result = comfy_api.generate_image(base_url, positive, negative, model, steps, width, height, cfg)
        return _force_bw(result) if force_bw else result

    from image import a1111_api
    result = a1111_api.generate_image(base_url, positive, negative, steps, width, height, cfg)
    return _force_bw(result) if force_bw else result
