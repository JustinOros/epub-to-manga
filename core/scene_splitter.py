import re

JUNK_PATTERNS = [
    r'all rights reserved',
    r'copyright\s*©',
    r'isbn[\s\-]',
    r'published by',
    r'first published',
    r'printed in',
    r'no part of this',
    r'table of contents',
    r'this is a work of fiction',
    r'any resemblance to',
]
JUNK_RE = re.compile('|'.join(JUNK_PATTERNS), re.IGNORECASE)

def _is_junk(text):
    if len(text.split()) < 30:
        return True
    if JUNK_RE.search(text):
        return True
    return False

def split_scenes(chapters, min_sentences=3, max_sentences=6):
    scenes = []
    for chapter_text in chapters:
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', chapter_text) if p.strip()]
        buf = []
        buf_sentences = 0

        for para in paragraphs:
            sentences = re.split(r'(?<=[.!?])\s+', para.strip())
            sentences = [s for s in sentences if s]

            for sentence in sentences:
                buf.append(sentence)
                buf_sentences += 1

                if buf_sentences >= max_sentences:
                    candidate = " ".join(buf)
                    if not _is_junk(candidate):
                        scenes.append(candidate)
                    buf = []
                    buf_sentences = 0

            if buf_sentences >= min_sentences:
                candidate = " ".join(buf)
                if not _is_junk(candidate):
                    scenes.append(candidate)
                buf = []
                buf_sentences = 0

        if buf:
            candidate = " ".join(buf)
            if scenes and _is_junk(candidate):
                pass
            elif scenes:
                scenes[-1] = scenes[-1] + " " + candidate
            elif not _is_junk(candidate):
                scenes.append(candidate)

    return [s for s in scenes if len(s.strip()) > 20]
