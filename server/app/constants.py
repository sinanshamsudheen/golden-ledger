"""
Shared constants used by both the FastAPI app and the worker pipeline.
"""

DOC_TYPES: list[str] = [
    "pitch_deck",
    "investment_memo",
    "prescreening_report",
    "meeting_minutes",
]

# Subset of DOC_TYPES that qualify a deal as a pipeline opportunity.
# Deals whose only documents are meeting_minutes are treated as client/portfolio.
PIPELINE_TYPES: frozenset[str] = frozenset(DOC_TYPES) - {"meeting_minutes"}
