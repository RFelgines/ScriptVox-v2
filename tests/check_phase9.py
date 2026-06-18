"""check_phase9.py — Roadmap Phase 8 (Casting), Étape 1: GET /voices.

Liste les voix logiques du catalogue (narrator + male/female/neutral) avec
genre et locale du provider TTS courant.
Run: .venv/Scripts/python tests/check_phase9.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Set env before any app import (edgetts default, no piper vars needed).
os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p9.db",
    "HUEY_DB_PATH": "./huey_test_p9.db",
    "TTS_PROVIDER": "edgetts",
})
os.environ.pop("EDGETTS_LOCALE", None)

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
    msg = f"    FAIL  {label}" + (f" — {detail}" if detail else "")
    print(msg)
    _errors.append(msg)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        ok(label)
    else:
        fail(label, detail)


# ── Imports ──────────────────────────────────────────────────────────────────

from app.config import get_settings  # noqa: E402
from app.core.enums import Gender  # noqa: E402
from app.main import app  # noqa: E402
from app.services.voice_assignment import (  # noqa: E402
    NARRATOR_VOICE_ID,
    VOICE_CATALOGUE,
    list_catalogue_voices,
)
from fastapi.testclient import TestClient  # noqa: E402

EXPECTED_IDS = [
    NARRATOR_VOICE_ID,
    "male_0", "male_1", "male_2",
    "female_0", "female_1", "female_2",
    "neutral_0", "neutral_1",
]
EXPECTED_GENDER = {
    NARRATOR_VOICE_ID: None,
    "male_0": Gender.MALE, "male_1": Gender.MALE, "male_2": Gender.MALE,
    "female_0": Gender.FEMALE, "female_1": Gender.FEMALE, "female_2": Gender.FEMALE,
    "neutral_0": Gender.NEUTRAL, "neutral_1": Gender.NEUTRAL,
}


# ── Section 1: list_catalogue_voices() déterministe + dédupliqué ──────────────

section("list_catalogue_voices(): ordre déterministe, narrator d'abord, dédup neutral")

voices = list_catalogue_voices()
ids = [vid for vid, _ in voices]

check("9 voix (narrator + 3 male + 3 female + 2 neutral)", len(voices) == 9,
      f"got {len(voices)}")
check("aucun doublon", len(ids) == len(set(ids)), f"ids={ids}")
check("narrator en premier", ids[0] == NARRATOR_VOICE_ID, f"ids[0]={ids[0]!r}")
check("ordre exact attendu", ids == EXPECTED_IDS, f"got {ids}")
check("narrator gender == None", voices[0][1] is None)
for vid, gender in voices:
    check(f"'{vid}' gender == {EXPECTED_GENDER[vid]!r}", gender == EXPECTED_GENDER[vid],
          f"got {gender!r}")

# neutral n'apparaît qu'une fois malgré UNKNOWN qui réutilise neutral_0/1
neutral_count = sum(1 for vid in ids if vid.startswith("neutral_"))
check("neutral listé une seule fois (pas via UNKNOWN)", neutral_count == 2,
      f"got {neutral_count}")


# ── Section 2: GET /voices — 200 + payload complet (provider edgetts) ─────────

section("GET /voices: 200, 9 voix, ids + genres corrects (provider=edgetts en-US)")

mock_edge = MagicMock()
mock_edge.tts_provider = "edgetts"
mock_edge.edgetts_locale = "en-US"
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app) as tc:
    resp = tc.get("/voices")
    check("status 200", resp.status_code == 200, f"got {resp.status_code}")
    data = resp.json()
    check("liste de 9 voix", isinstance(data, list) and len(data) == 9,
          f"got {len(data) if isinstance(data, list) else type(data)}")
    got_ids = [v["id"] for v in data]
    check("ids == EXPECTED_IDS", got_ids == EXPECTED_IDS, f"got {got_ids}")
    by_id = {v["id"]: v for v in data}
    for vid in EXPECTED_IDS:
        exp = EXPECTED_GENDER[vid]
        exp_val = exp.value if exp is not None else None
        check(f"'{vid}' gender == {exp_val!r}", by_id[vid]["gender"] == exp_val,
              f"got {by_id[vid]['gender']!r}")

app.dependency_overrides.clear()


# ── Section 3: GET /voices — locale du provider edgetts ──────────────────────

section("GET /voices: locale == 'en-US' sur chaque voix (provider=edgetts)")

app.dependency_overrides[get_settings] = lambda: mock_edge
with TestClient(app) as tc:
    data = tc.get("/voices").json()
    check("toutes les voix locale == 'en-US'",
          all(v["locale"] == "en-US" for v in data),
          f"locales={{v['locale'] for v in data}}")
app.dependency_overrides.clear()


# ── Section 4: GET /voices — locale custom fr-FR ─────────────────────────────

section("GET /voices: EDGETTS_LOCALE=fr-FR reflété (locale == 'fr-FR')")

mock_fr = MagicMock()
mock_fr.tts_provider = "edgetts"
mock_fr.edgetts_locale = "fr-FR"
app.dependency_overrides[get_settings] = lambda: mock_fr
with TestClient(app) as tc:
    data = tc.get("/voices").json()
    check("toutes les voix locale == 'fr-FR'",
          all(v["locale"] == "fr-FR" for v in data))
app.dependency_overrides.clear()


# ── Section 5: GET /voices — provider sans locale -> null ────────────────────

section("GET /voices: provider=elevenlabs -> locale null (autre branche)")

mock_eleven = MagicMock()
mock_eleven.tts_provider = "elevenlabs"
app.dependency_overrides[get_settings] = lambda: mock_eleven
with TestClient(app) as tc:
    resp = tc.get("/voices")
    check("status 200", resp.status_code == 200, f"got {resp.status_code}")
    data = resp.json()
    check("9 voix (catalogue inchangé)", len(data) == 9, f"got {len(data)}")
    check("toutes les voix locale == null",
          all(v["locale"] is None for v in data),
          f"locales={[v['locale'] for v in data]}")
app.dependency_overrides.clear()


# ── Section 6: cohérence catalogue (garde-fou) ────────────────────────────────

section("Garde-fou: les ids listés couvrent VOICE_CATALOGUE + narrator")

catalogue_ids = {NARRATOR_VOICE_ID}
for pool in VOICE_CATALOGUE.values():
    catalogue_ids.update(pool)
check("set(ids) == catalogue complet", set(ids) == catalogue_ids,
      f"diff={catalogue_ids ^ set(ids)}")


# ══════════════════════════════════════════════════════
# Phase 8 — Étape 2 : Traits de personnage enrichis
# ══════════════════════════════════════════════════════

from app.core.enums import AgeCategory  # noqa: E402
from app.models.entities import Character  # noqa: E402
from app.schemas.book import CharacterResponse  # noqa: E402
from app.services.llm.base import (  # noqa: E402
    CharacterData,
    SYSTEM_PROMPT,
    _parse_llm_json,
    _Span,
)

# ── Section 7: AgeCategory enum ──────────────────────────────────────────────

section("AgeCategory enum: valeurs attendues")

expected_ages = {"CHILD", "YOUNG_ADULT", "ADULT", "ELDER", "UNKNOWN"}
check("AgeCategory hérite str+Enum",
      issubclass(AgeCategory, str))
check("valeurs == attendues",
      {a.value for a in AgeCategory} == expected_ages,
      f"got {[a.value for a in AgeCategory]}")
check("UNKNOWN existe",
      hasattr(AgeCategory, "UNKNOWN"))

# ── Section 8: Character model — 3 nouveaux champs ───────────────────────────

section("Character model: age_category / tone / voice_quality présents avec bons défauts")

import inspect  # noqa: E402

char_fields = Character.model_fields
check("age_category dans Character", "age_category" in char_fields,
      f"fields={list(char_fields)}")
check("tone dans Character", "tone" in char_fields)
check("voice_quality dans Character", "voice_quality" in char_fields)
check("age_category défaut UNKNOWN",
      char_fields["age_category"].default == AgeCategory.UNKNOWN,
      f"got {char_fields['age_category'].default!r}")
check("tone défaut None",
      char_fields["tone"].default is None,
      f"got {char_fields['tone'].default!r}")
check("voice_quality défaut None",
      char_fields["voice_quality"].default is None,
      f"got {char_fields['voice_quality'].default!r}")

# ── Section 9: CharacterResponse — 3 nouveaux champs exposés ─────────────────

section("CharacterResponse: age_category / tone / voice_quality exposés")

resp_fields = CharacterResponse.model_fields
check("age_category dans CharacterResponse", "age_category" in resp_fields)
check("tone dans CharacterResponse", "tone" in resp_fields)
check("voice_quality dans CharacterResponse", "voice_quality" in resp_fields)

# instanciation avec les nouveaux champs
try:
    cr = CharacterResponse(
        id=1, name="Alice", gender=Gender.FEMALE,
        age_category=AgeCategory.YOUNG_ADULT,
        tone="warm", voice_quality="bright",
    )
    check("CharacterResponse instanciable avec nouveaux champs", True)
    check("age_category stocké", cr.age_category == AgeCategory.YOUNG_ADULT)
    check("tone stocké", cr.tone == "warm")
    check("voice_quality stocké", cr.voice_quality == "bright")
except Exception as e:
    check("CharacterResponse instanciable", False, str(e))

# ── Section 10: CharacterData dataclass — 3 nouveaux champs ──────────────────

section("CharacterData: age_category / tone / voice_quality présents avec bons défauts")

import dataclasses  # noqa: E402

cd_fields = {f.name: f for f in dataclasses.fields(CharacterData)}
check("age_category dans CharacterData", "age_category" in cd_fields)
check("tone dans CharacterData", "tone" in cd_fields)
check("voice_quality dans CharacterData", "voice_quality" in cd_fields)
check("age_category défaut UNKNOWN",
      cd_fields["age_category"].default == AgeCategory.UNKNOWN,
      f"got {cd_fields['age_category'].default!r}")
check("tone défaut None",
      cd_fields["tone"].default is None,
      f"got {cd_fields['tone'].default!r}")
check("voice_quality défaut None",
      cd_fields["voice_quality"].default is None,
      f"got {cd_fields['voice_quality'].default!r}")

# ── Section 11: _parse_llm_json — parsing des nouveaux traits ────────────────

section("_parse_llm_json: age_category / tone / voice_quality parsés depuis JSON LLM")

import json as _json  # noqa: E402

_spans_11 = [_Span(1, '"Hello."', True)]
_llm_json = _json.dumps({
    "characters": [
        {
            "name": "Alice",
            "description": "protagonist",
            "gender": "FEMALE",
            "age_category": "YOUNG_ADULT",
            "tone": "warm",
            "voice_quality": "bright",
            "voice_tone": "soft and hesitant",
        }
    ],
    "attributions": [{"index": 1, "character_name": "Alice"}],
})

try:
    result = _parse_llm_json(_llm_json, _spans_11)
    cd = result.characters[0]
    check("age_category == YOUNG_ADULT", cd.age_category == AgeCategory.YOUNG_ADULT,
          f"got {cd.age_category!r}")
    check("tone == 'warm'", cd.tone == "warm", f"got {cd.tone!r}")
    check("voice_quality == 'bright'", cd.voice_quality == "bright", f"got {cd.voice_quality!r}")
    check("voice_tone conservé", cd.voice_tone == "soft and hesitant", f"got {cd.voice_tone!r}")
except Exception as e:
    check("_parse_llm_json sans exception", False, str(e))

# ── Section 12: _parse_llm_json — fallback si champs absents (rétrocompat) ───

section("_parse_llm_json: fallback UNKNOWN/None si champs absents (rétrocompat)")

_spans_12 = [_Span(1, '"Hey."', True)]
_llm_json_old = _json.dumps({
    "characters": [
        {"name": "Bob", "gender": "MALE", "voice_tone": "deep"}
    ],
    "attributions": [{"index": 1, "character_name": "Bob"}],
})

try:
    result2 = _parse_llm_json(_llm_json_old, _spans_12)
    cd2 = result2.characters[0]
    check("age_category fallback UNKNOWN", cd2.age_category == AgeCategory.UNKNOWN,
          f"got {cd2.age_category!r}")
    check("tone fallback None", cd2.tone is None, f"got {cd2.tone!r}")
    check("voice_quality fallback None", cd2.voice_quality is None, f"got {cd2.voice_quality!r}")
except Exception as e:
    check("_parse_llm_json rétrocompat sans exception", False, str(e))

# ── Section 13: SYSTEM_PROMPT mentionne les nouveaux champs ──────────────────

section("SYSTEM_PROMPT: age_category / tone / voice_quality mentionnés")

check("age_category dans SYSTEM_PROMPT", "age_category" in SYSTEM_PROMPT)
check("tone dans SYSTEM_PROMPT", "tone" in SYSTEM_PROMPT)
check("voice_quality dans SYSTEM_PROMPT", "voice_quality" in SYSTEM_PROMPT)
check("CHILD|YOUNG_ADULT dans SYSTEM_PROMPT", "YOUNG_ADULT" in SYSTEM_PROMPT)


# ══════════════════════════════════════════════════════
# Phase 8 — Étape 3 : VoiceRegistry trait-based
# ══════════════════════════════════════════════════════

from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel, Session, create_engine, select  # noqa: E402

from app.models.entities import Book  # noqa: E402
from app.services.voice_assignment import (  # noqa: E402
    _CATALOGUE_META,
    _score_voice,
    assign_voices,
)


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _make_book(session) -> int:
    book = Book(title="Test", source_path="/tmp/t.epub")
    session.add(book)
    session.flush()
    return book.id


def _char(book_id, name, gender, age=AgeCategory.UNKNOWN, tone=None, quality=None):
    return Character(
        book_id=book_id, name=name, gender=gender,
        age_category=age, tone=tone, voice_quality=quality,
    )


# ── Section 14: _score_voice — MALE ADULT warm deep -> male_0 (score max) ────

section("_score_voice: MALE ADULT 'warm' 'deep' -> male_0 meilleur score (8)")

_c14 = _char(1, "X", Gender.MALE, AgeCategory.ADULT, "warm", "deep")
_scores14 = {vid: _score_voice(_c14, vid) for vid in _CATALOGUE_META}

check("male_0 score == 8", _scores14["male_0"] == 8, f"got {_scores14['male_0']}")
check("male_0 > tous les autres",
      all(_scores14["male_0"] >= v for v in _scores14.values()),
      f"scores={_scores14}")
check("narrator score < 0", _scores14["narrator"] < 0)
check("female_* score < male_0 (genre different -> pas de bonus genre)",
      all(_scores14[vid] < _scores14["male_0"] for vid in ["female_0", "female_1", "female_2"]),
      f"female scores={[_scores14[v] for v in ['female_0','female_1','female_2']]} male_0={_scores14['male_0']}")


# ── Section 15: _score_voice — MALE YOUNG_ADULT gentle smooth -> male_1 ──────

section("_score_voice: MALE YOUNG_ADULT 'gentle' 'smooth' -> male_1 meilleur (8)")

_c15 = _char(1, "X", Gender.MALE, AgeCategory.YOUNG_ADULT, "gentle", "smooth")
_scores15 = {vid: _score_voice(_c15, vid) for vid in _CATALOGUE_META}

check("male_1 score == 8", _scores15["male_1"] == 8, f"got {_scores15['male_1']}")
check("male_1 > male_0 et male_2",
      _scores15["male_1"] > _scores15["male_0"] and _scores15["male_1"] > _scores15["male_2"],
      f"male_0={_scores15['male_0']} male_1={_scores15['male_1']} male_2={_scores15['male_2']}")


# ── Section 16: assign_voices — assignation optimale par traits d'âge ────────

section("assign_voices: 3 personnages MALE avec âges distincts -> voix optimales")

_eng16 = _make_engine()
with Session(_eng16) as _s16:
    _bid16 = _make_book(_s16)
    _s16.add_all([
        _char(_bid16, "Alice", Gender.MALE, AgeCategory.YOUNG_ADULT),  # -> male_1
        _char(_bid16, "Bob",   Gender.MALE, AgeCategory.ADULT),         # -> male_0
        _char(_bid16, "Carl",  Gender.MALE, AgeCategory.ELDER),         # -> male_2
    ])
    _s16.commit()
    assign_voices(_bid16, _s16)

with Session(_eng16) as _s16b:
    _chars16 = {
        c.name: c.voice_id
        for c in _s16b.exec(select(Character).where(Character.book_id == _bid16)).all()
    }
check("Alice (YOUNG_ADULT) -> male_1", _chars16.get("Alice") == "male_1",
      f"got {_chars16.get('Alice')!r}")
check("Bob   (ADULT)       -> male_0", _chars16.get("Bob") == "male_0",
      f"got {_chars16.get('Bob')!r}")
check("Carl  (ELDER)       -> male_2", _chars16.get("Carl") == "male_2",
      f"got {_chars16.get('Carl')!r}")
check("voix toutes distinctes", len(set(_chars16.values())) == 3)


# ── Section 17: idempotence — 2e appel ne ré-assigne pas ─────────────────────

section("assign_voices: idempotence — 2e appel conserve les voix assignées")

with Session(_eng16) as _s17:
    assign_voices(_bid16, _s17)

with Session(_eng16) as _s17b:
    _chars17 = {
        c.name: c.voice_id
        for c in _s17b.exec(select(Character).where(Character.book_id == _bid16)).all()
    }
check("Alice inchangée après 2e appel", _chars17.get("Alice") == _chars16.get("Alice"))
check("Bob inchangé",                   _chars17.get("Bob")   == _chars16.get("Bob"))
check("Carl inchangé",                  _chars17.get("Carl")  == _chars16.get("Carl"))


# ── Section 18: wrap-around — plus de persos que de voix MALE ────────────────

section("assign_voices: wrap-around — 4e perso MALE quand les 3 voix sont prises")

_eng18 = _make_engine()
with Session(_eng18) as _s18:
    _bid18 = _make_book(_s18)
    _s18.add_all([
        _char(_bid18, "A", Gender.MALE, AgeCategory.YOUNG_ADULT),
        _char(_bid18, "B", Gender.MALE, AgeCategory.ADULT),
        _char(_bid18, "C", Gender.MALE, AgeCategory.ELDER),
        _char(_bid18, "D", Gender.MALE),  # 4e — wrap-around
    ])
    _s18.commit()
    assign_voices(_bid18, _s18)

with Session(_eng18) as _s18b:
    _vids18 = [
        c.voice_id
        for c in _s18b.exec(
            select(Character).where(Character.book_id == _bid18).order_by(Character.name)
        ).all()
    ]
check("4 voix assignées (pas d'erreur)", len(_vids18) == 4 and all(v is not None for v in _vids18),
      f"got {_vids18}")
check("voix D non nulle", _vids18[3] is not None)
check("voix D != narrator", _vids18[3] != NARRATOR_VOICE_ID)


# ── Section 19: narrator jamais attribué à un personnage ─────────────────────

section("assign_voices: 'narrator' jamais attribué (même si pool épuisé)")

with Session(_eng18) as _s19:
    _all_vids19 = [
        c.voice_id
        for c in _s19.exec(select(Character).where(Character.book_id == _bid18)).all()
    ]
check("aucun perso n'a 'narrator'",
      NARRATOR_VOICE_ID not in _all_vids19,
      f"got {_all_vids19}")


# ── Section 20: déterminisme — deux books identiques -> même assignation ───────

section("assign_voices: déterminisme — deux books identiques -> même résultat")

_eng20 = _make_engine()
with Session(_eng20) as _s20:
    _bid20a = _make_book(_s20)
    _bid20b = _make_book(_s20)
    for bid in (_bid20a, _bid20b):
        _s20.add_all([
            _char(bid, "Alice", Gender.FEMALE, AgeCategory.YOUNG_ADULT, "gentle", "bright"),
            _char(bid, "Bob",   Gender.MALE,   AgeCategory.ADULT,       "warm",   "deep"),
        ])
    _s20.commit()
    assign_voices(_bid20a, _s20)
    assign_voices(_bid20b, _s20)

with Session(_eng20) as _s20b:
    def _vmap(bid):
        return {
            c.name: c.voice_id
            for c in _s20b.exec(select(Character).where(Character.book_id == bid)).all()
        }
    _m20a, _m20b = _vmap(_bid20a), _vmap(_bid20b)

check("Alice même voix dans les deux books", _m20a.get("Alice") == _m20b.get("Alice"),
      f"{_m20a.get('Alice')!r} vs {_m20b.get('Alice')!r}")
check("Bob même voix dans les deux books",   _m20a.get("Bob")   == _m20b.get("Bob"),
      f"{_m20a.get('Bob')!r} vs {_m20b.get('Bob')!r}")


# ══════════════════════════════════════════════════════
# Phase 8 — Étape 4 : PATCH /characters/{id}
# ══════════════════════════════════════════════════════

from app.core.db import get_session  # noqa: E402
from app.schemas.book import CharacterUpdate  # noqa: E402

# Shared in-memory DB for Étape 4 sections
_eng_s4 = _make_engine()

with Session(_eng_s4) as _s4_setup:
    _book_s4 = Book(title="Casting Test", source_path="/tmp/cast.epub")
    _s4_setup.add(_book_s4)
    _s4_setup.flush()
    _char_s4 = Character(
        book_id=_book_s4.id, name="Alice",
        gender=Gender.FEMALE, age_category=AgeCategory.YOUNG_ADULT,
        voice_id="female_0",
    )
    _s4_setup.add(_char_s4)
    _s4_setup.commit()
    _char_s4_id = _char_s4.id
    _book_s4_id = _book_s4.id


def _s4_get_session():
    with Session(_eng_s4) as s:
        yield s


# ── Section 21: PATCH valide -> 200 + voice_id mis à jour ────────────────────

section("PATCH /characters/{id}: voice_id valide -> 200 + CharacterResponse mis à jour")

app.dependency_overrides[get_session] = _s4_get_session
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app) as tc:
    resp = tc.patch(f"/characters/{_char_s4_id}", json={"voice_id": "female_2"})
    check("status 200", resp.status_code == 200, f"got {resp.status_code}: {resp.text}")
    data = resp.json()
    check("voice_id == 'female_2'", data.get("voice_id") == "female_2",
          f"got {data.get('voice_id')!r}")
    check("id correct", data.get("id") == _char_s4_id)

app.dependency_overrides.clear()


# ── Section 22: autres champs inchangés après PATCH ──────────────────────────

section("PATCH /characters/{id}: champs non patchés restes inchangés")

app.dependency_overrides[get_session] = _s4_get_session
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app) as tc:
    data = tc.patch(f"/characters/{_char_s4_id}", json={"voice_id": "female_1"}).json()
    check("name inchangé", data.get("name") == "Alice", f"got {data.get('name')!r}")
    check("gender inchangé", data.get("gender") == Gender.FEMALE.value,
          f"got {data.get('gender')!r}")
    check("age_category inchangé", data.get("age_category") == AgeCategory.YOUNG_ADULT.value,
          f"got {data.get('age_category')!r}")

app.dependency_overrides.clear()


# ── Section 23: 404 si character inexistant ───────────────────────────────────

section("PATCH /characters/{id}: 404 si character inexistant")

app.dependency_overrides[get_session] = _s4_get_session
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app, raise_server_exceptions=False) as tc:
    resp = tc.patch("/characters/99999", json={"voice_id": "female_0"})
    check("status 404", resp.status_code == 404, f"got {resp.status_code}")

app.dependency_overrides.clear()


# ── Section 24: 422 si voice_id == 'narrator' (réservé) ──────────────────────

section("PATCH /characters/{id}: 422 si voice_id == 'narrator' (réservé à la narration)")

app.dependency_overrides[get_session] = _s4_get_session
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app, raise_server_exceptions=False) as tc:
    resp = tc.patch(f"/characters/{_char_s4_id}", json={"voice_id": "narrator"})
    check("status 422", resp.status_code == 422, f"got {resp.status_code}")

app.dependency_overrides.clear()


# ── Section 25: 422 si voice_id inconnu du catalogue ─────────────────────────

section("PATCH /characters/{id}: 422 si voice_id inconnu du catalogue")

app.dependency_overrides[get_session] = _s4_get_session
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app, raise_server_exceptions=False) as tc:
    resp = tc.patch(f"/characters/{_char_s4_id}", json={"voice_id": "ghost_voice"})
    check("status 422", resp.status_code == 422, f"got {resp.status_code}")

app.dependency_overrides.clear()


# ── Section 26: idempotence — deux PATCHes successifs ────────────────────────

section("PATCH /characters/{id}: idempotence — deux PATCHes meme valeur -> 200 x2")

app.dependency_overrides[get_session] = _s4_get_session
app.dependency_overrides[get_settings] = lambda: mock_edge

with TestClient(app) as tc:
    r1 = tc.patch(f"/characters/{_char_s4_id}", json={"voice_id": "female_0"})
    r2 = tc.patch(f"/characters/{_char_s4_id}", json={"voice_id": "female_0"})
    check("1er PATCH -> 200", r1.status_code == 200, f"got {r1.status_code}")
    check("2e PATCH -> 200", r2.status_code == 200, f"got {r2.status_code}")
    check("voice_id == 'female_0' apres les deux",
          r2.json().get("voice_id") == "female_0")

app.dependency_overrides.clear()


# ── Rapport ───────────────────────────────────────────────────────────────────

print(f"\n{'='*52}")
if _errors:
    print(f"FAIL — {len(_errors)} erreur(s) :")
    for e in _errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("OK — Toutes les sections passent (Phase 8 Étapes 1 + 2 + 3).")
