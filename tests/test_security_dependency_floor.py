"""Fail early if a known-vulnerable pytest constraint is reintroduced."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_pytest_minimum_is_patched():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    entries = [line.strip() for line in text.splitlines() if line.strip().startswith("pytest")]
    assert entries == ["pytest>=9.0.3,<10.0"], entries


def test_security_audit_remains_fail_closed():
    content = (ROOT / ".github/workflows/research-v20-security.yml").read_text(encoding="utf-8")
    assert "python -m pip_audit -r requirements.txt" in content
    assert "if: always()" in content and "release-evidence/" in content
    assert "continue-on-error: true" not in content
    assert not re.search(r"pip_audit[^\n]*\|\|\s*true", content)
    assert "actions/checkout@v5" in content
    assert "actions/setup-python@v6" in content
    assert "actions/upload-artifact@v6" in content
