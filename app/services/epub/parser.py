import re
import warnings
import zipfile

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
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
    r"acknowledg|about[-_ ]the[-_ ]author|nav|project gutenberg|pg[-_ ]header|pg[-_ ]footer|"
    r"coverpage|wrapper)\b"
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


# Sémantique EPUB des pages non narratives : types des repères EPUB3 (nav landmarks,
# epub:type) et du <guide> OPF d'EPUB2. « bodymatter », « text », « chapter »… restent inclus.
_NON_NARRATIVE_TYPES = {
    "cover", "titlepage", "title-page", "halftitlepage", "toc", "loi", "lot", "copyright-page",
    "copyright", "colophon", "dedication", "acknowledgements", "acknowledgments", "imprint",
    "imprimatur", "index", "bibliography", "glossary", "notice", "contributors", "errata",
    "landmarks", "page-list",
}


def _file_key(href: str) -> str:
    return href.split("#", 1)[0].rsplit("/", 1)[-1]


def _nav_entries(book) -> tuple[list[tuple[str, str]], set[str]]:
    """Nav EPUB3 lue directement : (entrées du sommaire [(href, titre)] dans l'ordre,
    fichiers marqués non narratifs par les repères « landmarks »). Vide sans nav."""
    entries: list[tuple[str, str]] = []
    non_narrative: set[str] = set()
    for item in book.get_items():
        if not isinstance(item, epub.EpubNav):
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for nav in soup.find_all("nav"):
            kind = (nav.get("epub:type") or nav.get("role") or "").lower()
            for a in nav.find_all("a", href=True):
                if "landmarks" in kind:
                    if (a.get("epub:type") or "").lower() in _NON_NARRATIVE_TYPES:
                        non_narrative.add(_file_key(a["href"]))
                elif "toc" in kind:
                    title = " ".join(a.get_text().split())
                    if title:
                        entries.append((a["href"], title))
    return entries, non_narrative


def _ncx_entries(book) -> list[tuple[str, str]]:
    """NCX (EPUB2) lu directement, dans l'ordre des navPoint (imbrication comprise)."""
    entries: list[tuple[str, str]] = []
    for item in book.get_items():
        if item.media_type != "application/x-dtbncx+xml" and not (item.get_name() or "").endswith(".ncx"):
            continue
        with warnings.catch_warnings():  # NCX = XML lu en HTML exprès (tolérant, sans lxml)
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(item.get_content(), "html.parser")
        for point in soup.find_all("navpoint"):
            label, content = point.find("navlabel"), point.find("content")
            title = " ".join(label.get_text().split()) if label else ""
            if content is not None and content.get("src") and title:
                entries.append((content["src"], title))
    return entries


def _ebooklib_entries(book) -> list[tuple[str, str]]:
    """book.toc d'ebooklib aplati (dernier recours)."""
    entries: list[tuple[str, str]] = []

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
                entries.append((href, str(title).strip()))

    try:
        walk(book.toc)
    except Exception:  # noqa: BLE001 — TOC malformée : on retombe sur les <h1>
        return []
    return entries


def _toc_entries(book) -> list[tuple[str, str]]:
    """Sommaire de référence [(href, titre)] : la nav EPUB3 d'abord ; le NCX complète les
    fichiers que la nav ne couvre pas, ou la remplace si elle est vide ou cassée (ebooklib,
    lui, ne retombe pas sur le NCX quand une nav existe) ; book.toc d'ebooklib en dernier
    recours. Les titres par intertitre (<h1>…) restent le repli de l'appelant."""
    nav, _ = _nav_entries(book)
    merged = list(nav)
    covered_files = {_file_key(h) for h, _ in nav}
    for href, title in _ncx_entries(book):
        if _file_key(href) not in covered_files:
            merged.append((href, title))
    return merged or _ebooklib_entries(book)


def _non_narrative_files(book) -> set[str]:
    """Fichiers déclarés couverture, page de titre, sommaire, mentions légales… par la
    sémantique EPUB (repères de la nav EPUB3, <guide> OPF d'EPUB2)."""
    _, landmarks = _nav_entries(book)
    guide = {
        _file_key(g.get("href") or "") for g in (getattr(book, "guide", None) or [])
        if (g.get("type") or "").lower() in _NON_NARRATIVE_TYPES and g.get("href")
    }
    return landmarks | guide


_BODY_TYPES = {"bodymatter", "chapter", "part", "division", "volume", "prologue", "epilogue"}
_PAGENUM_CLASS = re.compile(r"(?i)\bpage-?num(ber)?\b|\bpagenum\b")


def _strip_page_numbers(soup: BeautifulSoup) -> None:
    """Numéros de page d'une édition imprimée : jamais lus. EPUB3 (epub:type="pagebreak",
    role="doc-pagebreak", fréquents dans les éditions accessibles) et classe « pagenum » des
    EPUB convertis. Le texte qui suit un saut de page est conservé."""
    for tag in soup.find_all(True):
        types = (tag.get("epub:type") or "").lower().split()
        cls = " ".join(tag.get("class") or [])
        if "pagebreak" in types or tag.get("role") == "doc-pagebreak" or _PAGENUM_CLASS.search(cls):
            tag.decompose()


def _declared_body(soup: BeautifulSoup) -> bool:
    """Le document se déclare corps du texte (epub:type chapter, bodymatter…)."""
    for tag in (soup.find("body"), soup.find(["section", "div"])):
        types = set(((tag.get("epub:type") or "") if tag else "").lower().split())
        if types & _BODY_TYPES:
            return True
    return False


def _declared_non_narrative(soup: BeautifulSoup) -> bool:
    """epub:type porté par le <body> ou par la première section du document."""
    for tag in (soup.find("body"), soup.find(["section", "div"])):
        types = set(((tag.get("epub:type") or "") if tag else "").lower().split())
        if types & _NON_NARRATIVE_TYPES:
            return True
    return False


def _toc_titles(book, entries: list[tuple[str, str]] | None = None) -> dict[str, str]:
    """Titres du sommaire par nom de fichier (premier titre qui pointe vers le fichier) :
    plus fiables que le premier <h1> (souvent le titre du livre répété, ou absent)."""
    titles: dict[str, str] = {}
    for href, title in (entries if entries is not None else _toc_entries(book)):
        titles.setdefault(_file_key(href), title)
    return titles


def _toc_anchors(book, entries: list[tuple[str, str]] | None = None) -> dict[str, list[tuple[str, str]]]:
    """Ancres du sommaire par fichier, dans l'ordre : {fichier: [(id_ancre, titre), ...]}.
    Sert à découper un fichier qui contient PLUSIEURS chapitres (cas des EPUB du Projet
    Gutenberg : tout le livre en 3-4 fichiers)."""
    anchors: dict[str, list[tuple[str, str]]] = {}
    for href, title in (entries if entries is not None else _toc_entries(book)):
        if "#" not in href:
            continue
        anchor = href.split("#", 1)[1]
        key = _file_key(href)
        if anchor and all(a != anchor for a, _ in anchors.get(key, [])):
            anchors.setdefault(key, []).append((anchor, title))
    return anchors


def _split_by_anchors(soup: BeautifulSoup, anchors: list[tuple[str, str]]) -> list[tuple[str | None, str]]:
    """Découpe un document aux éléments dont l'id figure dans `anchors` (ordre du document).
    Retourne [(titre, texte)] ; le texte avant la première ancre forme une section sans titre.
    Même extraction qu'_extract_text (un paragraphe = une ligne) : aucun texte n'est perdu."""
    wanted = {a: t for a, t in anchors}
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for el in soup.descendants:
        if not getattr(el, "name", None):
            continue
        el_id = el.get("id")
        if el_id in wanted:
            sections.append((wanted.pop(el_id), []))
        if el.name in _BLOCK_TAGS and _is_leaf_block(el):
            line = " ".join(el.get_text().split())
            if line:
                sections[-1][1].append(line)
    return [(title, "\n".join(lines)) for title, lines in sections if lines]


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
        entries = _toc_entries(book)
        toc = _toc_titles(book, entries)
        anchors = _toc_anchors(book, entries)
        declared_front = _non_narrative_files(book)
        declared_by_body: set[int] = set()  # index des chapitres dont le <body> le déclare
        declared_body_files: set[str] = set()  # fichiers qui se déclarent corps du texte
        file_names: list[str] = []

        for spine_id, _ in book.spine:
            item = items_by_id.get(spine_id)
            if item is None:
                continue

            soup = BeautifulSoup(item.get_content(), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            _strip_page_numbers(soup)

            item_file = (item.get_name() or "").rsplit("/", 1)[-1]
            # Contenu BRUT : get_content() d'ebooklib reconstruit le document et perd les
            # attributs du <body>, dont epub:type.
            raw_soup = BeautifulSoup(getattr(item, "content", b"") or b"", "html.parser")
            declared = item_file in declared_front or _declared_non_narrative(raw_soup)
            if _declared_body(raw_soup) and not declared:
                declared_body_files.add(item_file)
            file_anchors = anchors.get(item_file, [])
            if len(file_anchors) >= 2:
                # Plusieurs chapitres dans ce fichier : un chapitre par entrée du sommaire.
                for section_title, section_text in _split_by_anchors(soup, file_anchors):
                    if declared:
                        declared_by_body.add(len(chapters))
                    position += 1
                    file_names.append(item.get_name() or "")
                    chapters.append(ParsedChapter(
                        position=position, title=section_title, raw_text=section_text,
                    ))
                continue

            raw_text = _extract_text(soup)
            if not raw_text:
                continue

            chapter_title: str | None = toc.get(item_file)
            if not chapter_title:
                heading = soup.find(["h1", "h2", "h3"])
                if heading:
                    chapter_title = heading.get_text(strip=True) or None
                elif soup.title:
                    chapter_title = soup.title.get_text(strip=True) or None

            if declared:
                declared_by_body.add(len(chapters))
            position += 1
            file_names.append(item.get_name() or "")
            chapters.append(
                ParsedChapter(position=position, title=chapter_title, raw_text=raw_text)
            )

        # Pages que l'EPUB DÉCLARE non narratives (repères EPUB3, <guide> OPF, epub:type) :
        # couverture, page de titre, sommaire, mentions légales… Métadonnée explicite, pas
        # une heuristique : appliquée même à un livre court. Réactivables dans l'UI.
        for i in declared_by_body:
            chapters[i].included = False

        # Pages non narratives (BE-6). Appliqué seulement si le livre contient au moins un vrai
        # chapitre : un livre entièrement court (jeu de test, recueil de poèmes) ne doit pas
        # être vidé de son contenu par une heuristique.
        has_real_chapter = any(len(c.raw_text) >= _REAL_BOOK_CHARS for c in chapters)
        if has_real_chapter:
            for chapter, name in zip(chapters, file_names):
                # Un chapitre DÉCLARÉ corps du texte n'est jamais exclu sur la foi de son titre
                # ou de son nom de fichier (« Dédicace », « Contents » peuvent être un vrai récit).
                if name.rsplit("/", 1)[-1] in declared_body_files:
                    continue
                label = f"{name} {chapter.title or ''}"
                boilerplate = "project gutenberg" in chapter.raw_text[:400].lower()
                if (_NON_NARRATIVE_RE.search(label) or boilerplate
                        or len(chapter.raw_text) < _SHORT_CHAPTER_CHARS):
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
