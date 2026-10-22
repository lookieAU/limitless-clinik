import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLINIC_IMPORT = re.compile(r"^\s*(from|import)\s+clinic(\.|\s|$)", re.MULTILINE)


def test_agent_never_imports_clinic_service():
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "agent").rglob("*.py") if CLINIC_IMPORT.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_shared_has_no_service_imports():
    pattern = re.compile(r"^\s*(from|import)\s+(agent|clinic)\b", re.MULTILINE)
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "shared").rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
