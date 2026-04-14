import json
import logging
from ai.llm_client import call_llm

log = logging.getLogger(__name__)

PROMPT_TEMPLATE = (
    'Analyze the scene below and return a JSON object with exactly these keys:\n'
    '"characters": array of proper name strings only, no pronouns\n'
    '"dialogue": array of objects with "speaker" (proper name or "?") and "line" (spoken words only) for every quoted line\n'
    '"visual_scene": string, one sentence describing the physical action to illustrate\n'
    '"mood": string, exactly one of: neutral happy sad tense angry mysterious romantic action\n'
    '"setting": string, brief location name\n\n'
    'Scene:\n{scene}'
)

JUNK_SPEAKERS = {
    "i", "me", "he", "she", "they", "we", "you", "it",
    "him", "her", "them", "his", "hers", "their",
    "narrator", "voice", "unknown", "someone", "anyone",
}

def _empty(scene):
    return {
        "characters": [],
        "dialogue": [],
        "visual_scene": scene[:120].strip(),
        "mood": "neutral",
        "setting": "",
    }

def _clean_dialogue(raw):
    if not isinstance(raw, list):
        return []
    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        line = entry.get("line") or entry.get("text") or entry.get("speech") or ""
        speaker = entry.get("speaker") or entry.get("name") or "?"
        line = str(line).strip().strip('"')
        speaker = str(speaker).strip()
        if not line:
            continue
        if len(speaker.split()) > 3 or speaker.endswith(('.', ',')):
            speaker = "?"
        if speaker.lower() in JUNK_SPEAKERS:
            speaker = "?"
        cleaned.append({"speaker": speaker, "line": line})
    return cleaned

def _extract(result, scene):
    if not isinstance(result, dict):
        log.warning("LLM returned non-dict JSON: %s", str(result)[:200])
        return _empty(scene)
    out = _empty(scene)
    out["characters"] = result.get("characters") or []
    out["dialogue"] = _clean_dialogue(result.get("dialogue", []))
    out["visual_scene"] = result.get("visual_scene") or scene[:120].strip()
    out["mood"] = result.get("mood") or "neutral"
    out["setting"] = result.get("setting") or ""
    for key in ("scene", "response", "output", "result"):
        if key in result and isinstance(result[key], dict):
            log.warning("LLM wrapped response under key '%s', unwrapping", key)
            return _extract(result[key], scene)
    return out

def parse_scene(scene, timeout=90):
    prompt = PROMPT_TEMPLATE.format(scene=scene)
    raw = call_llm(prompt, timeout=timeout)
    if not raw:
        log.warning("Empty LLM response")
        return _empty(scene)
    try:
        result = json.loads(raw)
        return _extract(result, scene)
    except json.JSONDecodeError as e:
        log.warning("JSON decode failed: %s — raw: %s", e, raw[:300])
        return _empty(scene)

def parse_in_batches(scenes, batch_size=1, progress_cb=None, timeout=90):
    results = []
    for i, scene in enumerate(scenes):
        result = parse_scene(scene, timeout=timeout)
        results.append(result)
        if progress_cb:
            progress_cb(i + 1, len(scenes))
    return results
