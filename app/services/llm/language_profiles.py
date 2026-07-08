"""Profils de segmentation par langue (§2.7 label-based).

Chaque langue a ses propres conventions typographiques de dialogue et son
propre signal d'incise (verbe/pronom qui identifie le narrateur d'une
réplique). Un profil regroupe ces règles pour que `_pre_segment` (base.py)
reste indépendant de la langue -- ajouter une langue = ajouter un profil ici,
pas modifier la logique de segmentation.
"""
import re
from dataclasses import dataclass

# Apostrophe tolérante : l'EPUB source utilise la typographique (’ U+2019), pas la droite (').
_APOS = r"['’]"


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    dialogue_re: re.Pattern
    # None = pas de scission d'incise pour cette langue (l'incise tombe déjà hors
    # dialogue par construction du dialogue_re, ex. dialogue entre guillemets).
    incise_re: re.Pattern | None
    explicit_name_re: re.Pattern | None


# ── Français ──────────────────────────────────────────────────────────────────
# Verbes d'incise courants (pour le cas « verbe + nom propre » : « dit Harry »).
# Liste curée, volontairement non exhaustive — voir _split_incise (dégradation bornée).
_FR_INCISE_VERBS = (
    r"dit|dirent|répondit|répondirent|demanda|demandèrent|murmura|cria|crièrent|"
    r"reprit|ajouta|lança|soupira|songea|hurla|chuchota|gronda|rétorqua|répliqua|"
    r"déclara|poursuivit|continua|conclut|fit|gémit|objecta|protesta|insista|"
    r"expliqua|affirma|marmonna|balbutia|susurra|rugit|beugla|bredouilla|grommela|"
    r"renchérit|coupa|trancha|s" + _APOS + r"écria|s" + _APOS + r"exclama|"
    r"s" + _APOS + r"étonna|s" + _APOS + r"enquit"
)

# Une incise est repérée par l'inversion verbe-sujet, signal le plus fiable du français :
#   - clitique : « dit-il », « dit-elle », « demanda-t-elle », « s'écria-t-il »…
#   - verbe d'incise curé + nom propre : « dit Harry », « répondit Mrs Dursley »…
# On ne l'extrait QUE si elle est terminale et propre (aucune virgule après le verbe) :
# « …, répondit-il, mais je viendrai » = dialogue repris → NON splitté (borné, cf. tests).
_FR_INCISE_VERB = (
    r"(?:"
    r"(?:[a-zà-ÿ]{1,3}" + _APOS + r")?\w+(?:-t)?-(?:il|elle|ils|elles|on|je)"   # inversion clitique
    r"|(?:" + _FR_INCISE_VERBS + r")\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]*"           # verbe d'incise + nom propre
    r")"
)

FR_PROFILE = LanguageProfile(
    code="fr",
    dialogue_re=re.compile(
        "|".join((
            r"«[^»]*»",              # guillemets français
            r"“[^”]*”",              # guillemets typographiques
            r'"[^"]*"',              # guillemets droits
            r"^[ \t]*[—–―][^\n]*",   # ligne ouverte par un tiret cadratin (dialogue FR)
        )),
        re.MULTILINE,
    ),
    incise_re=re.compile(
        r"(?P<dlg>.*[,?!…])(?P<inc>\s+" + _FR_INCISE_VERB + r"[^,]*)$",
        re.UNICODE,
    ),
    # Isole, à l'intérieur d'une incise déjà détectée, le cas "verbe d'incise + nom propre"
    # (« dit Dumbledore », « répondit Mrs Dursley ») — PAS le clitique (« dit-il »), dont le
    # référent ne peut pas être déduit sans contexte. Un nom explicite dans le texte source est
    # une attribution certaine, indépendante du LLM (cf. mesure spike 2026-07-02 : 13/80 dialogues
    # du Ch.3 HP couverts, dont 1 des 6 ratés du LLM récupéré).
    explicit_name_re=re.compile(
        r"(?:" + _FR_INCISE_VERBS + r")\s+([A-ZÀ-Ý][\wÀ-ÿ'’-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]*)?)"
    ),
)


# ── Anglais ───────────────────────────────────────────────────────────────────
# L'anglais n'a pas d'inversion clitique à trait d'union comme le français
# ("dit-il" n'a pas d'équivalent structurel — "he said" est un ordre sujet-verbe
# normal, pas une marque d'incise). La convention de dialogue anglaise est
# quasi exclusivement les guillemets (droits ou typographiques) ; le tiret
# cadratin en début de ligne n'est PAS un marqueur de dialogue en anglais
# (usage ponctuation différent), donc volontairement absent de dialogue_re
# pour éviter les faux positifs.
#
# Conséquence structurelle : comme en français avec les guillemets « », une
# incise anglaise ("he shouted.", "said Harry.") tombe déjà HORS de la
# réplique dès que le dialogue est délimité par des guillemets (le dialogue_re
# ne capture que le texte entre guillemets) -- aucune scission additionnelle
# n'est nécessaire, d'où incise_re=None. C'est le même niveau de couverture
# que celui déjà accepté pour le français en contexte guillemets (l'extraction
# de nom explicite n'y est pas câblée non plus, cf. base.py commentaire
# "Guillemets : l'incise est déjà hors « » -> comportement inchangé").
EN_PROFILE = LanguageProfile(
    code="en",
    dialogue_re=re.compile(
        "|".join((
            r"“[^”]*”",              # guillemets typographiques
            r'"[^"]*"',              # guillemets droits
        )),
        re.MULTILINE,
    ),
    incise_re=None,
    explicit_name_re=None,
)

_PROFILES: dict[str, LanguageProfile] = {"fr": FR_PROFILE, "en": EN_PROFILE}

# Codes reconnus par resolve_profile, exposés pour valider/lister les choix
# utilisateur (ex. AppSetting.preferred_language) sans dupliquer cette liste.
AVAILABLE_LANGUAGES: tuple[str, ...] = tuple(_PROFILES.keys())


def resolve_profile(language: str | None) -> LanguageProfile:
    """Normalise une valeur brute de ``Book.language`` (ex. ``"en-US"``, ``"eng"``,
    ``"fr-FR"``, ``None``) vers un ``LanguageProfile``. Toute valeur non reconnue
    comme anglaise retombe sur le profil français -- comportement historique de
    ScriptVox (conçu et testé en français), zéro régression sur les livres déjà
    traités sans métadonnée de langue fiable."""
    if not language:
        return FR_PROFILE
    normalized = language.strip().lower()
    if normalized.startswith("en") or normalized in ("eng", "english", "anglais"):
        return EN_PROFILE
    return FR_PROFILE
