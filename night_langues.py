"""Chantier B — analyse LLM + génération audio d'un chapitre, en plusieurs langues.

Objectif : vérifier de bout en bout que la chaîne ScriptVox tient sur des livres
de langues différentes — détection de la langue, analyse des personnages,
attribution des voix, génération audio — et consigner tout ce qui casse.

Volontairement UN SEUL chapitre par livre.

Rien n'est supprimé : les livres déjà analysés sont réutilisés (REUTILISER) et
on génère un chapitre encore jamais généré ; les autres sont importés à neuf.
Le moteur TTS est basculé à chaud via PATCH /settings, puis restauré à la fin.

v2 (2026-09-27) — corrections après le premier passage :
  - la génération d'UN chapitre ne change pas le statut du LIVRE (il reste
    ANALYZED) : on attend désormais le statut du CHAPITRE. Avant, le script
    concluait au bout de 4 s et l'audio répondait 409 (pas encore prêt) ;
  - POST /books lance déjà l'analyse : le POST /analyze de la v1 en enfilait une
    seconde, et chaque durée d'analyse mesurée en cumulait deux ;
  - un segment sans rien à prononcer (« ) », « ...... ») faisait échouer le
    chapitre avec EdgeTTS — corrigé dans l'appli (audio/chapter.py) ;
  - Book.language n'est renseigné qu'à l'analyse (dc:language lu au parsing) :
    on le lit après l'analyse, plus juste après l'import ;
  - vérification des takes sur disque (durée, silence) en plus du WAV du chapitre ;
  - trace de progression de l'analyse (durée par chapitre) pour le diagnostic du
    timeout italien.

Usage : python night_langues.py
"""
from __future__ import annotations

import array
import io
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import requests

API = "http://localhost:8000"
RACINE = Path(r"D:\Documents\Dev\ScriptVox")
DATA = RACINE / "data_demo"
RAPPORT = RACINE / "SCRIPTVOX-NIGHT-REPORT.md"
AUDIO_OUT = Path.home() / "Documents" / "ScriptVox-nuit-audio"
DL = Path.home() / "Downloads"

TIMEOUT_ANALYSE = 4 * 3600
TIMEOUT_GENERATION = 7200

LIVRES = [
    ("fr", DL / "daudet-lettres-de-mon-moulin.epub", "Daudet — Lettres de mon moulin"),
    ("en", DL / "carroll-alice-in-wonderland.epub", "Carroll — Alice in Wonderland"),
    ("es", DL / "scriptvox-langues" / "es-55514.epub", "Pardo Bazán — Cuentos de amor"),
    ("de", DL / "scriptvox-langues" / "de-22367.epub", "Kafka — Die Verwandlung"),
    ("it", DL / "scriptvox-langues" / "it-52484.epub", "Collodi — Pinocchio"),
]

# Livres déjà analysés au premier passage, dont l'analyse reste valable : les
# profils fr/en/es n'ont pas changé. de et it sont réimportés, car leur
# segmentation dépend des nouveaux profils (avant : repli sur le français).
REUTILISER = {"fr": 1, "en": 2, "es": 3, "de": 6}  # 6 = Kafka réimporté avec DE_PROFILE


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def livre(book_id: int) -> dict:
    r = requests.get(f"{API}/books/{book_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def attendre_livre(book_id: int, etats_fin: set[str], limite: int,
                   trace: list | None = None) -> tuple[str, dict]:
    """Interroge le livre jusqu'à un état terminal ou expiration. Si *trace* est
    fourni, y consigne chaque changement d'avancement (t, progress, stage)."""
    t0 = time.time()
    dernier = None
    while time.time() - t0 < limite:
        b = livre(book_id)
        etat = b.get("status", "")
        cle = (etat, round(b.get("progress") or 0, 3), b.get("stage"))
        if cle != dernier:
            log(f"    état : {etat} progress={cle[1]} stage={cle[2]} {b.get('error_message') or ''}")
            if trace is not None:
                trace.append({"t": round(time.time() - t0), "progress": cle[1], "stage": cle[2],
                              "msg": b.get("error_message")})
            dernier = cle
        if etat in etats_fin:
            return etat, b
        time.sleep(5)
    return "TIMEOUT", livre(book_id)


def attendre_chapitre(book_id: int, pos: int, limite: int) -> tuple[str, dict]:
    t0 = time.time()
    dernier = ""
    while time.time() - t0 < limite:
        chaps = requests.get(f"{API}/books/{book_id}/chapters", timeout=60).json()
        c = next(c for c in chaps if c["position"] == pos)
        if c["status"] != dernier:
            log(f"    chapitre {pos} : {c['status']}")
            dernier = c["status"]
        if c["status"] in ("DONE", "FAILED"):
            return c["status"], c
        time.sleep(5)
    return "TIMEOUT", {}


def analyse_wav(data: bytes) -> dict:
    with wave.open(io.BytesIO(data)) as w:
        n, sr, sw, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    pic = max((abs(x) for x in a), default=0)
    rms = (sum(x * x for x in a) / len(a)) ** 0.5 if a else 0.0
    return {
        "duree_s": round(n / sr, 1), "hz": sr, "canaux": ch,
        "pic": pic, "rms": round(rms, 1), "silencieux": pic < 100,
    }


def verifier_takes(book_id: int, depuis: float) -> dict:
    """Takes WAV écrits pendant la génération : nombre, durée totale, silencieux."""
    dossier = DATA / str(book_id) / "takes"
    fichiers = [f for f in dossier.glob("*.wav") if f.stat().st_mtime >= depuis - 1] if dossier.exists() else []
    total, silencieux, vides, illisibles = 0.0, 0, 0, 0
    for f in fichiers:
        try:
            a = analyse_wav(f.read_bytes())
            total += a["duree_s"]
            if a["duree_s"] == 0:
                vides += 1  # segment sans rien à prononcer : silence nul voulu (audio/chapter.py)
            else:
                silencieux += a["silencieux"]
        except Exception:  # noqa: BLE001
            illisibles += 1
    return {"nombre": len(fichiers), "duree_totale_s": round(total, 1),
            "silencieux": silencieux, "vides_voulus": vides, "illisibles": illisibles}


def importer(chemin: Path, res: dict) -> int | None:
    with chemin.open("rb") as fh:
        r = requests.post(f"{API}/books", files={"file": (chemin.name, fh, "application/epub+zip")},
                          timeout=300)
    if r.status_code != 202:
        res["erreurs"].append(f"POST /books -> {r.status_code} : {r.text[:300]}")
        return None
    return r.json()["id"]


def traiter(code: str, chemin: Path, libelle: str) -> dict:
    res: dict = {"langue_attendue": code, "livre": libelle, "fichier": chemin.name, "erreurs": []}
    t0 = time.time()

    book_id = REUTILISER.get(code)
    if book_id is not None and livre(book_id).get("status") == "ANALYZED":
        log(f"[{code}] réutilisation du livre {book_id} (déjà analysé)")
        res["book_id"], res["reutilise"] = book_id, True
        b = livre(book_id)
        res["analyse_etat"] = b["status"]
    else:
        if not chemin.exists():
            res["erreurs"].append(f"EPUB introuvable : {chemin}")
            return res
        log(f"[{code}] import de {chemin.name}")
        book_id = importer(chemin, res)
        if book_id is None:
            return res
        res["book_id"], res["reutilise"] = book_id, False

        # POST /books enfile DÉJÀ l'analyse (books.py upload_book -> analyze_book). La v1
        # attendait PENDING puis relançait POST /analyze : une seconde analyse complète
        # s'enfilait derrière la première, et la durée mesurée cumulait les deux.
        log(f"[{code}] analyse LLM (lancée par l'import)")
        t_an = time.time()
        trace: list = []
        etat, b = attendre_livre(book_id, {"ANALYZED", "FAILED"}, TIMEOUT_ANALYSE, trace)
        res["analyse_etat"] = etat
        res["analyse_duree_s"] = round(time.time() - t_an)
        res["analyse_trace"] = trace
        if etat != "ANALYZED":
            res["erreurs"].append(f"analyse terminée en état {etat} — {b.get('failed_stage')}")
            return res

    # La langue n'est connue qu'après l'analyse (dc:language lu au parsing).
    res["langue_detectee"] = b.get("language")
    res["langue_correcte"] = (b.get("language") or "").lower().startswith(code)

    chaps = requests.get(f"{API}/books/{book_id}/chapters", timeout=60).json()
    perso = requests.get(f"{API}/books/{book_id}/characters", timeout=60).json()
    res["chapitres"] = len(chaps)
    res["chapitres_inclus"] = sum(1 for c in chaps if c.get("included", True))
    res["personnages"] = len(perso)
    res["personnages_sans_voix"] = sum(1 for p in perso if not p.get("voice_id"))
    res["voix_distinctes"] = len({p.get("voice_id") for p in perso if p.get("voice_id")})
    res["exemples_personnages"] = [{"nom": p.get("name"), "voix": p.get("voice_id")} for p in perso[:6]]

    # Un chapitre inclus jamais généré : on ne régénère pas (et donc n'écrase pas)
    # l'audio d'un chapitre déjà DONE.
    # Un chapitre en échec est repris en priorité : c'est la preuve qu'un correctif marche.
    echecs = [c for c in chaps if c.get("included", True) and c["status"] == "FAILED"]
    candidats = [c for c in chaps if c.get("included", True) and c["status"] == "PENDING"]
    if not echecs and not candidats:
        res["erreurs"].append("aucun chapitre inclus à générer")
        return res
    # sinon ni le tout premier (souvent liminaire), ni la fin
    cible = echecs[0] if echecs else candidats[len(candidats) // 3]
    pos = cible["position"]
    res["chapitre_genere"] = {"position": pos, "titre": cible.get("title")}

    log(f"[{code}] génération du chapitre {pos} ({cible.get('title')})")
    t_gen = time.time()
    rg = requests.post(f"{API}/books/{book_id}/chapters/{pos}/generate", timeout=60)
    if rg.status_code >= 400:
        res["erreurs"].append(f"POST generate -> {rg.status_code} : {rg.text[:300]}")
        return res
    etat, c = attendre_chapitre(book_id, pos, TIMEOUT_GENERATION)
    res["generation_etat"] = etat
    res["generation_duree_s"] = round(time.time() - t_gen)
    if etat != "DONE":
        res["erreurs"].append(f"génération terminée en état {etat} — {c.get('error_message')}")
        return res

    res["takes"] = verifier_takes(book_id, t_gen)
    if res["takes"]["nombre"] == 0:
        res["erreurs"].append("aucun take écrit sur disque")
    if res["takes"]["silencieux"] or res["takes"]["illisibles"]:
        res["erreurs"].append(f"takes silencieux/illisibles : {res['takes']}")

    segs = requests.get(f"{API}/books/{book_id}/chapters/{pos}/segments", timeout=60).json()
    res["segments"] = {
        "total": len(segs),
        "dialogues": sum(1 for s in segs if s.get("segment_type") == "DIALOGUE"),
        "sans_duree": sum(1 for s in segs if not s.get("duration_ms")),
        "voix": sorted({s.get("voice_id") or "narrator" for s in segs}),
    }

    ra2 = requests.get(f"{API}/books/{book_id}/chapters/{pos}/audio", timeout=300)
    if ra2.status_code != 200:
        res["erreurs"].append(f"audio indisponible -> {ra2.status_code} : {ra2.text[:200]}")
    else:
        AUDIO_OUT.mkdir(parents=True, exist_ok=True)
        dest = AUDIO_OUT / f"{code}-{book_id}-ch{pos}.wav"
        dest.write_bytes(ra2.content)
        try:
            res["audio"] = analyse_wav(ra2.content)
            res["audio"]["fichier"] = str(dest)
            if res["audio"]["silencieux"]:
                res["erreurs"].append("AUDIO SILENCIEUX (pic < 100)")
            ratio = res["generation_duree_s"] / max(res["audio"]["duree_s"], 0.1)
            res["audio"]["ratio_temps_reel"] = round(ratio, 2)
        except Exception as exc:  # noqa: BLE001
            res["erreurs"].append(f"audio illisible : {type(exc).__name__} {exc}")

    res["duree_totale_s"] = round(time.time() - t0)
    return res


def main() -> int:
    log("=== chantier B : analyse + génération multilingue (v2) ===")
    reglages = requests.get(f"{API}/settings", timeout=30).json()
    origine = reglages.get("preferred_tts_provider")
    log(f"moteur TTS : défaut={reglages['default_tts_provider']} préféré={origine} -> bascule sur edgetts")
    requests.patch(f"{API}/settings", json={"preferred_tts_provider": "edgetts"}, timeout=30).raise_for_status()

    # `python night_langues.py en` : ne relance que les langues citées, et fusionne avec
    # les résultats du passage précédent pour les autres.
    seulement = set(sys.argv[1:])
    precedents: dict[str, dict] = {}
    fichier_res = RACINE / "night_langues_resultats.json"
    if seulement and fichier_res.exists():
        precedents = {r["langue_attendue"]: r for r in json.loads(fichier_res.read_text(encoding="utf-8"))}
    resultats = []
    try:
        for code, chemin, libelle in LIVRES:
            if seulement and code not in seulement:
                if code in precedents:
                    resultats.append(precedents[code])
                continue
            try:
                resultats.append(traiter(code, chemin, libelle))
            except Exception as exc:  # noqa: BLE001
                import traceback
                resultats.append({"langue_attendue": code, "livre": libelle,
                                  "erreurs": [f"{type(exc).__name__}: {exc}",
                                              traceback.format_exc()[-1500:]]})
            log(f"[{code}] terminé\n")
            # Sauvegarde intermédiaire : un arrêt en cours de route garde les résultats.
            fichier_res.write_text(
                json.dumps(resultats, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        requests.patch(f"{API}/settings", json={"preferred_tts_provider": origine}, timeout=30)
        log(f"moteur TTS restauré : {origine}")

    ecrire_rapport(resultats)
    log(f"rapport : {RAPPORT}")
    return 0


def ecrire_rapport(res: list[dict]) -> None:
    L = [
        "# ScriptVox — rapport de nuit (chantier B : multilingue)",
        "",
        f"Généré le {datetime.now():%Y-%m-%d %H:%M} (v2). Un seul chapitre par livre.",
        "Moteur TTS : edgetts (basculé à chaud, réglage d'origine restauré ensuite).",
        "",
        "## Synthèse",
        "",
        "| langue | détectée | analyse | perso. | chapitres | génération | takes | audio | ratio | erreurs |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in res:
        a = r.get("audio") or {}
        tk = r.get("takes") or {}
        an = "réutilisée" if r.get("reutilise") else f"{r.get('analyse_duree_s', '—')}s"
        L.append(
            f"| {r.get('langue_attendue')} | {r.get('langue_detectee') or '—'}"
            f"{' ✓' if r.get('langue_correcte') else ' ✗'} | {r.get('analyse_etat') or '—'} ({an})"
            f" | {r.get('personnages', '—')} | {r.get('chapitres_inclus', '—')}/{r.get('chapitres', '—')}"
            f" | {r.get('generation_etat') or '—'} ({r.get('generation_duree_s', '—')}s)"
            f" | {tk.get('nombre', '—')} ({tk.get('duree_totale_s', '—')}s)"
            f" | {a.get('duree_s', '—')}s{' SILENCE' if a.get('silencieux') else ''}"
            f" | {a.get('ratio_temps_reel', '—')}x | {len(r.get('erreurs', []))} |"
        )
    L += ["", "## Détail par livre", ""]
    for r in res:
        L += [f"### {r.get('livre')} (`{r.get('langue_attendue')}`)", "",
              "```json", json.dumps(r, ensure_ascii=False, indent=2), "```", ""]
    L += ["## Bugs et points à trancher", ""]
    bugs = [(r.get("livre"), e) for r in res for e in r.get("erreurs", [])]
    if bugs:
        for livre_, e in bugs:
            L.append(f"- **{livre_}** : {e.splitlines()[0][:300]}")
    else:
        L.append("- aucun échec détecté")
    RAPPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
