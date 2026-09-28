"""Lexique de prononciation : substitutions appliquées au texte envoyé au moteur TTS.

Le texte affiché (transcription, surbrillance) n'est jamais modifié : seule la
prononciation change. Les entrées d'un livre priment sur les entrées globales de même
terme ; les termes les plus longs sont appliqués d'abord (« Mme de Rênal » avant « Mme »).
"""
import re
from dataclasses import dataclass

from sqlmodel import Session, or_, select


@dataclass(frozen=True)
class Rule:
    term: str
    replacement: str
    whole_word: bool = True
    case_sensitive: bool = False


def load_rules(session: Session, book_id: int | None) -> list[Rule]:
    """Règles actives pour un livre : globales, puis celles du livre qui les remplacent."""
    from app.models import LexiconEntry

    cond = LexiconEntry.book_id.is_(None)
    if book_id is not None:
        cond = or_(cond, LexiconEntry.book_id == book_id)
    entries = session.exec(select(LexiconEntry).where(cond)).all()
    by_term: dict[str, Rule] = {}
    for e in sorted(entries, key=lambda e: e.book_id is not None):  # globales d'abord
        if not e.term:
            continue
        key = e.term if e.case_sensitive else e.term.lower()
        by_term[key] = Rule(e.term, e.replacement, e.whole_word, e.case_sensitive)
    return sorted(by_term.values(), key=lambda r: len(r.term), reverse=True)


def _pattern(rule: Rule) -> re.Pattern:
    body = re.escape(rule.term)
    if rule.whole_word:
        # Frontières de mot Unicode, y compris pour un terme qui commence ou finit par un
        # signe (« M. », « C++ ») où \b ne s'applique pas.
        body = rf"(?<![\w]){body}(?![\w])"
    return re.compile(body, 0 if rule.case_sensitive else re.IGNORECASE)


def apply(text: str, rules: list[Rule]) -> str:
    """Applique les règles en une seule passe (aucune substitution ne se rapplique au
    résultat d'une autre)."""
    if not rules or not text:
        return text
    compiled = [(_pattern(r), r.replacement) for r in rules]
    combined = re.compile("|".join(f"(?:{p.pattern})" if not (p.flags & re.IGNORECASE)
                                   else f"(?i:{p.pattern})" for p, _ in compiled))

    def repl(m: re.Match) -> str:
        found = m.group(0)
        for p, replacement in compiled:
            if p.fullmatch(found):
                return replacement
        return found

    return combined.sub(repl, text)
