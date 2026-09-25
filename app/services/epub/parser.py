import re
import zipfile

import ebooklib
from bs4 import BeautifulSoup
from dataclasses import dataclass
from ebooklib import epub

from app.core.exceptions import EpubParsingError

# ── Garde-fou « bombe de décompression » (SEC-5) ────────────────────────────────
# L'upload est plafonné à 200 Mo, mais un zip piégé peut se décompresser en plusieurs Go.
_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
_MAX_ENTRIES = 5000
_MAX_RATIO = 100  # rapport décompressé/compressé toléré par fichier > 1 Mo

# Pages non narratives (BE-6) : détectées par le nom du fichier ou le titre.
_NON_NARRATIVE_RE = re.compile(
    r"(?i)\b(cover|couverture|copyright|colophon|toc|table[-_ ]des[-_ ]mati|sommaire|contents|"
    r"titlepage|title[-_ ]page|page[-_ ]de[-_ ]titre|d[ée]dicace|dedication|remerciements|"
    r"acknowledg|about[-_ ]the[-_ ]author|nav)\b"
)
_SHORT_CHAPTER_CHARS = 300
_REAL_BOOK_CHARS = 5000  # le critère de longueur ne s'applique que si le livre a un vrai chapitre


def _check_zip_safety(path: str) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError):
        return  # laissé à ebooklib, qui produira l'EpubParsingError habituelle
    if len(infos) > _MAX_ENTRIES:
        raise ValueError(f"EPUB refusé : {len(infos)} fichiers (max {_MAX_ENTRIES}).")
    total = sum(i.file_size for i in infos)
    if total > _MAX_UNCOMPRESSED_BYTES:
        raise ValueError(
            f"EPUB refusé : {total // (1024 * 1024)} Mo décompressés (max "
            f"{_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} Mo)."
        )
    for i in infos:
        if i.file_size > 1024 * 1024 and i.compress_size > 0 and i.file_size / i.compress_size > _MAX_RATIO:
            raise ValueError(f"EPUB refusé : taux de compression suspect ({i.filename}).")

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
    # False = page non narrative détectée (couverture, copyright, sommaire…) : ignorée par
    # l'analyse et la génération, réactivable dans l'UI.
    included: bool = True


@dataclass
class ParsedBook:
    title: str
    author: str | None
    chapters: list[ParsedChapter]
    cover_image: bytes | None = None
    cover_media_type: str | None = None
    language: str | None = None


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

    # Strategy 4: fallback for EPUBs with NO formal cover declaration at all (no OPF
    # <meta name="cover">, no EPUB3 manifest property) -- common with older conversion
    # tools (observed: an "AlexandriZ"-generated EPUB whose cover item is named "cover"
    # by convention only). Best-effort: an image item whose id or filename mentions
    # "cover", picking the first match in manifest order.
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_IMAGE:
            continue
        haystack = f"{item.get_id()} {item.get_name()}".lower()
        if "cover" in haystack:
            content = item.get_content()
            if content:
                return content, item.media_type or None

    return None, None


def _toc_titles(book) -> dict[str, str]:
    """Titres de la table des matières EPUB par nom de fichier : plus fiables que le premier
    <h1> (souvent le titre du livre répété, ou absent)."""
    titles: dict[str, str] = {}

    def walk(nodes) -> None:
        for node in nodes:
            if isinstance(node, (list, tuple)):
                if node:
                    walk([node[0]])
                    if len(node) > 1 and isinstance(node[1], (list, tuple)):
                        walk(node[1])
                continue
            href = getattr(node, "href", None)
            title = getattr(node, "title", None)
            if href and title:
                key = href.split("#", 1)[0].rsplit("/", 1)[-1]
                titles.setdefault(key, str(title).strip())

    try:
        walk(book.toc)
    except Exception:  # noqa: BLE001 — TOC malformée : on retombe sur les <h1>
        return {}
    return titles


class EpubParser:
    def parse(self, path: str) -> ParsedBook:
        _check_zip_safety(path)
        try:
            book = epub.read_epub(path)
        except Exception as exc:
            raise EpubParsingError(path, exc) from exc

        title = (book.title or "").strip() or path.rsplit("/", 1)[-1].removesuffix(".epub")

        creators = book.get_metadata("DC", "creator")
        author = creators[0][0].strip() if creators else None

        languages = book.get_metadata("DC", "language")
        language = languages[0][0].strip() or None if languages else None

        items_by_id = {
            item.get_id(): item
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        }

        chapters: list[ParsedChapter] = []
        position = 0
        toc = _toc_titles(book)
        file_names: list[str] = []

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

            item_file = (item.get_name() or "").rsplit("/", 1)[-1]
            chapter_title: str | None = toc.get(item_file)
            if not chapter_title:
                heading = soup.find(["h1", "h2", "h3"])
                if heading:
                    chapter_title = heading.get_text(strip=True) or None
                elif soup.title:
                    chapter_title = soup.title.get_text(strip=True) or None

            position += 1
            file_names.append(item.get_name() or "")
            chapters.append(
                ParsedChapter(position=position, title=chapter_title, raw_text=raw_text)
            )

        # Pages non narratives (BE-6). Appliqué seulement si le livre contient au moins un vrai
        # chapitre : un livre entièrement court (jeu de test, recueil de poèmes) ne doit pas
        # être vidé de son contenu par une heuristique.
        has_real_chapter = any(len(c.raw_text) >= _REAL_BOOK_CHARS for c in chapters)
        if has_real_chapter:
            for chapter, name in zip(chapters, file_names):
                label = f"{name} {chapter.title or ''}"
                if _NON_NARRATIVE_RE.search(label) or len(chapter.raw_text) < _SHORT_CHAPTER_CHARS:
                    chapter.included = False

        cover_image, cover_media_type = _extract_cover(book)
        return ParsedBook(
            title=title,
            author=author,
            chapters=chapters,
            cover_image=cover_image,
            cover_media_type=cover_media_type,
            language=language,
        )
