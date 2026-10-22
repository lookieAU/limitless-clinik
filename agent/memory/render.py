from agent.vocab import claim_label

HEADINGS = {
    "en": {"constraints": "Customer said", "intents": "Open requests", "clinic": "Clinic records (re-verify before use)"},
    "hi": {"constraints": "ग्राहक ने कहा", "intents": "खुले अनुरोध", "clinic": "क्लिनिक रिकॉर्ड (इस्तेमाल से पहले दोबारा जाँचें)"},
}
AS_OF = {"en": "as of", "hi": "as of"}


def render_summary(structured: dict, lang: str) -> str:
    lang = "hi" if lang == "hi" else "en"
    words = HEADINGS[lang]
    parts = []
    constraints = [claim_label(item, lang) for item in structured.get("constraints", [])]
    if constraints:
        parts.append(f"{words['constraints']}: {'; '.join(constraints)}.")
    intents = [item["intent"] for item in structured.get("open_intents", [])]
    if intents:
        parts.append(f"{words['intents']}: {', '.join(intents)}.")
    snapshot = [
        f"{item['ref']} {item['status']} {AS_OF[lang]} {item['observed_utc']}" for item in structured.get("clinic_snapshot", [])
    ]
    if snapshot:
        parts.append(f"{words['clinic']}: {'; '.join(snapshot)}.")
    return " ".join(parts) or ("No customer statements today." if lang == "en" else "आज कोई बात दर्ज नहीं हुई।")
