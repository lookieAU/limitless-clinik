from agent.pipeline.templates import en, hi

LANGUAGES = {"en": en.TEMPLATES, "hi": hi.TEMPLATES}


def text(lang: str, key: str, **params) -> str:
    table = LANGUAGES.get(lang, en.TEMPLATES)
    return table.get(key, en.TEMPLATES[key]).format(**params)
