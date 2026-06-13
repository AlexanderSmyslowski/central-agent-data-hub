from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_reviewer_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_HUB_REVIEWERS", raising=False)
