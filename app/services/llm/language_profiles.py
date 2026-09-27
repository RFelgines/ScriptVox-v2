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

# ── Espagnol ──────────────────────────────────────────────────────────────────
# Typographie mesurée sur Don Quijote (Gutenberg 2000) : le tiret cadratin
# domine largement (99 occurrences sur 14 chapitres, contre 2 guillemets
# droits). Le dialogue_re français attrape déjà 47 répliques espagnoles tel
# quel — on réutilise donc la même construction.
# Incise : l'espagnol n'a PAS l'inversion clitique à trait d'union du français
# (« dit-il »). L'attribution passe par un sujet postposé — « dijo Sancho »,
# « respondió don Quijote ». On exige donc le verbe SUIVI d'un nom propre ou
# d'un pronom : un « dijo » nu n'identifie personne.
_ES_INCISE_VERBS = (
    r"dijo|dijeron|respondió|respondieron|replicó|replicaron|preguntó|preguntaron|"
    r"exclamó|añadió|murmuró|gritó|contestó|prosiguió|continuó|agregó|susurró|"
    r"insistió|objetó|protestó|explicó|afirmó|declaró|concluyó|repuso|observó|"
    r"suspiró|rugió|balbuceó|gruñó|interrumpió|advirtió|repitió"
)

# Le sujet postposé espagnol admet un déterminant ou un titre en minuscule
# devant le nom propre : « don Quijote », « la duquesa », « el cura ».
_ES_SUBJECT = r"(?:(?:el|la|los|las|don|doña|fray|su|mi)\s+)?[A-ZÁÉÍÓÚÑÜ][\wÁ-ÿñ'’-]*"

# Clitique antéposé au verbe : « —Puedes irte—le dijo al criado. »
_ES_CLITIC = r"(?:(?:me|te|le|les|se|nos|os)\s+)?"

_ES_INCISE_VERB = (
    _ES_CLITIC + r"(?:" + _ES_INCISE_VERBS + r")\s+(?:" + _ES_SUBJECT + r"|él|ella|ellos|ellas|yo)"
)

ES_PROFILE = LanguageProfile(
    code="es",
    dialogue_re=re.compile(
        "|".join((
            r"«[^»]*»",
            r"“[^”]*”",
            r'"[^"]*"',
            r"^[ \t]*[—–―][^\n]*",   # convention dominante en espagnol
        )),
        re.MULTILINE,
    ),
    # Différence structurelle majeure avec le français, mesurée sur 5 romans
    # espagnols : l'incise est introduite par un TIRET CADRATIN collé au verbe
    # (« —Sí, señorito—respondió Domingo »), là où le français emploie une
    # virgule (« , dit-il »). Un motif calqué sur le français ne matche donc
    # jamais — mesuré : 0 incise sur Niebla, Los argonautas, Cuentos de amor et
    # El crimen y el castigo avant correction.
    # Comme en français, on n'extrait que l'incise TERMINALE et propre : un
    # « —dijo Víctor a Augusto—, ¡tú… » (dialogue repris après) est laissé
    # intact, d'où l'exclusion des tirets dans la queue.
    incise_re=re.compile(
        r"(?P<dlg>.*[,?!…—–―])(?P<inc>\s*" + _ES_INCISE_VERB + r"[^,—–―]*)$",
        re.UNICODE,
    ),
    # Même principe qu'en français : un nom propre explicite dans le texte source
    # est une attribution certaine, indépendante du LLM.
    explicit_name_re=re.compile(
        r"(?:" + _ES_INCISE_VERBS + r")\s+(" + _ES_SUBJECT
        + r"(?:\s+[A-ZÁÉÍÓÚÑÜ][\wÁ-ÿñ'’-]*)?)"
    ),
)


# ── Allemand ──────────────────────────────────────────────────────────────────
# Typographie mesurée sur Die Verwandlung (Gutenberg 22367) et Aus dem Leben eines
# Taugenichts (35312) : les répliques sont entre guillemets INVERSÉS »…« (124 et
# 303 paires), aucun „…“, aucun tiret cadratin de dialogue. Le profil français
# (repli d'avant) était donc pire qu'inutile : son motif «[^»]*» part du « FERMANT
# d'une réplique et court jusqu'au » OUVRANT de la suivante, c'est-à-dire qu'il
# étiquetait DIALOGUE la narration située entre deux répliques
# (« sagte sich Gregor und fühlte… »).
# „…“ (convention imprimée moderne) et les guillemets droits restent acceptés.
# Les « » suisses (« … ») sont volontairement absents : dans un texte en »…«, un
# « isolé suffirait à réintroduire l'inversion décrite ci-dessus.
# Incise : comme en anglais, elle tombe HORS des guillemets (»…,« sagte sie) —
# aucune scission nécessaire, d'où incise_re=None.
DE_PROFILE = LanguageProfile(
    code="de",
    dialogue_re=re.compile(
        "|".join((
            r"»[^«]*«",              # guillemets allemands (Gutenberg, édition classique)
            r"„[^“”]*[“”]",          # guillemets bas-haut (édition moderne)
            r"“[^”]*”",
            r'"[^"]*"',
        )),
        re.MULTILINE,
    ),
    incise_re=None,
    explicit_name_re=None,
)


# ── Italien ───────────────────────────────────────────────────────────────────
# Typographie mesurée sur Pinocchio (Gutenberg 52484) : 1141 répliques ouvertes
# par un tiret cadratin en début de ligne, contre 47 paires de « » (citations).
# Même construction que l'espagnol, donc : le dialogue_re français convient, et
# l'incise est séparée de la réplique par un TIRET (« — Asino! — gridò
# Geppetto. »), pas par une virgule. Verbes relevés sur le même livre : disse
# (107), rispose (46), gridò (44), domandò (43), replicò (26), ripetè (19),
# soggiunse (16)…
_IT_INCISE_VERBS = (
    r"disse|dissero|rispose|risposero|gridò|gridarono|domandò|domandarono|"
    r"replicò|replicarono|ripetè|ripeté|soggiunse|aggiunse|urlò|urlarono|chiese|"
    r"esclamò|mormorò|sussurrò|riprese|continuò|osservò|borbottò|brontolò|"
    r"concluse|interruppe|proseguì|insistè|insistette|pensò|fece"
)

# Sujet postposé : nom propre (« disse Geppetto »), ou nom commun précédé d'un
# article ou d'un titre — en minuscule en italien : « gridò il burattino ».
_IT_SUBJECT = (
    r"(?:(?:il|lo|la|i|gli|le|un|uno|una|quel|quello|quella|mastro|don|donna|sor)\s+"
    r"[\wÀ-ÿ'’-]+|l['’][\wÀ-ÿ-]+|[A-ZÀ-Ý][\wÀ-ÿ'’-]*)"
)

# Clitique antéposé au verbe : « — Vieni qui — gli disse Geppetto. »
_IT_CLITIC = r"(?:(?:mi|ti|gli|le|ci|vi|si)\s+)?"

_IT_INCISE_VERB = (
    _IT_CLITIC + r"(?:" + _IT_INCISE_VERBS + r")\s+(?:" + _IT_SUBJECT + r"|lui|lei|loro|io)"
)

IT_PROFILE = LanguageProfile(
    code="it",
    dialogue_re=FR_PROFILE.dialogue_re,
    # Seule l'incise TERMINALE et propre est extraite, comme en espagnol :
    # « — Sbucciarle? — replicò Geppetto meravigliato. — Non avrei… » (réplique
    # reprise après l'incise) reste intact, d'où l'exclusion des tirets dans la queue.
    incise_re=re.compile(
        r"(?P<dlg>.*[,?!…—–―])(?P<inc>\s*" + _IT_INCISE_VERB + r"[^,—–―]*)$",
        re.UNICODE,
    ),
    # Nom propre explicite uniquement (« disse Geppetto », « rispose la Fata ») :
    # « gridò il burattino » désigne bien Pinocchio, mais ce n'est pas un nom.
    explicit_name_re=re.compile(
        r"(?:" + _IT_INCISE_VERBS + r")\s+((?:(?:mastro|don|donna|sor|il|lo|la)\s+)?"
        r"[A-ZÀ-Ý][\wÀ-ÿ'’-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]*)?)"
    ),
)


_PROFILES: dict[str, LanguageProfile] = {
    "fr": FR_PROFILE, "en": EN_PROFILE, "es": ES_PROFILE, "de": DE_PROFILE, "it": IT_PROFILE,
}

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
    if normalized.startswith("es") or normalized in ("spa", "spanish", "espagnol", "español"):
        return ES_PROFILE
    if normalized.startswith("de") or normalized in ("deu", "ger", "german", "allemand", "deutsch"):
        return DE_PROFILE
    if normalized.startswith("it") or normalized in ("ita", "italian", "italien", "italiano"):
        return IT_PROFILE
    return FR_PROFILE
