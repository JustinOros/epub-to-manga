import requests
import json
import uuid
import time
import os
import subprocess
import sys

COMFY_PORT = 8188
POLL_TIMEOUT = 300

MODELS = {
    "lineart": {
        "name": "Deliberate_v2.safetensors",
        "url": "https://huggingface.co/XpucT/Deliberate/resolve/main/Deliberate_v2.safetensors",
    },
    "manga": {
        "name": "Deliberate_v2.safetensors",
        "url": "https://huggingface.co/XpucT/Deliberate/resolve/main/Deliberate_v2.safetensors",
    },
}

DEFAULT_MODEL_URL = MODELS["manga"]["url"]
DEFAULT_MODEL_NAME = MODELS["manga"]["name"]

def base_url(host="127.0.0.1"):
    return f"http://{host}:{COMFY_PORT}"

def is_ready(host="127.0.0.1", timeout=3):
    try:
        requests.get(f"{base_url(host)}/system_stats", timeout=timeout)
        return True
    except Exception:
        return False

def find_model(comfy_path, name=None):
    model_dir = os.path.join(comfy_path, "models", "checkpoints")
    if not os.path.isdir(model_dir):
        return None
    if name:
        return name if os.path.exists(os.path.join(model_dir, name)) else None
    for f in os.listdir(model_dir):
        if f.endswith(".safetensors") or f.endswith(".ckpt"):
            return f
    return None

def download_model(comfy_path, style="manga"):
    model_info = MODELS.get(style, MODELS["manga"])
    model_name = model_info["name"]
    model_url = model_info["url"]
    style_label = "Anything V5 (anime/manga lineart)" if style == "lineart" else "Deliberate v2 (general purpose)"

    model_dir = os.path.join(comfy_path, "models", "checkpoints")
    os.makedirs(model_dir, exist_ok=True)
    dest = os.path.join(model_dir, model_name)

    if os.path.exists(dest):
        return model_name

    print(f"\n  Model for --style {style} not found: {model_name}")
    print(f"  Recommended model: {style_label}")
    print(f"  Source: {model_url}")
    confirm = input("\n  Download it now? (~2GB) [Y/n] ").strip().lower()
    if confirm in ("n", "no"):
        print("  Aborted.")
        sys.exit(0)

    print(f"\n  Downloading {model_name}...")

    bar_width = 35
    with requests.get(model_url, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total
                    filled = int(bar_width * pct)
                    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                    mb_done = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    print(f"\r  [{bar}] {mb_done:.0f}/{mb_total:.0f} MB  ", end="", flush=True)

    print(f"\r  Download complete: {dest}                              ")
    return model_name

def ensure_model_for_style(comfy_path, style="manga"):
    model_info = MODELS.get(style, MODELS["manga"])
    model_name = model_info["name"]
    existing = find_model(comfy_path, name=model_name)
    if existing:
        return existing
    return download_model(comfy_path, style=style)

def install_dependencies(comfy_path):
    req_file = os.path.join(comfy_path, "requirements.txt")
    stamp = os.path.join(comfy_path, ".deps_installed")
    if not os.path.exists(req_file):
        return
    if os.path.exists(stamp):
        req_mtime = os.path.getmtime(req_file)
        stamp_mtime = os.path.getmtime(stamp)
        if stamp_mtime >= req_mtime:
            return
    print("  Installing ComfyUI dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
        check=True,
    )
    open(stamp, "w").close()

def build_workflow(positive, negative, model_name, steps=20, width=768, height=1024, cfg=4.5):
    seed = int(time.time()) % 2**32
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler_ancestral",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model_name},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "manga", "images": ["8", 0]},
        },
    }

def generate_image(base_url_str, positive, negative, model_name, steps=20, width=768, height=1024, cfg=4.5):
    client_id = str(uuid.uuid4())
    workflow = build_workflow(positive, negative, model_name, steps, width, height, cfg)

    r = requests.post(f"{base_url_str}/prompt", json={"prompt": workflow, "client_id": client_id})
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(1)
        hist = requests.get(f"{base_url_str}/history/{prompt_id}").json()
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    img_info = node_output["images"][0]
                    img_r = requests.get(
                        f"{base_url_str}/view",
                        params={
                            "filename": img_info["filename"],
                            "subfolder": img_info.get("subfolder", ""),
                            "type": img_info["type"],
                        },
                    )
                    img_r.raise_for_status()
                    return img_r.content
            break

    raise RuntimeError(f"ComfyUI: no images returned for prompt_id {prompt_id} within {POLL_TIMEOUT}s")
