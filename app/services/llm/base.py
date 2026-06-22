import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from app.core.enums import AgeCategory, Gender, SegmentType
from app.core.exceptions import LLMParsingError

_logger = logging.getLogger(__name__)
_E = TypeVar("_E", bound=Enum)

_ALIASES: dict[type, dict[str, str]] = {
    SegmentType: {
        "DIALOG": "DIALOGUE",
        "NARRATE": "NARRATION",
        "PROSE": "NARRATION",
        "NARRATOR": "NARRATION",
        "DESCRIPTION": "NARRATION",
        "ACTION": "NARRATION",
        "MONOLOGUE": "DIALOGUE",
    },
    Gender: {
        "M": "MALE",
        "F": "FEMALE",
        "N": "NEUTRAL",
        "U": "UNKNOWN",
    },
    AgeCategory: {
        "YOUNG": "YOUNG_ADULT",
        "TEEN": "YOUNG_ADULT",
        "TEENAGER": "YOUNG_ADULT",
        "ADOLESCENT": "YOUNG_ADULT",
        "KID": "CHILD",
        "BABY": "CHILD",
        "INFANT": "CHILD",
        "TODDLER": "CHILD",
        "OLD": "ELDER",
        "ELDERLY": "ELDER",
        "SENIOR": "ELDER",
        "AGED": "ELDER",
    },
}


def _coerce_enum(raw: str, enum_cls: type[_E], default: _E) -> _E:
    """Normalise une valeur brute LLM en membre d'enum ; retombe sur *default* avec WARNING."""
    # Normaliser : upper, espaces/tirets → underscore, supprimer la ponctuation résiduelle
    step = re.sub(r"[\s\-]+", "_", raw.strip().upper())
    normalized = re.sub(r"[^A-Z_]", "", step)

    # 1. Correspondance directe après normalisation
    try:
        return enum_cls(normalized)
    except ValueError:
        pass

    # 2. Premier token (gère "DIALOG_" issu de "DIALOG, ")
    first_token = normalized.split("_")[0] if normalized else ""
    if first_token and first_token != normalized:
        try:
            return enum_cls(first_token)
        except ValueError:
            pass

    # 3. Table d'alias (normalized puis premier token)
    aliases = _ALIASES.get(enum_cls, {})
    for candidate in (normalized, first_token):
        if candidate in aliases:
            try:
                result = enum_cls(aliases[candidate])
                _logger.warning("_coerce_enum: %r -> %s.%s (alias)", raw, enum_cls.__name__, result.value)
                return result
            except ValueError:
                pass

    # 4. Défaut
    _logger.warning("_coerce_enum: %r unrecognized for %s, defaulting to %s", raw, enum_cls.__name__, default.value)
    return default

GEMINI_MAX_TOKENS = 500_000

SYSTEM_PROMPT = (
    "You are a literary analysis assistant. You receive a chapter split into numbered,\n"
    "tagged spans, one per line: [<index>][DIALOGUE|NARRATION] <text>.\n\n"
    "Your job is NOT to rewrite the text. Do TWO things only:\n"
    "1. Identify the speaking characters.\n"
    "2. For each [DIALOGUE] span, name the character who speaks it.\n\n"
    "Return ONLY valid JSON matching this exact schema — no markdown, no commentary:\n"
    "{\n"
    '  "characters": [\n'
    '    {\n'
    '      "name": "...", "description": "...",\n'
    '      "gender": "MALE|FEMALE|NEUTRAL|UNKNOWN",\n'
    '      "age_category": "CHILD|YOUNG_ADULT|ADULT|ELDER|UNKNOWN",\n'
    '      "tone": "...", "voice_quality": "...", "voice_tone": "..."\n'
    '    }\n'
    "  ],\n"
    '  "attributions": [ {"index": 2, "character_name": "...", "emotion": "..."} ]\n'
    "}\n\n"
    "Rules:\n"
    "- attributions: ONE entry per [DIALOGUE] span only, keyed by its <index>. Never include NARRATION spans.\n"
    "- character_name must exactly match a name in the characters array.\n"
    "- emotion: short free-text description of HOW the dialogue line should be delivered, e.g. "
    "\"furious and panicked\", \"soft and hesitant\", \"calm\"; use \"neutral\" if the line carries no "
    "notable emotional charge. Omit only if genuinely undeterminable.\n"
    "- NEVER reproduce or repeat span text — output indices and names only.\n"
    "- gender: infer from pronouns/context; use UNKNOWN if ambiguous.\n"
    "- age_category: CHILD <13, YOUNG_ADULT 13-25, ADULT 26-60, ELDER 60+; use UNKNOWN if ambiguous.\n"
    "- tone: single word for emotional/personality quality, e.g. \"warm\", \"cold\", \"harsh\", \"gentle\".\n"
    "- voice_quality: single word for acoustic quality, e.g. \"deep\", \"raspy\", \"bright\", \"smooth\".\n"
    "- voice_tone: concise phrase combining tone and quality, e.g. \"soft and hesitant\", \"deep and commanding\".\n"
    "- If a list of known characters from previous chapters is given, reuse the EXACT same "
    "name for a character who reappears; only introduce a new name for a genuinely new character."
)


@dataclass
class CharacterData:
    name: str
    description: str | None
    gender: Gender
    age_category: AgeCategory = AgeCategory.UNKNOWN
    tone: str | None = None
    voice_quality: str | None = None
    voice_tone: str | None = None


@dataclass
class SegmentData:
    position: int
    text: str
    segment_type: SegmentType
    character_name: str | None
    emotion: str | None = None


@dataclass
class LLMChapterResult:
    characters: list[CharacterData]
    segments: list[SegmentData]


@dataclass
class MergeSuggestion:
    survivor_name: str
    merged_name: str
    reason: str | None = None


class BaseLLMProvider(ABC):
    @abstractmethod
    async def analyze(
        self, text: str, known_characters: list[str] | None = None
    ) -> LLMChapterResult: ...

    @abstractmethod
    async def suggest_merges(
        self, characters: list[CharacterData]
    ) -> list[MergeSuggestion]: ...


# ── Pre-segmentation (label-based protocol, ARCHITECTURE.md §2.7) ────────────────

_DIALOGUE_RE = re.compile(
    "|".join((
        r"«[^»]*»",              # guillemets français
        r"“[^”]*”",              # guillemets typographiques
        r'"[^"]*"',              # guillemets droits
        r"^[ \t]*[—–―][^\n]*",   # ligne ouverte par un tiret cadratin (dialogue FR)
    )),
    re.MULTILINE,
)

# Verbes d'incise courants (pour le cas « verbe + nom propre » : « dit Harry »).
# Liste curée, volontairement non exhaustive — voir _split_incise (dégradation bornée).
# Apostrophe tolérante : l'EPUB source utilise la typographique (’ U+2019), pas la droite (').
_APOS = r"['’]"
_INCISE_VERBS = (
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
_INCISE_VERB = (
    r"(?:"
    r"(?:[a-zà-ÿ]{1,3}" + _APOS + r")?\w+(?:-t)?-(?:il|elle|ils|elles|on|je)"   # inversion clitique
    r"|(?:" + _INCISE_VERBS + r")\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]*"           # verbe d'incise + nom propre
    r")"
)
_INCISE_RE = re.compile(
    r"(?P<dlg>.*[,?!…])(?P<inc>\s+" + _INCISE_VERB + r"[^,]*)$",
    re.UNICODE,
)


@dataclass
class _Span:
    index: int
    text: str
    is_dialogue: bool


def _is_emdash(text: str) -> bool:
    """Vrai si le span est une réplique ouverte par un tiret cadratin (convention FR)."""
    return text.lstrip()[:1] in ("—", "–", "―")


def _split_incise(span_text: str) -> list[tuple[str, bool]]:
    """Scinde une réplique en tiret cadratin en ``[(dialogue, True), (incise, False)]``.

    L'incise (« dit-elle froidement ») doit être lue par le narrateur, pas par la voix
    du personnage. Découpe byte-exact : ``dialogue + incise == span_text``. Si aucune
    incise terminale propre n'est détectée, renvoie le span inchangé (``[(span_text, True)]``)
    — dégradation bornée : jamais de crash, jamais de mot perdu (cf. §2.7).
    """
    match = _INCISE_RE.match(span_text)
    if not match:
        return [(span_text, True)]
    dlg, inc = match.group("dlg"), match.group("inc")
    if not dlg.strip() or not inc.strip():
        return [(span_text, True)]
    return [(dlg, True), (inc, False)]


def _pre_segment(text: str) -> list[_Span]:
    """Découpe *text* en spans ordonnés narration/dialogue, byte-exact (zéro mot perdu).

    Invariant : ``"".join(s.text for s in _pre_segment(t)) == t`` et index 1-based contigus.
    Le type (dialogue vs narration) est déterminé ici via les délimiteurs ; les répliques
    en tiret cadratin sont en plus scindées de leur incise (_split_incise). Le LLM
    n'attribue qu'un locuteur aux spans de dialogue (cf. §2.7). Un dialogue non
    détecté reste narration (lu par le narrateur) — jamais de crash, jamais de perte.
    """
    raw: list[tuple[str, bool]] = []
    pos = 0
    for match in _DIALOGUE_RE.finditer(text):
        start, end = match.span()
        if start > pos:
            raw.append((text[pos:start], False))
        raw.append((text[start:end], True))
        pos = end
    if pos < len(text):
        raw.append((text[pos:], False))
    if not raw:
        raw.append((text, False))

    # Extraction de l'incise sur les répliques en tiret cadratin uniquement
    # (en guillemets, l'incise tombe déjà hors « », rien à faire).
    pieces: list[tuple[str, bool]] = []
    for seg_text, is_dialogue in raw:
        if is_dialogue and _is_emdash(seg_text):
            pieces.extend(_split_incise(seg_text))
        else:
            pieces.append((seg_text, is_dialogue))

    return [_Span(i, t, d) for i, (t, d) in enumerate(pieces, start=1)]


def _build_user_prompt(spans: list[_Span], known_characters: list[str] | None = None) -> str:
    """Rend les spans numérotés et tagués pour le LLM : ``[i][DIALOGUE|NARRATION] texte``.

    Le texte est normalisé (espaces/sauts de ligne compactés) ; les spans vides après
    normalisation sont omis de l'affichage mais conservent leur index d'origine.
    Si *known_characters* est non vide, une ligne de préambule liste les personnages déjà
    détectés dans les chapitres précédents (persistance des personnages, §2.7) ; sinon le
    rendu est identique à l'appel sans cet argument (no-op).
    """
    lines: list[str] = []
    if known_characters:
        lines.append("Known characters from previous chapters: " + ", ".join(known_characters) + ".")
    for span in spans:
        display = " ".join(span.text.split())
        if not display:
            continue
        tag = "DIALOGUE" if span.is_dialogue else "NARRATION"
        lines.append(f"[{span.index}][{tag}] {display}")
    return "\n".join(lines)


# ── Token budgeting ────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _compute_read_timeout(prompt: str, floor: float, per_1k_tokens: float) -> float:
    """Read timeout for one LLM request: a fixed floor plus extra time scaled to the
    estimated prompt size, so a dense chapter (or a slow/CPU-offloaded local model)
    isn't cut off before it can finish. See ARCHITECTURE.md §2.5."""
    return floor + (_estimate_tokens(prompt) / 1000) * per_1k_tokens


def _split_by_sep(text: str, sep: str, max_tokens: int) -> list[str]:
    parts = [p for p in text.split(sep) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for part in parts:
        part_tokens = _estimate_tokens(part)
        if part_tokens > max_tokens:
            # Single unit overflows — recurse to finer granularity
            if current:
                chunks.append(sep.join(current))
                current = []
                current_tokens = 0
            if sep == "\n\n":
                chunks.extend(_split_by_sep(part, "\n", max_tokens))
            else:
                chunks.append(part)  # single line too long — accept as-is
        elif current_tokens + part_tokens > max_tokens and current:
            chunks.append(sep.join(current))
            current = [part]
            current_tokens = part_tokens
        else:
            current.append(part)
            current_tokens += part_tokens

    if current:
        chunks.append(sep.join(current))

    return chunks or [text]


def _chunk_text(text: str, max_tokens: int) -> list[str]:
    if _estimate_tokens(text) <= max_tokens:
        return [text]
    return _split_by_sep(text, "\n\n", max_tokens)


# ── Result helpers ─────────────────────────────────────────────────────────────

def _merge_chunk_results(results: list[LLMChapterResult]) -> LLMChapterResult:
    seen: dict[str, CharacterData] = {}
    segments: list[SegmentData] = []
    pos = 0

    for result in results:
        for cd in result.characters:
            if cd.name not in seen:
                seen[cd.name] = cd
        for sd in result.segments:
            pos += 1
            segments.append(SegmentData(
                position=pos,
                text=sd.text,
                segment_type=sd.segment_type,
                character_name=sd.character_name,
                emotion=sd.emotion,
            ))

    return LLMChapterResult(characters=list(seen.values()), segments=segments)


def _segment_text(span: "_Span") -> str:
    """Retourne le texte du span avec les délimiteurs de dialogue retirés (pour le TTS)."""
    text = span.text.strip()
    if not span.is_dialogue:
        return text
    if text.startswith("«") and text.endswith("»"):
        text = text[1:-1].strip()
    elif text.startswith("“") and text.endswith("”"):
        text = text[1:-1].strip()
    elif text.startswith('"') and text.endswith('"') and len(text) > 1:
        text = text[1:-1].strip()
    else:
        text = re.sub(r'^[ \t]*[—–―]\s*', '', text)
        # Virgule orpheline laissée par l'extraction d'incise : « …pas, » -> « …pas »
        text = re.sub(r'\s*,\s*$', '', text)
    return text.strip()


def _parse_llm_json(raw: str, spans: "list[_Span]") -> LLMChapterResult:
    """Parse la réponse LLM label-based ``{characters, attributions}`` et reconstruit
    les ``SegmentData`` depuis les spans pré-segmentés (cf. ARCHITECTURE.md §2.7)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMParsingError(raw, exc) from exc

    try:
        characters = [
            CharacterData(
                name=c["name"],
                description=c.get("description"),
                gender=_coerce_enum(c.get("gender", "UNKNOWN"), Gender, Gender.UNKNOWN),
                age_category=_coerce_enum(c.get("age_category", "UNKNOWN"), AgeCategory, AgeCategory.UNKNOWN),
                tone=c.get("tone"),
                voice_quality=c.get("voice_quality"),
                voice_tone=c.get("voice_tone"),
            )
            for c in data.get("characters", [])
        ]
        known_names = {c.name for c in characters}
        attr_map: dict[int, str] = {}
        emotion_map: dict[int, str] = {}
        for a in data.get("attributions", []):
            name = a.get("character_name")
            if name and name in known_names:
                attr_map[a["index"]] = name
            else:
                _logger.warning(
                    "_parse_llm_json: attribution index=%s character=%r not in characters list, "
                    "falling back to narrator",
                    a.get("index"), name,
                )
            emotion = a.get("emotion")
            if emotion:
                emotion_map[a["index"]] = emotion

        segments: list[SegmentData] = []
        pos = 0
        for span in spans:
            text = _segment_text(span)
            if not text:
                continue
            pos += 1
            seg_type = SegmentType.DIALOGUE if span.is_dialogue else SegmentType.NARRATION
            char_name = attr_map.get(span.index) if span.is_dialogue else None
            emotion = emotion_map.get(span.index) if span.is_dialogue else None
            segments.append(SegmentData(
                position=pos,
                text=text,
                segment_type=seg_type,
                character_name=char_name,
                emotion=emotion,
            ))
    except (KeyError, ValueError) as exc:
        raise LLMParsingError(raw, exc) from exc

    return LLMChapterResult(characters=characters, segments=segments)


# ── Fusion de personnages (suggest_merges) ──────────────────────────────────────

MERGE_SYSTEM_PROMPT = (
    "You receive a list of characters detected across a whole book, each with a name "
    "and short descriptive traits. Some entries might refer to the SAME real person "
    "under different names (e.g. \"Mr Dursley\" and \"Vernon Dursley\").\n\n"
    "Your job: identify groups of duplicate names that refer to the same character, "
    "and for each group, pick the most complete/canonical name as survivor.\n\n"
    "Return ONLY valid JSON matching this exact schema — no markdown, no commentary:\n"
    "{\n"
    '  "merges": [ {"survivor_name": "...", "merged_name": "...", "reason": "..."} ]\n'
    "}\n\n"
    "Rules:\n"
    "- Both survivor_name and merged_name MUST exactly match a name from the input list.\n"
    "- Only suggest a merge when reasonably confident they are the same person — "
    "when in doubt, do NOT suggest a merge (a wrong merge destroys a distinct character).\n"
    "- If a group has 3+ duplicates, emit one entry per non-survivor name, all sharing "
    "the same survivor_name.\n"
    "- reason: short free-text explanation, e.g. \"Same person, full name vs. nickname\".\n"
    "- If no duplicates are found, return {\"merges\": []}."
)


def _build_merge_prompt(characters: list[CharacterData]) -> str:
    lines = ["Characters detected in this book:"]
    for c in characters:
        traits = ", ".join(
            f"{label}: {value}"
            for label, value in (
                ("gender", c.gender.value),
                ("age", c.age_category.value),
                ("description", c.description),
            )
            if value
        )
        lines.append(f"- {c.name} ({traits})" if traits else f"- {c.name}")
    return "\n".join(lines)


def _parse_merge_json(raw: str, characters: list[CharacterData]) -> list[MergeSuggestion]:
    """Parse la réponse LLM ``{merges}`` ; toute entrée invalide est ignorée (WARNING),
    jamais de crash (cf. philosophie de dégradation bornée du reste de ce fichier)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMParsingError(raw, exc) from exc

    known_names = {c.name for c in characters}
    suggestions: list[MergeSuggestion] = []
    for m in data.get("merges", []):
        survivor_name = m.get("survivor_name")
        merged_name = m.get("merged_name")
        if survivor_name not in known_names or merged_name not in known_names:
            _logger.warning(
                "_parse_merge_json: survivor=%r merged=%r not both in known characters, skipped",
                survivor_name, merged_name,
            )
            continue
        if survivor_name == merged_name:
            _logger.warning("_parse_merge_json: survivor_name == merged_name (%r), skipped", survivor_name)
            continue
        suggestions.append(MergeSuggestion(
            survivor_name=survivor_name,
            merged_name=merged_name,
            reason=m.get("reason"),
        ))
    return suggestions
