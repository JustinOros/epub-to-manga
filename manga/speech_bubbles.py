import textwrap
from PIL import Image, ImageDraw, ImageFont
import os

MAX_BUBBLES = 3
MAX_LINE_WIDTH = 22
BUBBLE_PADDING = 14
FONT_SIZE = 22
TAIL_SIZE = 14

def get_font(size=FONT_SIZE):
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def wrap_text(text, max_width=MAX_LINE_WIDTH):
    return textwrap.fill(text, max_width)

def draw_bubble(draw, x, y, w, h, tail_side="bottom"):
    r = 16
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r, fill="white", outline="black", width=3)

    if tail_side == "bottom":
        tx = x + w // 2
        ty = y + h
        draw.polygon([
            (tx - TAIL_SIZE, ty - 4),
            (tx + TAIL_SIZE, ty - 4),
            (tx, ty + TAIL_SIZE),
        ], fill="white")
        draw.line([(tx - TAIL_SIZE, ty - 4), (tx, ty + TAIL_SIZE)], fill="black", width=3)
        draw.line([(tx + TAIL_SIZE, ty - 4), (tx, ty + TAIL_SIZE)], fill="black", width=3)
    elif tail_side == "top":
        tx = x + w // 2
        ty = y
        draw.polygon([
            (tx - TAIL_SIZE, ty + 4),
            (tx + TAIL_SIZE, ty + 4),
            (tx, ty - TAIL_SIZE),
        ], fill="white")
        draw.line([(tx - TAIL_SIZE, ty + 4), (tx, ty - TAIL_SIZE)], fill="black", width=3)
        draw.line([(tx + TAIL_SIZE, ty + 4), (tx, ty - TAIL_SIZE)], fill="black", width=3)

def add_speech_bubbles(img_path, dialogue):
    if not dialogue:
        return

    entries = [d for d in dialogue if d.get("line", "").strip()][:MAX_BUBBLES]
    if not entries:
        return

    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = get_font(FONT_SIZE)
    small_font = get_font(FONT_SIZE - 6)

    iw, ih = img.size
    margin = 18

    zones = [
        ih // 8,
        ih * 5 // 8,
        ih // 4,
    ]

    for i, entry in enumerate(entries):
        speaker = entry.get("speaker", "").strip()
        line = entry.get("line", "").strip()
        if not line:
            continue

        wrapped = wrap_text(line)

        bbox = draw.textbbox((0, 0), wrapped, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        if speaker and speaker != "?":
            spk_bbox = draw.textbbox((0, 0), speaker, font=small_font)
            spk_h = spk_bbox[3] - spk_bbox[1] + 4
        else:
            spk_h = 0

        bw = min(text_w + BUBBLE_PADDING * 2, iw - margin * 2)
        bh = text_h + spk_h + BUBBLE_PADDING * 2

        x_offset = margin if i % 2 == 0 else iw - bw - margin
        by = zones[i % len(zones)]

        by = max(margin, min(by, ih - bh - margin))

        tail = "bottom" if by < ih // 2 else "top"
        draw_bubble(draw, x_offset, by, bw, bh, tail_side=tail)

        if speaker and speaker != "?":
            draw.text((x_offset + BUBBLE_PADDING, by + BUBBLE_PADDING), speaker, font=small_font, fill="#444444")

        draw.text(
            (x_offset + BUBBLE_PADDING, by + BUBBLE_PADDING + spk_h),
            wrapped,
            font=font,
            fill="black",
        )

    img.save(img_path)
