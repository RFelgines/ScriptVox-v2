"""Génère un epub mono-chapitre — Ch.3 HP (« Le Survivant », 82 dialogues, le pire
cas déjà cartographié côté LLM, jamais testé côté TTS) — pour atteindre ANALYZED
en minutes plutôt qu'en heures (cf. Phase 11 Étape 8 / TASKS.md).

Hors suite de régression : nécessite un epub dans `Ebook/`, aucun assert — produit
un fichier. Sélection du chapitre identique à `bench_hp_label_based.py`
(MIN_CONTENT_CHARS=1500, content[0]) pour rester cohérent avec la cartographie B-3.

Sortie : Ebook/hp_chapter3_only.epub (gitignored — contenu HP copyrighté).

Run: .venv/Scripts/python tests/make_hp_chapter3_fixture.py
"""
import html
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from ebooklib import epub  # noqa: E402

from app.services.epub.parser import EpubParser  # noqa: E402
from app.services.llm.base import _pre_segment  # noqa: E402

MIN_CONTENT_CHARS = 1500  # identique à bench_hp_label_based.py


OUT_NAME = "hp_chapter3_only.epub"


def main() -> None:
    # Exclut notre propre sortie des candidats : Windows trie les chemins sans
    # tenir compte de la casse, donc un sorted() naïf reprendrait ce fichier au
    # lieu de la vraie source dès le 2e run ("h" < "r" une fois la casse ignorée).
    epubs = sorted(p for p in (ROOT / "Ebook").glob("*.epub") if p.name != OUT_NAME)
    if not epubs:
        print("Aucun epub source dans Ebook/ — abandon.")
        sys.exit(1)
    src_path = epubs[0]
    print(f"Source : {src_path.name}")

    parsed = EpubParser().parse(str(src_path))
    content = [ch for ch in parsed.chapters if len(ch.raw_text) >= MIN_CONTENT_CHARS]
    if not content:
        print("Aucun chapitre de contenu — abandon.")
        sys.exit(1)
    ch = content[0]

    spans = _pre_segment(ch.raw_text)
    n_dialogue = sum(1 for s in spans if s.is_dialogue)
    print(f"Chapitre sélectionné : position {ch.position}  « {(ch.title or '?').strip()} »")
    print(f"  {len(ch.raw_text):,} car.  ·  {len(spans)} spans ({n_dialogue} dialogue / {len(spans) - n_dialogue} narration)")

    # Reconstruit le HTML ligne par ligne : ch.raw_text est déjà le résultat de
    # BeautifulSoup get_text(separator="\n") sur l'epub original — il contient
    # DÉJÀ le titre en 1res lignes (le <h1> source était "1<br/>LE SURVIVANT").
    # Pas de <h1> séparé ici : ça le dupliquerait. Réinjecter chaque ligne dans
    # son propre <p> garantit un round-trip byte-exact (mêmes délimiteurs de
    # dialogue en tête de ligne pour _pre_segment).
    title = (ch.title or "Chapitre").strip()
    lines = [html.escape(line) for line in ch.raw_text.split("\n")]
    body = "\n".join(f"<p>{line}</p>" for line in lines)
    chapter_item = epub.EpubHtml(title=title, file_name="chap01.xhtml")
    chapter_item.content = f"<html><body>{body}</body></html>".encode("utf-8")

    book = epub.EpubBook()
    book.set_title(f"{parsed.title} [Ch.3 seul — test TTS]")
    book.set_language("fr")
    if parsed.author:
        book.add_author(parsed.author)
    book.add_item(chapter_item)
    # nav reste dans le manifeste (conformité EPUB3) mais PAS dans le spine :
    # EpubParser ne lit que les items référencés par le spine, donc l'inclure
    # ici ferait apparaître un faux 2e "chapitre" (le contenu auto-généré du nav).
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = [chapter_item]

    out_path = ROOT / "Ebook" / OUT_NAME
    epub.write_epub(str(out_path), book)
    print(f"\nÉcrit : {out_path}")

    # Sanity check : round-trip via le vrai parser, doit retrouver le même texte.
    reparsed = EpubParser().parse(str(out_path))
    assert len(reparsed.chapters) == 1, f"attendu 1 chapitre, obtenu {len(reparsed.chapters)}"
    match = reparsed.chapters[0].raw_text == ch.raw_text
    print(f"Round-trip texte identique à l'original : {'OK' if match else 'DIVERGENT !'}")
    if not match:
        print(f"  original  : {len(ch.raw_text)} car.")
        print(f"  round-trip: {len(reparsed.chapters[0].raw_text)} car.")


if __name__ == "__main__":
    main()
