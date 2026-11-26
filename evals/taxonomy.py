"""Interest taxonomy used to score lead capture (plan default for Q4)."""
from typing import Optional

CATEGORIES = {
    "market_landscaping": "Market Landscaping",
    "opportunity_assessment": "Opportunity Landscape / Assessment",
    "partner_identification": "Partner Identification & Ecosystem Building",
    "due_diligence": "Due Diligence & Deal Structuring",
    "go_to_market": "Go-to-Market Strategy & Entry Blueprint",
    "local_presence": "Local Presence & Market Entry Execution",
    "sales_marketing": "Sales, Marketing & Ecosystem Enablement",
    "back_office": "Back Office & Corporate Support",
    "membership": "Membership",
    "jisc": "JISC / Semiconductors",
    "events": "Events & Delegations",
    "innovation_hub": "R&I Hub / Innovation",
    "other": "Other",
}

_BY_LABEL = {v.lower(): k for k, v in CATEGORIES.items()}


def category_for_service(value: Optional[str]) -> Optional[str]:
    """Map a stored service label (legacy) or category id (new) to a category id."""
    if not value:
        return None
    v = value.strip()
    if v in CATEGORIES:
        return v
    return _BY_LABEL.get(v.lower(), "other")
