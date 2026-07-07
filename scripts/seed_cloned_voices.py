"""
Seed cloned voices into the Voice table from data/voice_uploads/.

Run from the project root:
    .venv/Scripts/python scripts/seed_cloned_voices.py

Idempotent: skips voices whose voice_id already exists in DB.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlmodel import Session, create_engine, select

from app.config import get_settings
from app.core.enums import Gender, VoiceKind
from app.models.entities import Voice

UPLOADS_DIR = ROOT / "data" / "voice_uploads"

# Explicit mapping: filename (without extension, matching a file in UPLOADS_DIR)
# → (display name, gender). Populate this locally with your own reference
# recordings — left empty here since this file is committed to a public repo.
# Example:
#   "my_recording": ("My Voice", Gender.MALE),
KNOWN_VOICES: dict[str, tuple[str, Gender]] = {}


def _name_to_voice_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        existing = {v.voice_id for v in session.exec(select(Voice)).all()}

        added = 0
        skipped = 0

        for stem, (display_name, gender) in KNOWN_VOICES.items():
            mp3 = UPLOADS_DIR / f"{stem}.mp3"
            if not mp3.exists():
                print(f"  [!] Fichier introuvable : {mp3} - ignore")
                continue

            voice_id = _name_to_voice_id(stem)
            if voice_id in existing:
                print(f"  [=] {display_name} ({voice_id}) - deja en base")
                skipped += 1
                continue

            session.add(Voice(
                voice_id=voice_id,
                name=display_name,
                kind=VoiceKind.CLONED,
                gender=gender,
                reference_audio_path=str(mp3.resolve()),
            ))
            print(f"  [+] {display_name} ({voice_id}) - ajoute")
            added += 1

        session.commit()

    print(f"\n{added} voix ajoutée(s), {skipped} déjà présente(s).")


if __name__ == "__main__":
    main()
