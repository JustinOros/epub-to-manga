
import requests
import base64

def generate_image(base_url, positive, negative, steps=20, width=768, height=1024, cfg=4.5):
    r = requests.post(f"{base_url}/sdapi/v1/txt2img", json={
        "prompt": positive,
        "negative_prompt": negative,
        "steps": steps,
        "width": width,
        "height": height,
        "cfg_scale": cfg,
    })
    r.raise_for_status()
    return base64.b64decode(r.json()["images"][0])

def is_ready(base_url, timeout=3):
    try:
        requests.get(f"{base_url}/sdapi/v1/options", timeout=timeout)
        return True
    except Exception:
        return False
