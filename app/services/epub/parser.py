import ebooklib
from bs4 import BeautifulSoup
from dataclasses import dataclass
from ebooklib import epub

from app.core.exceptions import EpubParsingError


@dataclass
class ParsedChapter:
    position: int
    title: str | None
    raw_text: str


@dataclass
class ParsedBook:
    title: str
    author: str | None
    chapters: list[ParsedChapter]


class EpubParser:
    def parse(self, path: str) -> ParsedBook:
        try:
            book = epub.read_epub(path)
        except Exception as exc:
            raise EpubParsingError(path, exc) from exc

        title = (book.title or "").strip() or path.rsplit("/", 1)[-1].removesuffix(".epub")

        creators = book.get_metadata("DC", "creator")
        author = creators[0][0].strip() if creators else None

        items_by_id = {
            item.get_id(): item
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        }

        chapters: list[ParsedChapter] = []
        position = 0

        for spine_id, _ in book.spine:
            item = items_by_id.get(spine_id)
            if item is None:
                continue

            soup = BeautifulSoup(item.get_content(), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()

            raw_text = soup.get_text(separator="\n", strip=True)
            if not raw_text:
                continue

            chapter_title: str | None = None
            heading = soup.find(["h1", "h2", "h3"])
            if heading:
                chapter_title = heading.get_text(strip=True) or None
            elif soup.title:
                chapter_title = soup.title.get_text(strip=True) or None

            position += 1
            chapters.append(
                ParsedChapter(position=position, title=chapter_title, raw_text=raw_text)
            )

        return ParsedBook(title=title, author=author, chapters=chapters)
