NEGATIONS = {
    "en": ("not", "no", "never", "avoid", "except", "can't", "cannot", "won't", "don't", "isn't", "doesn't"),
    "hi": ("नहीं", "मत", "ना", "न", "बिना", "छोड़कर"),
    "romanized": ("nahi", "nahin", "mat", "na"),
}

ALL_NEGATIONS = frozenset(word for words in NEGATIONS.values() for word in words)
WINDOW = 3
PUNCTUATION = ".,;:!?\"'()[]{}—–-…।"


def tokenize(text: str) -> list[str]:
    return [token.strip(PUNCTUATION).lower() for token in text.split() if token.strip(PUNCTUATION)]


def is_negation(token: str) -> bool:
    return token in ALL_NEGATIONS or token.endswith("n't")
