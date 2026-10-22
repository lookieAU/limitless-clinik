import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
ROMANIZED_HINDI = frozenset(
    "kar karo karna kardo chalega chalegi nahi nahin mat haan haa ji kya hai hain hua hoga theek thik "
    "baje agle agla hafte hafta mera meri mujhe aap aapka kab kaise bhai acha accha wala wali sahi bilkul".split()
)
HINT_THRESHOLD = 2
HINT_RATIO = 0.34


def detect_language(text: str, fallback: str = "en") -> str:
    if DEVANAGARI.search(text):
        return "hi"
    tokens = re.findall(r"[a-z]+", text.lower())
    if not tokens:
        return fallback
    hits = sum(token in ROMANIZED_HINDI for token in tokens)
    return "hi" if hits >= HINT_THRESHOLD or (hits and hits / len(tokens) >= HINT_RATIO) else "en"
