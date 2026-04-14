from ebooklib import epub
from PIL import Image
import io
import os

def _to_jpeg(img_path, quality=85):
    img = Image.open(img_path).convert("L").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()

def build_epub(images, output, title="Manga Book", author="Manga", jpeg_quality=85):
    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    chapters = []

    for i, img_path in enumerate(images):
        if not os.path.exists(img_path):
            continue

        img_data = _to_jpeg(img_path, quality=jpeg_quality)
        img_name = f"images/page_{i}.jpg"

        epub_img = epub.EpubItem(
            uid=f"img_{i}",
            file_name=img_name,
            media_type="image/jpeg",
            content=img_data,
        )
        book.add_item(epub_img)

        c = epub.EpubHtml(title=f"Page {i+1}", file_name=f"p{i}.xhtml", lang="en")
        c.content = (
            f'<html><body style="margin:0;padding:0;background:#000;">'
            f'<img src="{img_name}" style="width:100%;height:auto;display:block;"/>'
            f'</body></html>'
        )
        book.add_item(c)
        chapters.append(c)

    book.toc = tuple(chapters)
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(output, book)
    return output
