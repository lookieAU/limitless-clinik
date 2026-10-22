import re
from dataclasses import dataclass, field

from agent.memory.negation_lexicon import WINDOW, is_negation, tokenize
from agent.vocab import surface_forms


@dataclass
class Validation:
    ok: bool
    errors: list[str] = field(default_factory=list)


def validation_forms(subject: str, value: str) -> list[list[str]]:
    forms = [form for form in surface_forms(subject, value) if len(form) >= 4 or not form.isascii()]
    return [tokenize(form) for form in forms if tokenize(form)]


def occurrences(tokens: list[str], phrase: list[str]) -> list[tuple[int, int]]:
    size = len(phrase)
    return [(i, i + size) for i in range(len(tokens) - size + 1) if tokens[i : i + size] == phrase]


def negated(tokens: list[str], start: int, end: int) -> bool:
    window = tokens[max(0, start - WINDOW) : start] + tokens[end : end + WINDOW]
    return any(is_negation(token) for token in window)


def check_constraint(tokens: list[str], constraint: dict) -> str | None:
    label = f"{constraint['subject']}={constraint['value']}"
    hits = [hit for phrase in validation_forms(constraint["subject"], constraint["value"]) for hit in occurrences(tokens, phrase)]
    if not hits:
        return f"negation dropped: {label} missing from prose"
    if any(not negated(tokens, start, end) for start, end in hits):
        return f"negation lost: {label} appears without a negation"
    return None


def validate_summary(structured: dict, prose: str) -> Validation:
    errors = []
    tokens = tokenize(prose)
    for constraint in structured.get("constraints", []):
        if not constraint.get("claim_ids"):
            errors.append(f"constraint without source claim: {constraint['subject']}={constraint['value']}")
        if constraint["polarity"] == "negative" and (error := check_constraint(tokens, constraint)):
            errors.append(error)
    for sentence in re.split(r"(?<=[.!?।])\s+", prose):
        for item in structured.get("clinic_snapshot", []):
            if item["ref"].lower() in sentence.lower() and "as of" not in sentence.lower():
                errors.append(f"clinic status for {item['ref']} stated without 'as of'")
    return Validation(not errors, errors)
