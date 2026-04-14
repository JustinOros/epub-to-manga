
import os
import subprocess
import time
import threading
import sys
import requests

_sd_process = None

CONFIG_FILE = os.path.expanduser("~/.epub-to-manga")

BACKENDS = [
    {
        "name": "AUTOMATIC1111 Stable Diffusion WebUI",
        "repo": "https://github.com/AUTOMATIC1111/stable-diffusion-webui",
        "dir": "stable-diffusion-webui",
        "type": "a1111",
        "launch": ["bash", "webui.sh", "--api", "--nowebui"],
        "ready_url": "http://127.0.0.1:7860/sdapi/v1/options",
    },
    {
        "name": "ComfyUI  (lighter, faster on Apple Silicon)",
        "repo": "https://github.com/comfyanonymous/ComfyUI",
        "dir": "ComfyUI",
        "type": "comfyui",
        "launch": [sys.executable, "main.py", "--listen"],
        "ready_url": "http://127.0.0.1:8188/system_stats",
    },
    {
        "name": "InvokeAI",
        "repo": "https://github.com/invoke-ai/InvokeAI",
        "dir": "InvokeAI",
        "type": "invokeai",
        "launch": ["invokeai-web"],
        "ready_url": "http://127.0.0.1:9090/api/v1/app/version",
    },
]

KNOWN_ERRORS = [
    {
        "markers": ["No module named 'pkg_resources'", "Couldn't install clip"],
        "message": "AUTOMATIC1111 is not compatible with Python {python_version}. A1111 requires Python 3.10.",
        "solutions": [
            {
                "label": "Install Python 3.10 via pyenv and relaunch A1111",
                "action": "fix_a1111_python",
            },
            {
                "label": "Switch to ComfyUI (better Apple Silicon support)",
                "action": "switch_backend",
                "backend_index": 1,
            },
        ],
    },
    {
        "markers": ["CUDA out of memory", "out of memory"],
        "message": "GPU ran out of memory.",
        "solutions": [
            {
                "label": "Re-run with a smaller image size (--size 256x384)",
                "action": "suggest_flag",
                "flag": "--size 256x384",
            },
        ],
    },
]

def read_config():
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    config[key.strip()] = val.strip()
    return config

def write_config(key, value):
    config = read_config()
    config[key] = value
    with open(CONFIG_FILE, "w") as f:
        for k, v in config.items():
            f.write(f"{k}={v}\n")

def get_backend_for_path(sd_path):
    if not sd_path:
        return BACKENDS[0]
    for b in BACKENDS:
        if b["dir"] in sd_path or os.path.exists(os.path.join(sd_path, b["dir"])):
            return b
        if b["type"] == "a1111" and os.path.exists(os.path.join(sd_path, "webui.sh")):
            return b
        if b["type"] == "comfyui" and os.path.exists(os.path.join(sd_path, "comfy_extras")):
            return b
    return BACKENDS[0]

def is_running(ready_url, timeout=3):
    try:
        requests.get(ready_url, timeout=timeout)
        return True
    except Exception:
        return False

def find_installed():
    home = os.path.expanduser("~")
    search_dirs = [home, os.path.join(home, "Downloads"), os.path.join(home, "Documents"), os.getcwd()]
    for backend in BACKENDS:
        for base in search_dirs:
            candidate = os.path.join(base, backend["dir"])
            if os.path.isdir(candidate):
                return candidate, backend
    return None, None

def get_python_version():
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

def handle_known_error(error_def, sd_path, backend):
    python_version = get_python_version()
    msg = error_def["message"].format(python_version=python_version)
    solutions = error_def["solutions"]

    print(f"\n\n  ⚠️  {msg}\n")
    print("  Solutions:\n")
    for i, s in enumerate(solutions, 1):
        print(f"    {i}) {s['label']}")
    print()

    while True:
        choice = input("  Choose a solution (or q to quit): ").strip().lower()
        if choice == "q":
            sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(solutions):
            solution = solutions[int(choice) - 1]
            break
        print(f"  Enter a number between 1 and {len(solutions)}")

    action = solution["action"]

    if action == "fix_a1111_python":
        print("\n  Installing pyenv and Python 3.10.14...")
        subprocess.run(["brew", "install", "pyenv"], check=False)
        subprocess.run(["pyenv", "install", "3.10.14"], check=False)
        pyenv_python = os.path.expanduser("~/.pyenv/versions/3.10.14/bin/python3")
        if not os.path.exists(pyenv_python):
            print("\n  Error: pyenv install failed. See https://github.com/pyenv/pyenv")
            sys.exit(1)
        env = os.environ.copy()
        env["PYTHON"] = pyenv_python
        print(f"\n  Relaunching A1111 with Python 3.10.14...")
        global _sd_process
        _sd_process = subprocess.Popen(
            ["bash", "webui.sh", "--api", "--nowebui"],
            cwd=sd_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        stream_and_wait(backend, sd_path)

    elif action == "switch_backend":
        new_backend = BACKENDS[solution["backend_index"]]
        dest = os.path.join(os.path.expanduser("~"), new_backend["dir"])
        if os.path.isdir(dest):
            print(f"\n  Found existing {new_backend['name']} at {dest} — using it.")
        else:
            confirm = input(f"\n  Install {new_backend['name']} to {dest}? [Y/n] ").strip().lower()
            if confirm in ("n", "no"):
                print("  Aborted.")
                sys.exit(0)
            print(f"\n  Cloning {new_backend['repo']}...")
            result = subprocess.run(["git", "clone", "--recursive", new_backend["repo"], dest], check=False)
            if result.returncode != 0:
                print("\n  Error: git clone failed.")
                sys.exit(1)
            print(f"\n  Installed to {dest}")
        write_config("sd-path", dest)
        write_config("sd-backend", new_backend["type"])
        print(f"  Re-run your original command — switching will take effect automatically.")
        sys.exit(0)

    elif action == "suggest_flag":
        print(f"\n  Re-run with: {solution['flag']}")
        sys.exit(0)

def stream_logs(proc, ready_event, error_detected, sd_path, backend):
    interesting = [
        "Loading", "Downloading", "Installing", "Running", "Creating",
        "Model loaded", "Starting", "Applying", "torch", "CUDA", "MPS",
        "checkpoint", "venv", "pip", "Startup", "listen",
    ]

    for raw in proc.stdout:
        if ready_event.is_set():
            break
        line = raw.decode("utf-8", errors="replace").rstrip()

        for err_def in KNOWN_ERRORS:
            if any(m in line for m in err_def["markers"]):
                ready_event.set()
                error_detected["def"] = err_def
                return

        if any(kw in line for kw in interesting):
            print(f"\r  > {line[:100]:<100}")
            print("  ", end="", flush=True)

def stream_and_wait(backend, sd_path):
    global _sd_process
    ready_event = threading.Event()
    error_detected = {}

    log_thread = threading.Thread(
        target=stream_logs,
        args=(_sd_process, ready_event, error_detected, sd_path, backend),
        daemon=True,
    )
    log_thread.start()

    start = time.time()
    while not ready_event.is_set():
        elapsed = int(time.time() - start)
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        print(f"\r  Waiting for API... {elapsed_str} elapsed  ", end="", flush=True)

        if is_running(backend["ready_url"]):
            ready_event.set()
            elapsed = int(time.time() - start)
            mins, secs = divmod(elapsed, 60)
            elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
            print(f"\r  Ready in {elapsed_str}!                              \n")
            return

        if _sd_process.poll() is not None and not ready_event.is_set():
            ready_event.set()
            break

        time.sleep(2)

    log_thread.join(timeout=2)

    if "def" in error_detected:
        handle_known_error(error_detected["def"], sd_path, backend)
    elif not is_running(backend["ready_url"]):
        print("\n\n  Error: SD process exited unexpectedly.")
        sys.exit(1)

def launch(sd_path, backend):
    global _sd_process
    print(f"\nStarting {backend['name']} from {sd_path}...")

    _sd_process = subprocess.Popen(
        backend["launch"],
        cwd=sd_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    stream_and_wait(backend, sd_path)

def prompt_install():
    print("\nNo Stable Diffusion backend found on your system.")
    print("\nAvailable backends to install:\n")
    for i, b in enumerate(BACKENDS, 1):
        print(f"  {i}) {b['name']}")
        print(f"     {b['repo']}")
    print()

    while True:
        choice = input("Enter number to install (or q to quit): ").strip().lower()
        if choice == "q":
            sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(BACKENDS):
            backend = BACKENDS[int(choice) - 1]
            break
        print(f"  Please enter a number between 1 and {len(BACKENDS)}")

    dest = os.path.join(os.path.expanduser("~"), backend["dir"])
    confirm = input(f"\nInstall {backend['name']} to {dest}? [Y/n] ").strip().lower()
    if confirm in ("n", "no"):
        print("Aborted.")
        sys.exit(0)

    if os.path.isdir(dest):
        print(f"\nFound existing {backend['name']} at {dest} — using it.")
    else:
        print(f"\nCloning {backend['repo']}...")
        result = subprocess.run(["git", "clone", "--recursive", backend["repo"], dest], check=False)
        if result.returncode != 0:
            print("\nError: git clone failed. Is git installed?")
            sys.exit(1)
        print(f"\nInstalled to {dest}")

    write_config("sd-path", dest)
    write_config("sd-backend", backend["type"])
    print(f"Saved to {CONFIG_FILE}")
    print(f"\nRe-run your original command — no --sd-path needed.")
    sys.exit(0)

def ensure_running(sd_url=None, sd_path=None, style="manga"):
    config = read_config()

    if not sd_path:
        sd_path = config.get("sd-path")

    backend = get_backend_for_path(sd_path)

    if is_running(backend["ready_url"]):
        return

    if sd_path and os.path.isdir(sd_path):
        from image import backend as backend_mod
        backend_mod.setup(sd_path)
        backend_mod.ensure_model(backend["type"], sd_path, style=style)
        launch(sd_path, backend)
        return

    installed_path, found_backend = find_installed()
    if installed_path:
        print(f"\nFound {found_backend['name']} at {installed_path}")
        write_config("sd-path", installed_path)
        write_config("sd-backend", found_backend["type"])
        print(f"Saved to {CONFIG_FILE}")
        from image import backend as backend_mod
        backend_mod.setup(installed_path)
        backend_mod.ensure_model(found_backend["type"], installed_path, style=style)
        launch(installed_path, found_backend)
        return

    prompt_install()

def shutdown():
    global _sd_process
    if _sd_process:
        _sd_process.terminate()
        _sd_process = None
