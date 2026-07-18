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
    "DATA_DIR": "./data_test",
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


def _pre_alembic_engine(tmpdir: Path, name: str = "test.db"):
    """Un moteur dont le schéma est l'image EXACTE de la seule migration
    baseline (0a0a59b228cc), sans table alembic_version -- la forme réelle de
    tout scriptvox.db créé avant l'adoption d'Alembic (2026-07-02).

    Volontairement PAS SQLModel.metadata.create_all() sur les modèles actuels :
    ceux-ci contiennent déjà chapter.priority/cancel_requested et
    app_setting.preferred_language (migrations 2 et 3), ce qu'aucune vraie
    vieille base ne peut avoir -- un tel fixture ne peut pas détecter un stamp
    erroné à head au lieu de la baseline (régression audit 2026-07-11, cf.
    section 8)."""
    from alembic import command
    from alembic.config import Config

    eng = _fresh_file_engine(tmpdir, name)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", eng.url.render_as_string(hide_password=False))
    command.upgrade(cfg, "0a0a59b228cc")
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP TABLE alembic_version")
    return eng


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
    _book_cols2 = {c["name"] for c in inspect(_eng2).get_columns("book")}
    check("colonne 'book.failed_stage' créée (migration 4, audit 2026-07-11 T2.3)",
          "failed_stage" in _book_cols2, f"got {_book_cols2}")
    check("historique alembic présent ('alembic_version')", "alembic_version" in _tables2)
    _eng2.dispose()


# ── 3. Base "pré-Alembic" (schéma baseline) -> auto-tamponnée, pas de crash ──
section("Base pré-Alembic (schéma baseline, sans historique) : auto-tamponnée sans crash")
with tempfile.TemporaryDirectory() as _tmp3:
    _eng3 = _pre_alembic_engine(Path(_tmp3))
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
    _eng4 = _pre_alembic_engine(Path(_tmp4))

    # INSERT SQL brut limité aux colonnes baseline (PAS Session.add(Book(...)) :
    # l'ORM construit l'INSERT depuis le modèle SQLModel ACTUEL, qui inclut
    # désormais book.failed_stage -- ajouté par la migration 4, absente du
    # schéma baseline de ce fixture -- ce qui échouerait sur une vraie vieille
    # base. Even principe que _pre_alembic_engine : rester fidèle au schéma
    # RÉEL d'une base pré-migration 4 (audit 2026-07-11, T2.3).
    with _eng4.begin() as _conn4:
        _conn4.exec_driver_sql(
            "INSERT INTO book (title, author, source_path, status, progress, "
            "audio_path, mp3_path, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "Mon Vrai Livre", "Un Vrai Auteur", "/data/1/original.epub", "DONE", 100.0,
                "/data/1/book.wav", "/data/1/book.mp3",
                "2026-07-02 00:00:00", "2026-07-02 00:00:00",
            ),
        )
        _book4_id = _conn4.exec_driver_sql(
            "SELECT id FROM book WHERE title = 'Mon Vrai Livre'"
        ).scalar_one()

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
    _eng7 = _pre_alembic_engine(Path(_tmp7))

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


# ── 8. RÉGRESSION (audit 2026-07-11) : le stamp doit cibler la BASELINE, ─────
# pas "head" -- sans quoi les migrations 2 et 3 ne sont jamais appliquées à une
# vraie vieille base (auto-tamponnée "à jour" alors que chapter.priority/
# cancel_requested et app_setting.preferred_language lui manquent encore).
# _pre_alembic_engine (contrairement à l'ancien fixture create_all() sur les
# modèles actuels qu'utilisaient les sections 3/4/7 avant ce lot) reproduit
# fidèlement ce cas : lui seul peut détecter un stamp erroné à head.
section("RÉGRESSION : une base pré-Alembic au schéma RÉELLEMENT ancien reçoit les migrations manquantes")
with tempfile.TemporaryDirectory() as _tmp8:
    _eng8 = _pre_alembic_engine(Path(_tmp8))

    # INSERT SQL brut, même raison qu'en section 4 : le modèle Book actuel
    # inclut failed_stage (migration 4), absente du schéma baseline ici.
    with _eng8.begin() as _conn8:
        _conn8.exec_driver_sql(
            "INSERT INTO book (title, source_path, status, progress, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "Vieux Livre Pré-Migration", "/data/2/x.epub", "DONE", 100.0,
                "2026-07-02 00:00:00", "2026-07-02 00:00:00",
            ),
        )
        _book8_id = _conn8.exec_driver_sql(
            "SELECT id FROM book WHERE title = 'Vieux Livre Pré-Migration'"
        ).scalar_one()

    _cols_before8 = {c["name"] for c in inspect(_eng8).get_columns("chapter")}
    check("schéma baseline confirmé : chapter.priority absente avant fix",
          "priority" not in _cols_before8, f"got {_cols_before8}")

    _ensure_schema(_eng8)  # doit stamper la BASELINE puis upgrade -- pas stamper head directement

    _cols_chapter8 = {c["name"] for c in inspect(_eng8).get_columns("chapter")}
    check("chapter.priority ajoutée après _ensure_schema (migration 9e2bc226e2fa appliquée)",
          "priority" in _cols_chapter8, f"got {_cols_chapter8}")
    check("chapter.cancel_requested ajoutée",
          "cancel_requested" in _cols_chapter8, f"got {_cols_chapter8}")
    _cols_setting8 = {c["name"] for c in inspect(_eng8).get_columns("app_setting")}
    check("app_setting.preferred_language ajoutée (migration 29e226c24b2d appliquée)",
          "preferred_language" in _cols_setting8, f"got {_cols_setting8}")
    _cols_book8 = {c["name"] for c in inspect(_eng8).get_columns("book")}
    check("book.failed_stage ajoutée (migration 67521bdee0e5 appliquée)",
          "failed_stage" in _cols_book8, f"got {_cols_book8}")

    with Session(_eng8) as _s:
        _book8_after = _s.get(Book, _book8_id)
        check("le livre pré-existant survit intact",
              _book8_after is not None and _book8_after.title == "Vieux Livre Pré-Migration")

    try:
        _ensure_schema(_eng8)
        ok("2e appel idempotent après le fix (déjà à head, upgrade no-op)")
    except Exception as exc:
        fail("2e appel a levé une exception", f"{type(exc).__name__}: {exc}")

    _eng8.dispose()


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
