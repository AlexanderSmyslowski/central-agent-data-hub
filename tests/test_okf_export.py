from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

import yaml

from agent_hub.exporting import okf


PROJECT = {
    "id": "project-1",
    "slug": "demo-project",
    "name": "Demo Project",
    "description": "A demo project.",
    "status": "active",
    "metadata": {},
    "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    "updated_at": datetime(2026, 6, 2, tzinfo=timezone.utc),
}


def fact_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "11111111-1111-4111-8111-111111111111",
        "statement": "Reviewed facts can be exported as portable knowledge.",
        "source": "unit test",
        "confidence": 0.95,
        "status": "verified",
        "metadata": {"tags": ["portable-context"]},
        "created_at": datetime(2026, 6, 3, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 4, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_build_okf_files_outputs_conformant_markdown_bundle() -> None:
    files = okf.build_okf_files(
        project=PROJECT,
        rows_by_type={"fact": [fact_row()]},
        generated_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )
    by_path = {str(item.relative_path): item.content for item in files}

    assert "index.md" in by_path
    assert "log.md" in by_path
    assert "facts/index.md" in by_path
    fact_paths = [
        path
        for path in by_path
        if path.startswith("facts/") and path != "facts/index.md"
    ]
    assert len(fact_paths) == 1
    fact = by_path[fact_paths[0]]

    assert not by_path["index.md"].startswith("---")
    assert "OKF target: 0.1" in by_path["index.md"]
    assert "Snapshot timestamp: 2026-06-05T12:00:00+00:00" in by_path["index.md"]
    assert "Generated at" not in by_path["index.md"]
    assert "Excluded: drafts" in by_path["index.md"]

    match = re.match(r"---\n(.*?)\n---\n\n(.*)", fact, flags=re.S)
    assert match
    frontmatter = yaml.safe_load(match.group(1))
    assert frontmatter["type"] == "ADH Fact"
    assert frontmatter["title"] == "Reviewed facts can be exported as portable knowledge."
    assert frontmatter["resource"].startswith("adh://demo-project/fact/")
    assert frontmatter["review_status"] == "reviewed"
    assert frontmatter["adh_status"] == "verified"
    assert "portable-context" in frontmatter["tags"]
    assert "# Summary" in match.group(2)


def test_build_okf_files_without_generated_at_is_byte_stable() -> None:
    kwargs = {
        "project": PROJECT,
        "rows_by_type": {"fact": [fact_row()]},
    }

    first = okf.build_okf_files(**kwargs)
    second = okf.build_okf_files(**kwargs)

    assert [
        (item.relative_path, item.content) for item in first
    ] == [
        (item.relative_path, item.content) for item in second
    ]
    by_path = {str(item.relative_path): item.content for item in first}
    assert "Snapshot timestamp: 2026-06-04T00:00:00+00:00" in by_path["index.md"]
    assert "Generated at" not in by_path["index.md"]
    assert "## 2026-06-04" in by_path["log.md"]


def test_export_project_okf_reads_only_reviewed_statuses_and_writes_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeCursor:
        def __init__(self) -> None:
            self.rows: list[dict[str, object]] = []
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
            if re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql.upper()):
                raise AssertionError("OKF export must stay read-only")
            self.calls.append((sql, params))
            if "FROM projects" in sql:
                self.rows = [PROJECT]
            elif "FROM facts" in sql:
                assert params[1:] == ("verified",)
                self.rows = [fact_row()]
            elif "FROM decisions" in sql:
                assert params[1:] == ("accepted",)
                self.rows = []
            elif "FROM risks" in sql:
                assert params[1:] == ("open", "mitigating", "accepted")
                self.rows = []
            elif "FROM open_questions" in sql:
                assert params[1:] == ("open", "answered")
                self.rows = []
            elif "FROM reports" in sql:
                assert params[1:] == ("published",)
                self.rows = []
            else:
                raise AssertionError(f"unexpected query: {sql}")

        def fetchone(self) -> dict[str, object] | None:
            return self.rows[0] if self.rows else None

        def fetchall(self) -> list[dict[str, object]]:
            return self.rows

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

    fake_connection = FakeConnection()
    monkeypatch.setattr(okf, "connect", lambda: fake_connection)

    written = okf.export_project_okf("demo-project", tmp_path)

    assert tmp_path / "index.md" in written
    assert tmp_path / "facts" / "index.md" in written
    assert any(path.parent == tmp_path / "facts" and path.name != "index.md" for path in written)
    assert not any("draft" in str(call[1]) for call in fake_connection.cursor_instance.calls)
