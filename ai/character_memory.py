CHARACTER_DB = {}

def load(data):
    global CHARACTER_DB
    CHARACTER_DB = data if isinstance(data, dict) else {}

def dump():
    return dict(CHARACTER_DB)

def update(name, description=""):
    if name not in CHARACTER_DB:
        CHARACTER_DB[name] = {"appearances": 0, "description": description}
    else:
        if description and not CHARACTER_DB[name].get("description"):
            CHARACTER_DB[name]["description"] = description
    CHARACTER_DB[name]["appearances"] += 1

def add_hint(name, description):
    if name not in CHARACTER_DB:
        CHARACTER_DB[name] = {"appearances": 0, "description": description}
    else:
        CHARACTER_DB[name]["description"] = description

def get_all():
    return list(CHARACTER_DB.keys())

def build_consistency_tokens(characters):
    parts = []
    for c in characters:
        if not c or not c.strip():
            continue
        desc = CHARACTER_DB.get(c, {}).get("description", "")
        if desc:
            parts.append(f"{c} ({desc})")
        else:
            parts.append(c)
    return ", ".join(parts)
