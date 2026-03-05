"""
Field definitions for the ExtractFields API, keyed by investment_type.

Each FieldDef maps directly to one entry in the POST /api/ExtractFields
`fields` array:
  - field_name    → request `name`
  - description   → request `description` (retrieval query)
  - instructions  → request `instructions` (extraction prompt)
  - field_label   → UI display label
  - field_type    → original CSV type hint for UI rendering
                    (select | assetManagerSelect | geography | text | currency | range)
  - section       → UI grouping ("Opportunity overview" | "Key terms")

Source CSVs: Fund-Fields, Direct-Fields, Co-Investment-Fields
"""

from typing import TypedDict


class FieldDef(TypedDict):
    field_name: str
    field_label: str
    field_type: str
    section: str
    description: str
    instructions: str


# ── Shared field objects (reused across investment types) ─────────────────────

_ASSET_CLASS = FieldDef(
    field_name="prescreening_assetClass",
    field_label="Asset Class",
    field_type="select",
    section="Opportunity overview",
    description=(
        "The broad asset category of the investment. Look for: 'Asset Class:', "
        "stage indicators (Seed/Series A/B → Venture Capital, Buyout/Growth → Private Equity), "
        "sector mentions (Real Estate, Debt instruments → Private Debt), "
        "or investment classification sections."
    ),
    instructions=(
        "Determine asset class based on: Document explicit classification (highest priority). "
        "Stage indicators: Seed/Series A/B/C+ → Venture Capital; Buyout/Growth → Private Equity. "
        "Sector indicators: Real Estate sector → Real Estate asset class. "
        "Investment structure: Debt instruments → Private Debt. "
        "Return EXACTLY one of: Private Equity, Venture Capital, Real Estate, Private Debt, "
        "Hedge Fund, Infrastructure, Other. Match case exactly."
    ),
)

_ASSET_MANAGER = FieldDef(
    field_name="prescreening_assetManager",
    field_label="Asset Manager",
    field_type="assetManagerSelect",
    section="Opportunity overview",
    description=(
        "Name of the asset manager, sponsor, lead investor, or GP managing the opportunity. "
        "Look for: 'Asset Manager:', 'Sponsor:', 'General Partner:', 'Lead investor:', "
        "or managing firm name in co-investment contexts."
    ),
    instructions=(
        "Extract the asset manager or sponsor name. "
        "Look for: 'Asset Manager:', 'Sponsor:', 'General Partner:', 'Lead investor:', "
        "managing firm name. Return as plain text (company name only, no additional context). "
        "If not explicitly stated, return null."
    ),
)

_GEOGRAPHY = FieldDef(
    field_name="prescreening_geography",
    field_label="Geography",
    field_type="geography",
    section="Opportunity overview",
    description=(
        "Geographic allocation across regions as percentages. "
        "Look for: 'Geographic allocation:', 'Regional distribution:', "
        "percentage breakdowns by region/country, or portfolio geographic mix tables."
    ),
    instructions=(
        "Extract geographic allocation. "
        "Look for: 'Geographic allocation:', percentage breakdowns by region/country. "
        "Return as plain text describing the breakdown "
        "(e.g. 'North America 50%, Europe 30%, Asia 20%'). "
        "If not found, return null."
    ),
)

_INVESTMENT_TYPE_FIELD = FieldDef(
    field_name="prescreening_investmentType",
    field_label="Investment Type",
    field_type="select",
    section="Opportunity overview",
    description=(
        "The type of investment structure: Fund (pooled vehicle), "
        "Co-investment (alongside a sponsor), or Direct investment (direct equity stake). "
        "Look for: 'Investment Type:', fund structure descriptions, "
        "co-investment keywords ('alongside', 'sponsor-led'), or direct equity indicators."
    ),
    instructions=(
        "Determine investment type from document characteristics. "
        "Check for explicit statement 'Investment Type: Fund/Co-investment/Direct'. "
        "Fund indicators: 'Fund' in name, fund size field present. "
        "Co-investment keywords: 'co-invest', 'alongside', 'sponsor', 'lead manager'. "
        "Direct investment keywords: 'direct equity', 'primary investment', 'company investment'. "
        "Default to 'Fund' if ambiguous. Return one of: Fund, Co-investment, Direct, Other."
    ),
)

_OPPORTUNITY_NAME = FieldDef(
    field_name="prescreening_opportunityName",
    field_label="Opportunity Name",
    field_type="text",
    section="Opportunity overview",
    description=(
        "The formal name of the investment opportunity, fund, or company. "
        "Look for: document title, 'Opportunity Name:', 'Fund Name:', 'Company Name:', "
        "executive summary header, or primary stated name in the introduction."
    ),
    instructions=(
        "Extract the opportunity name using only explicitly stated information. "
        "Look for: 'Opportunity Name:', 'Fund Name:', 'Company Name:', document title/header. "
        "No hallucination or inference — if not explicitly stated, return null. "
        "Return as plain text. Must be the opportunity being analyzed, "
        "not an opportunity mentioned in the track record."
    ),
)

_SUB_ASSET_CLASS = FieldDef(
    field_name="prescreening_subAssetClass",
    field_label="Sub Asset Class",
    field_type="select",
    section="Opportunity overview",
    description=(
        "The sub-asset class or specific investment stage within the broader asset class. "
        "Look for: 'Stage:', 'Sub-Asset Class:', maturity indicators "
        "(Early-stage, Growth, Late-stage, Buyout), or detailed classification sections."
    ),
    instructions=(
        "Extract the sub-asset class or stage. "
        "Look for: 'Stage:', 'Sub-Asset Class:', "
        "specific stage mentions (Early-stage, Growth, Late-stage, Buyout, Venture). "
        "Return as plain text. If not explicitly stated, infer from context "
        "(funding round, company maturity). If uncertain, return null."
    ),
)

_SECTOR = FieldDef(
    field_name="prescreening_sector",
    field_label="Sector",
    field_type="select",
    section="Opportunity overview",
    description=(
        "The primary industry or investment focus of the opportunity currently being evaluated. "
        "Reflects the main area in which the business operates or the fund primarily invests. "
        "References to past investments, portfolio examples, or track record "
        "must not influence the classification."
    ),
    instructions=(
        "Extract the sector only if explicitly stated as the focus of the current opportunity. "
        "Look for: 'Sector', 'Industry', 'Focus', 'Strategy', or equivalent labels. "
        "Do not infer from examples, prior investments, or thematic language. "
        "If multiple sectors listed, select the primary one for the opportunity under review. "
        "If no explicit sector stated, return null. Plain text only."
    ),
)

_STAGE = FieldDef(
    field_name="prescreening_stage",
    field_label="Stage",
    field_type="select",
    section="Opportunity overview",
    description=(
        "The explicit venture financing stage of the company at the time of the transaction "
        "(e.g., Pre-Seed, Seed, Series A, Series B, Series C, Late-Stage, Pre-IPO), "
        "as stated in the source documents."
    ),
    instructions=(
        "Extract the venture stage exactly as explicitly stated. "
        "Look for: 'Pre-Seed', 'Seed', 'Series A/B/C', 'Growth Round', 'Pre-IPO' "
        "in the transaction description or financing section. "
        "Select the stage for the current round, not prior historical rounds. "
        "Do not infer from revenue, valuation, maturity, or narrative context. "
        "If not explicitly stated, return null. Plain text only."
    ),
)

_FUND_SIZE = FieldDef(
    field_name="prescreening_fundSize",
    field_label="Fund Size",
    field_type="currency",
    section="Key terms",
    description=(
        "The total target or stated size of the fund currently being raised or managed, "
        "as explicitly indicated in the documents. "
        "Reflects the fund's overall capital base, not the firm's AuM or individual deal sizes."
    ),
    instructions=(
        "Extract the total fund size exactly as explicitly stated. "
        "Look for: 'Fund Size', 'Target Size', 'Hard Cap', 'Fundraising Target', "
        "or equivalent language describing total fund capital. "
        "Do not confuse with AuM, partial commitments, transaction value, "
        "or portfolio company valuations. "
        "If target and hard cap both present, return the primary target size. "
        "Do not infer or calculate. If not explicitly stated, return null. Plain text only."
    ),
)

_PRE_MONEY_VALUATION = FieldDef(
    field_name="prescreening_preMoneyValuation",
    field_label="Pre-money Valuation",
    field_type="currency",
    section="Key terms",
    description=(
        "Company valuation before this investment round. "
        "Look for: 'Pre-money valuation:', 'Valuation:', 'Company valued at:', "
        "or valuation figures explicitly stated as pre-money."
    ),
    instructions=(
        "Extract pre-money valuation exactly as stated, including currency and units "
        "(e.g. '$50M', '50 million USD', '€80M'). "
        "Look for: 'Pre-money valuation:', figures explicitly stated as pre-money. "
        "If only post-money available, return null (do not calculate). "
        "If not found, return null."
    ),
)

_ROUND_SIZE = FieldDef(
    field_name="prescreening_roundSize",
    field_label="Round Size",
    field_type="currency",
    section="Key terms",
    description=(
        "Total size of the current funding round. "
        "Look for: 'Round size:', 'Funding amount:', 'Investment size:', 'Raise amount:', "
        "or total capital being raised for this specific round."
    ),
    instructions=(
        "Extract the funding round size with currency and units "
        "(e.g. '$200M', '200 million USD'). "
        "Look for: 'Round size:', 'Funding amount:', 'Investment size:'. "
        "If not found, return null."
    ),
)

_TARGET_HOLDING_PERIOD = FieldDef(
    field_name="prescreening_targetHoldingPeriod",
    field_label="Target Holding Period",
    field_type="range",
    section="Key terms",
    description=(
        "Target investment holding period in years. "
        "Look for: 'Holding period:', 'Investment horizon:', 'Expected hold:', "
        "timeframe mentions in years, or fund term descriptions."
    ),
    instructions=(
        "Extract the target holding period including units "
        "(e.g. '5 years', '3-5 years', '4.6 years'). "
        "Look for: 'Holding period:', 'Investment horizon:', timeframe in years. "
        "If not found, return null."
    ),
)

_TARGET_IRR_GROSS = FieldDef(
    field_name="prescreening_targetIRRGross",
    field_label="Target IRR (Gross)",
    field_type="range",
    section="Key terms",
    description=(
        "Target Internal Rate of Return BEFORE FEES as a percentage or range. "
        "Look for: 'Target Gross IRR:', 'Expected Gross IRR:', 'Gross IRR:', "
        "performance projections, or return expectation sections."
    ),
    instructions=(
        "Extract target IRR BEFORE FEES including % symbol "
        "(e.g. '20-25%', '28%'). "
        "Look for: 'Gross IRR:', 'Target IRR:', 'Expected IRR:'. "
        "If not found, return null."
    ),
)

_TARGET_IRR_NET = FieldDef(
    field_name="prescreening_targetIRRNet",
    field_label="Target IRR (Net)",
    field_type="range",
    section="Key terms",
    description=(
        "Target Internal Rate of Return AFTER FEES as a percentage or range. "
        "Look for: 'Target Net IRR:', 'Expected Net IRR:', 'Net IRR:', "
        "performance projections, or return expectation sections."
    ),
    instructions=(
        "Extract target IRR AFTER FEES including % symbol "
        "(e.g. '18-22%', '25%'). "
        "Look for: 'Net IRR:', 'Target Net IRR:', 'Expected Net IRR:'. "
        "If not found, return null."
    ),
)

_TARGET_MOIC_GROSS = FieldDef(
    field_name="prescreening_targetMOICGross",
    field_label="Target MOIC (Gross)",
    field_type="range",
    section="Key terms",
    description=(
        "Target Multiple on Invested Capital BEFORE FEES (e.g., 2.5-3.0x). "
        "Look for: 'Target MOIC:', 'Expected multiple:', 'Gross MOIC:', "
        "return projections, or cash-on-cash multiple expectations."
    ),
    instructions=(
        "Extract target MOIC BEFORE FEES including x suffix "
        "(e.g. '2.5-3.0x', '3.2x'). "
        "Look for: 'Gross MOIC:', 'Target MOIC:', 'Expected multiple:'. "
        "If not found, return null."
    ),
)

_TARGET_MOIC_NET = FieldDef(
    field_name="prescreening_targetMOICNet",
    field_label="Target MOIC (Net)",
    field_type="range",
    section="Key terms",
    description=(
        "Target Multiple on Invested Capital AFTER FEES (e.g., 2.5-3.0x). "
        "Look for: 'Target MOIC:', 'Expected multiple:', 'Net MOIC:', "
        "return projections, or cash-on-cash multiple expectations."
    ),
    instructions=(
        "Extract target MOIC AFTER FEES including x suffix "
        "(e.g. '2.0-2.5x', '2.8x'). "
        "Look for: 'Net MOIC:', 'Target Net MOIC:', 'Expected multiple:'. "
        "If not found, return null."
    ),
)

_TARGET_YIELD = FieldDef(
    field_name="prescreening_targetYield",
    field_label="Target Yield",
    field_type="range",
    section="Key terms",
    description=(
        "Target annual yield as a percentage or range. "
        "Reflects expected gross income return component "
        "(distributions, coupons, rental yield) prior to management fees."
    ),
    instructions=(
        "Extract the target yield including % symbol "
        "(e.g. '6-8%', '9%'). "
        "Look for: 'Target Yield', 'Expected Yield', 'Gross Yield', 'Income Yield'. "
        "Do not infer yield from IRR or total return metrics. "
        "If not explicitly stated, return null."
    ),
)


# ── Per-type field lists (order = display order in UI) ────────────────────────

FUND_FIELDS: list[FieldDef] = [
    _ASSET_CLASS,
    _ASSET_MANAGER,
    _GEOGRAPHY,
    _INVESTMENT_TYPE_FIELD,
    _OPPORTUNITY_NAME,
    _SUB_ASSET_CLASS,
    _FUND_SIZE,
    _TARGET_HOLDING_PERIOD,
    _TARGET_IRR_GROSS,
    _TARGET_IRR_NET,
    _TARGET_MOIC_GROSS,
    _TARGET_MOIC_NET,
    _TARGET_YIELD,
]

DIRECT_FIELDS: list[FieldDef] = [
    _ASSET_CLASS,
    _GEOGRAPHY,
    _INVESTMENT_TYPE_FIELD,
    _OPPORTUNITY_NAME,
    _SECTOR,
    _STAGE,
    _SUB_ASSET_CLASS,
    _PRE_MONEY_VALUATION,
    _ROUND_SIZE,
    _TARGET_HOLDING_PERIOD,
    _TARGET_IRR_GROSS,
    _TARGET_IRR_NET,
    _TARGET_MOIC_GROSS,
    _TARGET_MOIC_NET,
    _TARGET_YIELD,
]

CO_INVESTMENT_FIELDS: list[FieldDef] = [
    _ASSET_CLASS,
    _ASSET_MANAGER,
    _GEOGRAPHY,
    _INVESTMENT_TYPE_FIELD,
    _OPPORTUNITY_NAME,
    _SECTOR,
    _STAGE,
    _SUB_ASSET_CLASS,
    _PRE_MONEY_VALUATION,
    _ROUND_SIZE,
    _TARGET_HOLDING_PERIOD,
    _TARGET_IRR_GROSS,
    _TARGET_IRR_NET,
    _TARGET_MOIC_GROSS,
    _TARGET_MOIC_NET,
    _TARGET_YIELD,
]

# ── Lookup by investment_type (as returned by Analytical endpoint) ────────────
FIELDS_BY_INVESTMENT_TYPE: dict[str, list[FieldDef]] = {
    "Fund": FUND_FIELDS,
    "Direct": DIRECT_FIELDS,
    "Co-Investment": CO_INVESTMENT_FIELDS,
}
