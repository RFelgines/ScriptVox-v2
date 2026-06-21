import ebooklib
from bs4 import BeautifulSoup
from dataclasses import dataclass
from ebooklib import epub

from app.core.exceptions import EpubParsingError

# Tags de bloc : un paragraphe source = une ligne de raw_text. Le hard-wrap interne
# (XHTML ~80 colonnes) introduit des \n EN PLEIN MILIEU d'une phrase ou d'une réplique
# em-dash, ce qui casse leur détection en aval (_pre_segment, ARCHITECTURE.md §2.7) --
# d'où l'écrasement du whitespace interne à chaque bloc, pas seulement à ses bords.
_BLOCK_TAGS = ("p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6")


def _is_leaf_block(tag) -> bool:
    """Vrai si *tag* ne contient aucun autre tag de bloc (évite le double comptage)."""
    return tag.find(_BLOCK_TAGS) is None


def _extract_text(soup: BeautifulSoup) -> str:
    """Un paragraphe = une ligne ; le whitespace (espaces, \\n de hard-wrap, \\xa0)
    interne à un même paragraphe est écrasé en un espace simple. Repli sur l'ancien
    comportement (tout le document, séparateur \\n) si aucun bloc feuille n'est trouvé
    -- jamais de texte perdu sur un document mal structuré."""
    leaves = [b for b in soup.find_all(_BLOCK_TAGS) if _is_leaf_block(b)]
    if not leaves:
        return soup.get_text(separator="\n", strip=True)
    lines = [" ".join(b.get_text().split()) for b in leaves]
    return "\n".join(line for line in lines if line)


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
    cover_image: bytes | None = None
    cover_media_type: str | None = None


def _extract_cover(book) -> tuple[bytes | None, str | None]:
    # Strategy 1: conventional 'cover-image' uid (ebooklib / most EPUB generators)
    item = book.get_item_with_id("cover-image")
    if item is not None:
        content = item.get_content()
        if content:
            return content, item.media_type or None

    # Strategy 2: items of type ITEM_COVER (epub3)
    try:
        import ebooklib as _eb
        for item in book.get_items_of_type(_eb.ITEM_COVER):
            content = item.get_content()
            if content:
                return content, item.media_type or None
    except Exception:
        pass

    # Strategy 3: items with 'cover-image' in properties
    for item in book.get_items():
        props = getattr(item, "properties", "") or ""
        if "cover-image" in props:
            content = item.get_content()
            if content:
                return content, item.media_type or None

    return None, None


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

            raw_text = _extract_text(soup)
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

        cover_image, cover_media_type = _extract_cover(book)
        return ParsedBook(
            title=title,
            author=author,
            chapters=chapters,
            cover_image=cover_image,
            cover_media_type=cover_media_type,
        )
