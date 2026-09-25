"""run_all.py — lance toutes les suites tests/check_phase*.py dans l'ordre numérique.

Chaque suite tourne dans son propre sous-processus (elles posent chacune leurs
variables d'environnement au chargement et ne peuvent donc pas cohabiter dans le même
interpréteur). Code de sortie != 0 si au moins une suite échoue.

Usage :
    python tests/run_all.py            # toutes les suites
    python tests/run_all.py 45 46      # seulement check_phase45 et check_phase46
"""
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
TIMEOUT_S = 600


def _number(path: Path) -> int:
    return int(re.search(r"check_phase(\d+)", path.name).group(1))


def main(argv: list[str]) -> int:
    suites = sorted(TESTS.glob("check_phase*.py"), key=_number)
    if argv:
        wanted = {int(a) for a in argv}
        suites = [s for s in suites if _number(s) in wanted]
    if not suites:
        print("Aucune suite trouvée.")
        return 1

    failures: list[str] = []
    for suite in suites:
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(suite)],
                cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S,
                encoding="utf-8", errors="replace",
            )
            code, out = proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as exc:
            code, out = 124, f"TIMEOUT après {TIMEOUT_S}s\n{exc.stdout or ''}"
        status = "OK  " if code == 0 else "FAIL"
        print(f"{status} {suite.name:<24} {time.time() - t0:6.1f}s")
        if code != 0:
            failures.append(suite.name)
            print("\n".join("      " + line for line in out.strip().splitlines()[-25:]))

    print(f"\n{len(suites) - len(failures)}/{len(suites)} suites OK")
    if failures:
        print("Échecs : " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
