from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "fictional_rfp.pdf"
GOLD = ROOT / "samples" / "gold.json"


@pytest.fixture(scope="session")
def sample_pages():
    from contractiq.pdf import read_pages
    return read_pages(SAMPLE)


@pytest.fixture(scope="session")
def sample_result():
    from contractiq.pipeline import run
    return run(SAMPLE)


@pytest.fixture(scope="session")
def gold():
    from contractiq.schema import Extraction
    return Extraction.model_validate_json(GOLD.read_text(encoding="utf-8"))


class FakeClient:
    """Stands in for anthropic.Anthropic(): returns queued tool inputs (or raises queued exceptions)."""

    def __init__(self, *replies, stop_reason="tool_use"):
        self.replies = list(replies)
        self.calls = []
        self.stop_reason = stop_reason
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        content = [] if reply is None else [NS(type="tool_use", id=f"toolu_{len(self.calls)}",
                                                 name="record_extraction", input=reply)]
        return NS(stop_reason=self.stop_reason, content=content)


@pytest.fixture
def fake_client():
    return FakeClient
