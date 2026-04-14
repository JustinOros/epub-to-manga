from ebooklib import epub
from ebooklib import ITEM_DOCUMENT
from bs4 import BeautifulSoup

CHAPTER_TAGS = {"h1", "h2", "h3", "h4"}

def read_epub(path):
    book = epub.read_epub(path)
    chapters = []
    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            chapters.append(soup.get_text())
    return chapters

def read_epub_flat(path):
    return "\n\n".join(read_epub(path))

def read_epub_metadata(path):
    book = epub.read_epub(path)
    title = book.get_metadata('DC', 'title')
    author = book.get_metadata('DC', 'creator')
    title_str = title[0][0] if title else None
    author_str = author[0][0] if author else None
    return title_str, author_str
