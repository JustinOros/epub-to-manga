import requests
import logging
import time
import json
from config import OLLAMA_URL, OLLAMA_MODEL

log = logging.getLogger(__name__)

def call_llm(prompt, timeout=90):
    deadline = time.time() + timeout
    try:
        with requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": True, "format": "json"},
            stream=True,
            timeout=30,
        ) as r:
            r.raise_for_status()
            chunks = []
            for line in r.iter_lines():
                if time.time() > deadline:
                    log.warning("LLM call exceeded wall-clock timeout of %ds", timeout)
                    break
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    chunks.append(data.get("response", ""))
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
            return "".join(chunks)
    except requests.RequestException as e:
        log.error("LLM call failed: %s", e)
        return ""
