"""Deterministic workspace grouping from explicit project metadata."""

from __future__ import annotations


WORKSPACE_CATEGORY_ORDER = (
    "website_brand",
    "product_platform",
    "agent_infrastructure",
    "company_relevant",
    "unclassified",
    "empty_ad_hoc",
    "personal_private",
    "demo",
)

WORKSPACE_CATEGORY_LABEL_KEYS = {
    "website_brand": "workspace_category_website_brand",
    "product_platform": "workspace_category_product_platform",
    "agent_infrastructure": "workspace_category_agent_infrastructure",
    "company_relevant": "workspace_category_company_relevant",
    "unclassified": "workspace_category_unclassified",
    "empty_ad_hoc": "workspace_category_empty_ad_hoc",
    "personal_private": "workspace_category_personal_private",
    "demo": "workspace_category_demo",
}

WORKSPACE_CATEGORY_BODY_KEYS = {
    "website_brand": "workspace_category_website_brand_body",
    "product_platform": "workspace_category_product_platform_body",
    "agent_infrastructure": "workspace_category_agent_infrastructure_body",
    "company_relevant": "workspace_category_company_relevant_body",
    "unclassified": "workspace_category_unclassified_body",
    "empty_ad_hoc": "workspace_category_empty_ad_hoc_body",
    "personal_private": "workspace_category_personal_private_body",
    "demo": "workspace_category_demo_body",
}

WORKSPACE_CATEGORY_REASON_KEYS = {
    "website_brand": "workspace_reason_website_brand",
    "product_platform": "workspace_reason_product_platform",
    "agent_infrastructure": "workspace_reason_agent_infrastructure",
    "company_relevant": "workspace_reason_company_relevant",
    "unclassified": "workspace_reason_unclassified",
    "empty_ad_hoc": "workspace_reason_empty_ad_hoc",
    "personal_private": "workspace_reason_personal_private",
    "demo": "workspace_reason_demo",
}

WORKSPACE_COMPANY_CATEGORIES = frozenset(
    {
        "website_brand",
        "product_platform",
        "agent_infrastructure",
        "company_relevant",
    }
)
WORKSPACE_SEPARATE_CATEGORIES = frozenset(
    {"unclassified", "empty_ad_hoc", "personal_private", "demo"}
)

PROJECT_TYPE_CATEGORIES = {
    "website": "website_brand",
    "product": "product_platform",
    "ops": "agent_infrastructure",
    "business": "company_relevant",
    "personal": "personal_private",
    "demo": "demo",
}

MEMORY_SCOPE_CATEGORIES = {
    "website": "website_brand",
    "planned-website": "website_brand",
    "product": "product_platform",
    "product-platform": "product_platform",
    "platform": "product_platform",
    "tool": "product_platform",
    "agentic-operations": "agent_infrastructure",
    "agent-infrastructure": "agent_infrastructure",
    "business": "company_relevant",
    "company": "company_relevant",
    "organization": "company_relevant",
    "org": "company_relevant",
    "personal": "personal_private",
    "private": "personal_private",
    "demo": "demo",
}


def classify_workspace_project(
    project: dict[str, object],
    *,
    current_total: int,
    draft_count: int,
) -> dict[str, str]:
    """Group one project without interpreting its name, slug, or description."""
    metadata = project.get("metadata") or {}
    metadata = metadata if isinstance(metadata, dict) else {}
    project_type = str(metadata.get("project_type") or "").strip().lower()
    memory_scope = str(metadata.get("memory_scope") or "").strip().lower()
    is_demo = metadata.get("demo") is True

    scope_category = MEMORY_SCOPE_CATEGORIES.get(memory_scope)
    type_category = PROJECT_TYPE_CATEGORIES.get(project_type)

    # Demo and personal boundaries must remain visible even before memory exists.
    if is_demo:
        category = "demo"
    elif scope_category in {"demo", "personal_private"}:
        category = scope_category
    elif type_category in {"demo", "personal_private"}:
        category = type_category
    elif current_total == 0 and draft_count == 0:
        category = "empty_ad_hoc"
    elif scope_category:
        category = scope_category
    elif type_category:
        category = type_category
    else:
        category = "unclassified"

    return {
        "category": category,
        "label_key": WORKSPACE_CATEGORY_LABEL_KEYS[category],
        "body_key": WORKSPACE_CATEGORY_BODY_KEYS[category],
        "reason_key": WORKSPACE_CATEGORY_REASON_KEYS[category],
    }
