import re
from ai.character_memory import build_consistency_tokens

STYLES = {
    "lineart": {
        "positive": (
            "anime illustration, manga style, black and white, monochrome, "
            "clean ink linework, expressive characters, dynamic composition, "
            "professional manga art, single scene, full image"
        ),
        "negative": (
            "color, colorful, coloured, vibrant, saturated, "
            "multiple panels, panel borders, panel grid, split panels, "
            "collage, triptych, diptych, "
            "realistic, photorealistic, photograph, 3d render, "
            "ugly, blurry, watermark, text, signature, lowres, "
            "bad anatomy, deformed, extra limbs"
        ),
        "cfg": 7.0,
    },
    "manga": {
        "positive": (
            "single full-page manga illustration, full-bleed scene, "
            "black and white ink, screentone shading, "
            "expressive faces, detailed backgrounds, "
            "professional manga art, one continuous scene"
        ),
        "negative": (
            "multiple panels, panel borders, panel grid, comic layout, split panels, "
            "panel dividers, gutters, multi-panel page, page layout, comic book grid, "
            "collage, triptych, diptych, "
            "lowres, bad anatomy, blurry, watermark, text, ugly, deformed, "
            "color, coloured, western comic style"
        ),
        "cfg": 7.5,
    },
}

MOOD_MAP = {
    "tense": "tense dramatic scene, characters look worried or scared",
    "sad": "sad melancholy scene, characters look downcast",
    "happy": "happy cheerful scene, characters smiling",
    "angry": "angry confrontational scene, characters look furious",
    "mysterious": "mysterious eerie scene, shadowy atmosphere",
    "neutral": "calm everyday scene",
    "romantic": "romantic gentle scene, soft atmosphere",
    "action": "action dynamic scene, characters in motion",
    "excited": "excited energetic scene, characters enthusiastic",
    "fearful": "fearful tense scene, characters look afraid",
}

JUNK_NAMES = {
    "he", "she", "they", "him", "her", "them", "his", "hers", "their",
    "i", "me", "we", "us", "it", "you", "location", "unknown", "none",
    "character", "person", "man", "woman", "boy", "girl",
    "the man", "the woman", "the boy", "the girl", "the person",
    "a man", "a woman", "old man", "young man", "young woman",
    "his secretary", "his secretarys", "her secretary",
    "narrator", "voice", "someone", "anyone", "everyone",
}

PLACEHOLDER_SETTINGS = {"location", "unknown", "none", "'location'", '"location"', ""}

POSSESSIVE_RE = re.compile(r"'s$|s'$", re.IGNORECASE)

def clean_text(s):
    s = s.replace("\\u0022", "").replace("\\u0027", "")
    s = s.replace('\\"', "").replace("\\'", "")
    s = re.sub(r'[\"\'`]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_valid_name(name):
    n = name.strip().lower()
    if not n or len(n) < 2:
        return False
    if n in JUNK_NAMES:
        return False
    if POSSESSIVE_RE.search(n):
        return False
    return True

def build_page_prompt(parsed_scenes, style="lineart"):
    style_def = STYLES.get(style, STYLES["lineart"])

    if not parsed_scenes:
        return style_def["positive"], style_def["negative"]

    all_characters = []
    visual_parts = []
    settings = []
    moods = []

    for scene in parsed_scenes:
        if isinstance(scene, str):
            visual_parts.append(scene)
            continue
        for char in scene.get("characters", []):
            char = clean_text(char)
            if is_valid_name(char):
                all_characters.append(char)
        visual = clean_text(scene.get("visual_scene", ""))
        if visual:
            visual_parts.append(visual)
        setting = clean_text(scene.get("setting", ""))
        if setting.lower() not in PLACEHOLDER_SETTINGS:
            settings.append(setting)
        mood = scene.get("mood", "neutral").strip().lower()
        if mood:
            moods.append(mood)

    unique_chars = list(dict.fromkeys(all_characters))
    char_tokens = build_consistency_tokens(unique_chars)

    dominant_mood = moods[0] if moods else "neutral"
    mood_desc = MOOD_MAP.get(dominant_mood, MOOD_MAP["neutral"])

    setting_str = settings[0][:60] if settings else ""
    scene_str = visual_parts[0][:80] if visual_parts else ""

    style_prefix = (
        "(anime style:1.4), (manga illustration:1.3), "
        "(black and white:1.3), (monochrome:1.2), "
    ) if style == "lineart" else ""

    parts = [style_prefix + style_def["positive"], mood_desc]
    if setting_str:
        parts.append(setting_str)
    if char_tokens:
        parts.append(char_tokens)
    if scene_str:
        parts.append(scene_str)

    return ", ".join(parts), style_def["negative"]

def get_cfg(style="lineart"):
    return STYLES.get(style, STYLES["lineart"])["cfg"]
