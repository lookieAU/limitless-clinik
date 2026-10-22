from datetime import date, time

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DAY_FORMS = {
    "mon": {"en": ["monday", "mon"], "hi": ["सोमवार", "somvar", "somwar"]},
    "tue": {"en": ["tuesday", "tue", "tues"], "hi": ["मंगलवार", "mangalvar", "mangalwar"]},
    "wed": {"en": ["wednesday", "wed"], "hi": ["बुधवार", "budhvar", "budhwar"]},
    "thu": {"en": ["thursday", "thu", "thurs"], "hi": ["गुरुवार", "बृहस्पतिवार", "guruvar", "guruwar", "veervar"]},
    "fri": {"en": ["friday", "fri"], "hi": ["शुक्रवार", "shukravar", "shukrawar"]},
    "sat": {"en": ["saturday", "sat"], "hi": ["शनिवार", "shanivar", "shaniwar"]},
    "sun": {"en": ["sunday", "sun"], "hi": ["रविवार", "ravivar", "raviwar", "itvaar"]},
}

WEEK_FORMS = {
    "this_week": {"en": ["this week"], "hi": ["इस हफ्ते", "इस सप्ताह", "is hafte", "iss hafte"]},
    "next_week": {"en": ["next week"], "hi": ["अगले हफ्ते", "अगले सप्ताह", "agle hafte", "next week"]},
}

DAY_LABEL = {
    "en": {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"},
    "hi": {"mon": "सोमवार", "tue": "मंगलवार", "wed": "बुधवार", "thu": "गुरुवार", "fri": "शुक्रवार", "sat": "शनिवार", "sun": "रविवार"},
}

WEEK_LABEL = {
    "en": {"this_week": "this week", "next_week": "next week"},
    "hi": {"this_week": "इस हफ्ते", "next_week": "अगले हफ्ते"},
}


def clock_label(value: str) -> str:
    wall = time.fromisoformat(value)
    hour = wall.hour % 12 or 12
    return f"{hour}:{wall.minute:02d} {'am' if wall.hour < 12 else 'pm'}"


def time_label(value: str, lang: str) -> str:
    if value.startswith("before_"):
        return f"{clock_label(value[7:])} से पहले" if lang == "hi" else f"before {clock_label(value[7:])}"
    if value.startswith("after_"):
        return f"{clock_label(value[6:])} के बाद" if lang == "hi" else f"after {clock_label(value[6:])}"
    return clock_label(value)


def value_label(subject: str, value: str, lang: str, doctors: dict[str, str] | None = None) -> str:
    lang = "hi" if lang == "hi" else "en"
    if subject == "day":
        return DAY_LABEL[lang].get(value, value)
    if subject == "week":
        return WEEK_LABEL[lang].get(value, value)
    if subject == "date":
        day = date.fromisoformat(value)
        return f"{day.day} {day:%b}"
    if subject == "time_window":
        return time_label(value, lang)
    if subject == "doctor":
        return (doctors or {}).get(value) or f"Dr {value.removeprefix('dr_').upper()}"
    return value


def claim_label(claim: dict, lang: str, doctors: dict[str, str] | None = None) -> str:
    text = value_label(claim["subject"], claim["value"], lang, doctors)
    if claim["polarity"] == "negative":
        return f"{text} नहीं" if lang == "hi" else f"not {text}"
    return text


def surface_forms(subject: str, value: str) -> list[str]:
    if subject == "day":
        return [form for forms in DAY_FORMS.get(value, {}).values() for form in forms]
    if subject == "week":
        return [form for forms in WEEK_FORMS.get(value, {}).values() for form in forms]
    if subject == "date":
        day = date.fromisoformat(value)
        return [f"{day.day} {day:%b}".lower(), f"{day:%B} {day.day}".lower(), f"{day.day} {day:%B}".lower(), value]
    if subject == "time_window":
        return [time_label(value, "en").lower(), time_label(value, "hi"), value]
    return [value.lower()]
