import sys
import argparse
import logging
import time
import os
import json
import requests
import concurrent.futures
from core.epub_reader import read_epub, read_epub_metadata
from core.scene_splitter import split_scenes
from manga.panel_layout import group_into_pages
from manga.prompt_builder import build_page_prompt, get_cfg
from manga.speech_bubbles import add_speech_bubbles
from ai.scene_parser import parse_scene
from ai.character_memory import update as update_character, load as load_character_db, dump as dump_character_db, add_hint
from image.backend import generate_image
from image.sd_launcher import ensure_running, shutdown
import atexit
from export.epub_builder import build_epub
from utils.naming import make_output_name
import config

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

def fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"

def progress_bar(current, total, label="", eta_str="", width=35):
    pct = current / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    eta = f"  ETA {eta_str}" if eta_str else ""
    print(f"\r  [{bar}] {current}/{total} {label}{eta}  ", end="", flush=True)

def parse_args():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Convert an EPUB novel into a manga-style EPUB using LLM scene parsing and Stable Diffusion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python3 main.py book.epub
  python3 main.py book.epub output.epub
  python3 main.py book.epub --layout tiny --model mistral
  python3 main.py book.epub --sd-url http://192.168.1.10:7860 --steps 30 --size 512x768
  python3 main.py book.epub --dry-run

layout modes:
  normal   3 scenes per page  (default)
  tiny     1 scene per page (more pages, more detail per image)

requirements:
  Ollama running at OLLAMA_URL (default: http://localhost:11434)
  Stable Diffusion WebUI running at SD_API_URL (default: http://127.0.0.1:7860)
  Both URLs can be overridden via flags or by editing config.py
        """
    )

    parser.add_argument("input", help="Path to input .epub file")
    parser.add_argument("output", nargs="?", help="Path for output .epub (default: manga-<input>.epub)")
    parser.add_argument("--layout", choices=["normal", "tiny"], default="normal",
        help="Page layout mode: normal=3 scenes/page, tiny=1 scene/page (default: normal)")
    parser.add_argument("--model", default=config.OLLAMA_MODEL, metavar="MODEL",
        help=f"Ollama model to use for scene parsing (default: {config.OLLAMA_MODEL})")
    parser.add_argument("--ollama-url", default=config.OLLAMA_URL, metavar="URL",
        help=f"Ollama API base URL (default: {config.OLLAMA_URL})")
    parser.add_argument("--sd-url", default=config.SD_API_URL, metavar="URL",
        help=f"Stable Diffusion WebUI API URL (default: {config.SD_API_URL})")
    parser.add_argument("--sd-path", default=None, metavar="PATH",
        help="Path to stable-diffusion-webui folder; if SD is not running, auto-starts it")
    parser.add_argument("--steps", type=int, default=20, metavar="N",
        help="Diffusion steps per image (default: 20, higher=better quality but slower)")
    parser.add_argument("--style", choices=["lineart", "manga"], default="lineart",
        help="Image style: lineart=simple clean outlines (default), manga=detailed screentone")
    parser.add_argument("--size", default="768x1024", metavar="WxH",
        help="Image dimensions in pixels (default: 768x1024)")
    parser.add_argument("--workers", type=int, default=2, metavar="N",
        help="Parallel image generation workers (default: 2)")
    parser.add_argument("--hint", action="append", metavar="NAME:DESC",
        help="Character description hint e.g. 'Rocky:alien who resembles a rock spider'. Can be used multiple times.")
    parser.add_argument("--jpeg-quality", type=int, default=85, metavar="N",
        help="JPEG quality for epub images 1-95 (default: 85, lower=smaller file)")
    parser.add_argument("--dry-run", nargs="?", const=3, type=int, metavar="N",
        help="Show N prompts without generating images (default: 3)")
    parser.add_argument("--verbose", "-v", action="store_true",
        help="Show debug logging")

    return parser.parse_args()

def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config.OLLAMA_MODEL = args.model
    config.OLLAMA_URL = args.ollama_url
    from image.sd_launcher import write_config as _wc
    _wc("llm-model", args.model)
    config.SD_API_URL = args.sd_url

    atexit.register(shutdown)
    ensure_running(args.sd_url, args.sd_path, style=args.style)

    try:
        width, height = (int(x) for x in args.size.split("x"))
    except ValueError:
        print(f"Error: --size must be in WxH format, e.g. 768x1024")
        sys.exit(1)

    if not os.path.isfile(args.input):
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    output = args.output or make_output_name(args.input)
    output_dir = os.path.splitext(output)[0] + "_pages"
    os.makedirs(output_dir, exist_ok=True)

    total_start = time.time()

    print(f"\nepub-to-manga")
    print(f"  input:  {args.input}")
    print(f"  output: {output}")
    print(f"  layout: {args.layout}  |  model: {args.model}  |  steps: {args.steps}  |  size: {width}x{height}  |  style: {args.style}  |  workers: {args.workers}")

    cache_file = make_output_name(args.input).replace(".epub", ".cache.json")

    print(f"\nReading & splitting epub...")
    source_title, source_author = read_epub_metadata(args.input)
    chapters = read_epub(args.input)
    scenes = split_scenes(chapters)
    print(f"  {len(scenes)} scenes found across {len(chapters)} chapters")

    dry_run_n = args.dry_run if args.dry_run is not None else None
    needed = dry_run_n if dry_run_n is not None else len(scenes)

    cached_scenes = []
    cached_chars = {}
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache_data = json.load(f)
            cached_scenes = cache_data.get("parsed_scenes", [])
            cached_chars = cache_data.get("character_db", {})

    load_character_db(cached_chars)

    if args.hint:
        for hint in args.hint:
            if ":" in hint:
                name, _, desc = hint.partition(":")
                add_hint(name.strip(), desc.strip())
                print(f"  Character hint: {name.strip()} = {desc.strip()}")

    if len(cached_scenes) >= needed:
        print(f"  Loaded {len(cached_scenes)} scenes from cache ({cache_file})")
        parsed_scenes = cached_scenes
    else:
        if cached_scenes:
            print(f"  Resuming parse — {len(cached_scenes)}/{needed} scenes cached")

        remaining_scenes = scenes[len(cached_scenes):needed]

        print(f"\nParsing scenes with {args.model} ({needed} total)")
        progress_bar(len(cached_scenes), needed)
        run_start = time.time()

        new_parsed = []
        scene_times = []

        def on_scene_done(batch_idx, batch_len):
            pass

        for idx, scene in enumerate(remaining_scenes):
            t0 = time.time()
            result = parse_scene(scene, timeout=90)
            elapsed_scene = time.time() - t0
            new_parsed.append(result)
            scene_times.append(elapsed_scene)
            if len(scene_times) > 10:
                scene_times.pop(0)

            for char in result.get("characters", []):
                if char and char.strip():
                    update_character(char.strip(), "")

            combined = cached_scenes + new_parsed
            with open(cache_file, "w") as f:
                json.dump({"parsed_scenes": combined, "character_db": dump_character_db()}, f)

            done = len(cached_scenes) + len(new_parsed)
            avg = sum(scene_times) / len(scene_times)
            remaining_count = needed - done
            eta = fmt_time(avg * remaining_count) if remaining_count > 0 else fmt_time(time.time() - run_start)
            progress_bar(done, needed, eta_str=eta)

        print()
        parsed_scenes = cached_scenes + new_parsed
        print(f"  Saved to {cache_file}")

    for ps in parsed_scenes:
        for char in ps.get("characters", []):
            if char and char.strip():
                update_character(char.strip(), "")

    pages = group_into_pages(parsed_scenes, mode=args.layout)
    print(f"  {len(pages)} pages ({args.layout} layout)")

    if args.dry_run is not None:
        n = args.dry_run
        print(f"\nDry run — first {n} prompts:")
        for i, page in enumerate(pages[:n]):
            positive, negative = build_page_prompt(page, style=args.style)
            print(f"\n--- Page {i+1} ---\nPositive: {positive}\nNegative: {negative}")
        return


    from image.sd_launcher import read_config as _rc
    _sd_cfg = _rc()
    _sd_path = _sd_cfg.get("sd-path", "")
    _backend = _sd_cfg.get("sd-backend", "comfyui")
    _port = "8188" if _backend == "comfyui" else "7860"
    if _backend == "comfyui":
        from image import comfy_api
        _model = comfy_api.ensure_model_for_style(_sd_path, style=args.style)
        from image.sd_launcher import write_config as _wc2
        _wc2("comfy-model", _model)

    total = len(pages)
    already_done = [
        os.path.join(output_dir, f"page_{i}.png")
        for i in range(total)
        if os.path.exists(os.path.join(output_dir, f"page_{i}.png"))
    ]
    resumed = len(already_done)

    print(f"\nGenerating images...  (http://127.0.0.1:{_port})")
    print(f"  {total} pages  |  ~{args.steps} steps each  |  {width}x{height}  |  {args.workers} workers")
    if resumed:
        print(f"  Resuming — {resumed}/{total} pages already done, skipping...")

    images = [None] * total
    for i in range(total):
        img_path = os.path.join(output_dir, f"page_{i}.png")
        if os.path.exists(img_path):
            images[i] = img_path

    progress_bar(resumed, total)
    img_start = time.time()
    times = []
    completed = resumed
    lock = __import__("threading").Lock()

    def gen_page(args_tuple):
        i, page = args_tuple
        img_path = os.path.join(output_dir, f"page_{i}.png")
        if os.path.exists(img_path):
            return i, img_path, None

        positive, negative = build_page_prompt(page, style=args.style)
        t0 = time.time()
        try:
            img_bytes = generate_image(
                positive, negative,
                steps=args.steps, width=width, height=height,
                cfg=get_cfg(args.style),
                force_bw=(args.style == "lineart"),
                style=args.style
            )
            elapsed = time.time() - t0

            with open(img_path, "wb") as f:
                f.write(img_bytes)

            dialogue = []
            if isinstance(page, list):
                for scene in page:
                    if isinstance(scene, dict):
                        dialogue.extend(scene.get("dialogue", []))
            if dialogue:
                add_speech_bubbles(img_path, dialogue)

            return i, img_path, elapsed
        except (requests.RequestException, KeyError, IndexError, RuntimeError) as e:
            return i, None, str(e)

    pending = [(i, page) for i, page in enumerate(pages) if images[i] is None]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(gen_page, item): item[0] for item in pending}
        for future in concurrent.futures.as_completed(futures):
            i, img_path, result = future.result()
            with lock:
                if img_path:
                    images[i] = img_path
                    if isinstance(result, float):
                        times.append(result)
                        if len(times) > 8:
                            times.pop(0)
                else:
                    print(f"\n  [!] Page {i} failed: {result}")
                completed += 1
                avg = sum(times) / len(times) if times else 0
                remaining_count = total - completed
                eta = fmt_time(avg * remaining_count / args.workers) if avg and remaining_count else ""
                progress_bar(completed, total, eta_str=eta)

    print()

    final_images = [img for img in images if img]

    if not final_images:
        print(f"\nError: no images generated. Is the SD API running at {args.sd_url}?")
        sys.exit(1)

    print(f"\nBuilding epub...")
    result = build_epub(final_images, output, title=source_title or "Manga Book", author="Manga", jpeg_quality=args.jpeg_quality)

    total_elapsed = time.time() - total_start
    print(f"  Done in {fmt_time(total_elapsed)}: {result}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped. Progress saved - re-run to resume.")
