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


# ── Rapport ───────────────────────────────────────────────────────────────────

print(f"\n{'='*52}")
if _errors:
    print(f"FAIL — {len(_errors)} erreur(s) :")
    for e in _errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("OK — Toutes les sections passent (Phase 8 Étape 1: GET /voices).")
