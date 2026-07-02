"""check_phase30.py — Phase 30 (Lot E, audit 2026-07-02) : migrations Alembic.

Remplace SQLModel.metadata.create_all() (init_db) par des migrations Alembic —
chaque évolution de schéma historique de ce projet a nécessité de supprimer
scriptvox.db et perdre toute la bibliothèque, puisque create_all() ne fait
JAMAIS que créer les tables manquantes, jamais évoluer une table existante.

⚠️ Ce test n'utilise QUE des fichiers SQLite jetables créés dans un répertoire
temporaire — jamais scriptvox.db/data/ réels (une analyse de livre réelle est
en cours ailleurs pendant cette session).

Valide :
  - Base neuve (fichier vide) -> _ensure_schema crée tout le schéma via la
    migration baseline (équivalent à l'ancien create_all).
  - Base "pré-Alembic" (tables déjà créées via un create_all brut, sans
    historique alembic -- exactement l'état de tout scriptvox.db existant
    aujourd'hui) -> auto-tamponnée (stamp), pas de crash, pas de tentative de
    recréer des tables existantes.
  - **Le plus important** : une base pré-Alembic contenant déjà de VRAIES
    données (un Book réel) -> ces données survivent intactes, octet pour octet,
    après l'auto-tamponnement. Aucune perte, aucune intervention manuelle.
  - Idempotence : appeler _ensure_schema deux fois de suite sur la même base
    ne lève rien et ne duplique rien.
  - Intégration : init_db() (point d'entrée public réel) sur une base neuve
    crée le schéma ET seed le catalogue de voix (comportement préexistant).
  - Intégration : init_db() sur une base pré-Alembic avec des données
    existantes (Book + Voice favorite) -> tout survit, le seed catalogue reste
    idempotent (pas de doublon).

Run: .venv/Scripts/python tests/check_phase30.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p30.db",
    "HUEY_DB_PATH": "./huey_test_p30.db",
})

PASS = "\033[32mOK\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_errors: list[str] = []
_n = 0


def section(title: str) -> None:
    global _n
    _n += 1
    print(f"\n[{_n}] {title}")


def ok(label: str) -> None:
    print(f"    ok  {label}")


def fail(label: str, detail: str = "") -> None:
    msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
    print(msg)
    _errors.append(msg)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        ok(label)
    else:
        fail(label, detail)


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
from sqlalchemy import create_engine, inspect  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402

from app.core.db import _ensure_schema, init_db  # noqa: E402
from app.models import Book, Voice  # noqa: E402
from app.core.enums import BookStatus, Gender, VoiceKind  # noqa: E402
ok("_ensure_schema, init_db, models, enums")


def _fresh_file_engine(tmpdir: Path, name: str = "test.db"):
    """Un fichier SQLite réel (pas :memory:) dans un tempdir jetable -- jamais
    scriptvox.db/data/ réels."""
    return create_engine(
        f"sqlite:///{tmpdir / name}", connect_args={"check_same_thread": False},
    )


# ── 2. Base neuve -> _ensure_schema crée tout le schéma ──────────────────────
section("Base neuve (fichier vide) : _ensure_schema crée toutes les tables")
with tempfile.TemporaryDirectory() as _tmp2:
    _eng2 = _fresh_file_engine(Path(_tmp2))
    _ensure_schema(_eng2)
    _tables2 = set(inspect(_eng2).get_table_names())
    check("table 'book' créée", "book" in _tables2, f"got {_tables2}")
    check("table 'chapter' créée", "chapter" in _tables2)
    check("table 'segment' créée", "segment" in _tables2)
    check("table 'voice' créée", "voice" in _tables2)
    check("historique alembic présent ('alembic_version')", "alembic_version" in _tables2)
    _eng2.dispose()


# ── 3. Base "pré-Alembic" (create_all brut) -> auto-tamponnée, pas de crash ──
section("Base pré-Alembic (create_all brut, sans historique) : auto-tamponnée sans crash")
with tempfile.TemporaryDirectory() as _tmp3:
    _eng3 = _fresh_file_engine(Path(_tmp3))
    import app.models  # noqa: F401 -- enregistre les tables sur SQLModel.metadata
    SQLModel.metadata.create_all(_eng3)  # simule l'ancien comportement (avant ce lot)
    _tables_before3 = set(inspect(_eng3).get_table_names())
    check("pas d'historique alembic avant (simule une vraie DB existante)",
          "alembic_version" not in _tables_before3, f"got {_tables_before3}")

    try:
        _ensure_schema(_eng3)
        ok("_ensure_schema ne lève rien sur une base pré-Alembic existante")
    except Exception as exc:
        fail("_ensure_schema a levé une exception sur une base pré-Alembic",
             f"{type(exc).__name__}: {exc}")

    _tables_after3 = set(inspect(_eng3).get_table_names())
    check("historique alembic maintenant présent (tamponnée)",
          "alembic_version" in _tables_after3)
    check("toutes les tables applicatives toujours présentes",
          _tables_before3 <= _tables_after3, f"avant={_tables_before3} après={_tables_after3}")
    _eng3.dispose()


# ── 4. LE PLUS IMPORTANT : des données réelles survivent au tamponnage ───────
section("Données réelles préexistantes survivent intactes à l'auto-tamponnage")
with tempfile.TemporaryDirectory() as _tmp4:
    _eng4 = _fresh_file_engine(Path(_tmp4))
    SQLModel.metadata.create_all(_eng4)  # simule une vraie DB déjà en usage

    with Session(_eng4) as _s:
        _book4 = Book(
            title="Mon Vrai Livre", author="Un Vrai Auteur",
            source_path="/data/1/original.epub", status=BookStatus.DONE,
            progress=100.0, audio_path="/data/1/book.wav", mp3_path="/data/1/book.mp3",
        )
        _s.add(_book4)
        _s.commit()
        _s.refresh(_book4)
        _book4_id = _book4.id

    _ensure_schema(_eng4)  # l'opération potentiellement dangereuse

    with Session(_eng4) as _s:
        _book4_after = _s.get(Book, _book4_id)
        check("le livre existe toujours (même id)", _book4_after is not None)
        if _book4_after:
            check("titre intact", _book4_after.title == "Mon Vrai Livre",
                  f"got {_book4_after.title!r}")
            check("auteur intact", _book4_after.author == "Un Vrai Auteur")
            check("statut intact (DONE)", _book4_after.status == BookStatus.DONE,
                  f"got {_book4_after.status}")
            check("audio_path intact", _book4_after.audio_path == "/data/1/book.wav")
            check("mp3_path intact", _book4_after.mp3_path == "/data/1/book.mp3")
    _eng4.dispose()


# ── 5. Idempotence : appeler _ensure_schema deux fois ne casse rien ──────────
section("Idempotence : _ensure_schema appelé 2x de suite sur la même base -> aucun crash")
with tempfile.TemporaryDirectory() as _tmp5:
    _eng5 = _fresh_file_engine(Path(_tmp5))
    _ensure_schema(_eng5)
    try:
        _ensure_schema(_eng5)
        ok("2e appel sans exception (déjà à head)")
    except Exception as exc:
        fail("2e appel a levé une exception", f"{type(exc).__name__}: {exc}")
    _eng5.dispose()


# ── 6. Intégration : init_db() sur base neuve -> schéma + seed catalogue ─────
section("Intégration : init_db() sur base neuve -> tables + catalogue de voix seedé")
with tempfile.TemporaryDirectory() as _tmp6:
    _eng6 = _fresh_file_engine(Path(_tmp6))
    init_db(_eng6)
    with Session(_eng6) as _s:
        _voices6 = _s.exec(select(Voice)).all()
        check("catalogue de voix seedé (narrator + 8 autres = 9)", len(_voices6) == 9,
              f"got {len(_voices6)}")
    _eng6.dispose()


# ── 7. Intégration : init_db() sur base pré-Alembic avec données existantes ──
section("Intégration : init_db() préserve les données d'une base pré-Alembic existante")
with tempfile.TemporaryDirectory() as _tmp7:
    _eng7 = _fresh_file_engine(Path(_tmp7))
    SQLModel.metadata.create_all(_eng7)  # simule une vraie DB déjà en usage

    with Session(_eng7) as _s:
        _voice7 = Voice(
            voice_id="patrick-baud-clone", name="Patrick Baud",
            kind=VoiceKind.CLONED, gender=Gender.MALE, is_favorite=True,
            reference_audio_path="/data/voices/patrick-baud/ref.wav",
        )
        _s.add(_voice7)
        _s.commit()

    init_db(_eng7)

    with Session(_eng7) as _s:
        _cloned7 = _s.exec(
            select(Voice).where(Voice.voice_id == "patrick-baud-clone")
        ).first()
        check("voix clonée préexistante toujours présente", _cloned7 is not None)
        if _cloned7:
            check("is_favorite intact", _cloned7.is_favorite is True)
            check("reference_audio_path intact",
                  _cloned7.reference_audio_path == "/data/voices/patrick-baud/ref.wav")

        _all_voices7 = _s.exec(select(Voice)).all()
        _catalogue7 = [v for v in _all_voices7 if v.kind == VoiceKind.CATALOGUE]
        check("catalogue seedé sans doublon (9 voix catalogue)", len(_catalogue7) == 9,
              f"got {len(_catalogue7)}")
        check("la voix clonée n'a pas été dupliquée",
              sum(1 for v in _all_voices7 if v.voice_id == "patrick-baud-clone") == 1)
    _eng7.dispose()


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p30.db", "huey_test_p30.db"):
    try:
        if os.path.exists(_leftover):
            os.remove(_leftover)
    except PermissionError:
        pass  # Windows file lock — ignoré


# ── Résumé ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*52}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
