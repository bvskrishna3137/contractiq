"""Repo hygiene: fail loudly if a key, a .env file or a private document is ever committed."""
import re
import subprocess

from conftest import ROOT

SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "build", "dist", "output"}
KEY_PATTERNS = [re.compile("sk-" + "ant-[A-Za-z0-9_-]{20,}"), re.compile("-----BEGIN [A-Z ]*PRIVATE" + " KEY-----"),
                re.compile("ANTHROPIC_API_KEY\\s*=\\s*[\"']?sk-")]


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        if out:
            return [ROOT / f for f in out]
    except (OSError, subprocess.CalledProcessError):
        pass
    return [p for p in ROOT.rglob("*") if p.is_file()
            and not (SKIP_DIRS & set(p.relative_to(ROOT).parts)) and "egg-info" not in str(p)]


def test_no_secrets_in_source():
    for f in tracked_files():
        if f.suffix in {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".json", ".example", ""} and f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            for rx in KEY_PATTERNS:
                assert not rx.search(text), f"possible secret in {f.relative_to(ROOT)}"


def test_env_file_is_not_present_or_tracked():
    assert ".env" in (ROOT / ".gitignore").read_text()
    assert not any(f.name == ".env" for f in tracked_files())


def test_only_the_fictional_sample_pdf_is_in_the_repo():
    pdfs = {f.relative_to(ROOT).as_posix() for f in tracked_files() if f.suffix.lower() == ".pdf"}
    assert pdfs <= {"samples/fictional_rfp.pdf"}


def test_env_example_has_no_real_key():
    assert "your-key-here" in (ROOT / ".env.example").read_text()
