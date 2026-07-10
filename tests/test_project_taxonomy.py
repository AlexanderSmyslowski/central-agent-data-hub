from __future__ import annotations

import pytest

from agent_hub.project_taxonomy import classify_workspace_project


def project_with_metadata(**metadata: object) -> dict[str, object]:
    return {
        "name": "Example Project",
        "slug": "example-project",
        "description": "Neutral project description.",
        "metadata": metadata,
    }


@pytest.mark.parametrize(
    ("metadata", "current_total", "draft_count", "expected"),
    [
        ({"demo": True}, 1, 0, "demo"),
        ({"project_type": "demo"}, 1, 0, "demo"),
        ({"project_type": "personal"}, 0, 0, "personal_private"),
        ({"project_type": "website"}, 1, 0, "website_brand"),
        ({"memory_scope": "product-platform"}, 1, 0, "product_platform"),
        ({"project_type": "ops"}, 1, 0, "agent_infrastructure"),
        ({"project_type": "business"}, 1, 0, "company_relevant"),
        ({"project_type": "research"}, 1, 0, "unclassified"),
        ({"project_type": "product"}, 0, 0, "empty_ad_hoc"),
    ],
)
def test_workspace_classification_uses_only_project_metadata_and_counts(
    metadata: dict[str, object],
    current_total: int,
    draft_count: int,
    expected: str,
) -> None:
    result = classify_workspace_project(
        project_with_metadata(**metadata),
        current_total=current_total,
        draft_count=draft_count,
    )

    assert result["category"] == expected


def test_workspace_classification_does_not_infer_from_visible_text() -> None:
    project = {
        "name": "Private Agent Demo",
        "slug": "private-agent-demo",
        "description": "A name should never decide this category.",
        "metadata": {"project_type": "research"},
    }

    result = classify_workspace_project(project, current_total=1, draft_count=0)

    assert result["category"] == "unclassified"
    assert result["reason_key"] == "workspace_reason_unclassified"
