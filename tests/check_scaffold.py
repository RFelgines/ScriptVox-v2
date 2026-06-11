"""Scaffold verification — stdlib only. Run: python tests/check_scaffold.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

EXPECTED = [
    "ARCHITECTURE.md",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "app/__init__.py",
    "app/main.py",
    "app/config.py",
    "app/api/__init__.py",
    "app/api/routes/__init__.py",
    "app/core/__init__.py",
    "app/models/__init__.py",
    "app/schemas/__init__.py",
    "app/services/__init__.py",
    "app/services/epub/__init__.py",
    "app/services/llm/__init__.py",
    "app/services/tts/__init__.py",
    "app/workers/__init__.py",
    "data/.gitkeep",
    "tests/__init__.py",
]

missing = [p for p in EXPECTED if not (ROOT / p).exists()]

if missing:
    print("SCAFFOLD INCOMPLETE — missing entries:")
    for m in missing:
        print(f"  x {m}")
    sys.exit(1)

print("SCAFFOLD OK — all expected files and directories are present.")
