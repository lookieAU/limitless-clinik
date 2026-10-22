import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {ROOT / "shared" / "clock.py", Path(__file__).resolve()}
SKIPPED_DIRS = {".venv", ".git", "__pycache__", "node_modules"}
FORBIDDEN = re.compile(r"\b(datetime\.now|datetime\.utcnow|utcnow|datetime\.today|date\.today)\s*\(")


def violations(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if FORBIDDEN.search(line)]


def python_sources() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.py")
        if not SKIPPED_DIRS.intersection(path.relative_to(ROOT).parts) and path not in ALLOWED
    ]


def test_scanner_catches_wall_clock_reads():
    sample = "a = datetime.now()\nb = datetime.utcnow()\nc = date.today()\nd = clock.now()"
    assert len(violations(sample)) == 3


def test_no_wall_clock_reads_outside_clock_module():
    found = {
        str(path.relative_to(ROOT)): hits
        for path in python_sources()
        if (hits := violations(path.read_text(encoding="utf-8")))
    }
    assert found == {}
