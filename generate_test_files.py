#!/usr/bin/env python3
"""Generate 50 test files for investment document intelligence system."""

import os
import random
from datetime import datetime, timedelta

# Seed for reproducibility
random.seed(42)

# Folder structure
FOLDERS = {
    "Acme Robotics/2024/Q1": 8,
    "Acme Robotics/Fundraising": 4,
    "Beta Health/Diligence": 6,
    "Beta Health/Board": 5,
    "Gamma Fintech": 7,
    "misc": 8,
    "docs": 7,
    "archive/Zeta Energy": 5,
}

# Deals and their document counts
DEALS = {
    "acme": {"name": "Acme Robotics", "count": 6, "keywords": ["robotics", "automation", "manufacturing", "industrial"]},
    "beta": {"name": "Beta Health", "count": 5, "keywords": ["healthcare", "medical", "biotech", "clinical"]},
    "gamma": {"name": "Gamma Fintech", "count": 4, "keywords": ["fintech", "payments", "banking", "financial"]},
    "zeta": {"name": "Zeta Energy", "count": 3, "keywords": ["energy", "renewable", "solar", "clean tech"]},
}

# Document types with their required phrases
DOC_TYPES = {
    "pitch_deck": {
        "prefix": "pitchdeck",
        "phrases": ["pitch deck", "company overview", "go to market", "funding round", "series a", "series b", "seed round", "venture capital", "investor presentation"],
        "required_count": 3,
    },
    "investment_memo": {
        "prefix": "memo",
        "phrases": ["investment memo", "investment thesis", "deal overview", "deal analysis", "investment committee", "term sheet", "diligence summary"],
        "required_count": 3,
    },
    "prescreening_report": {
        "prefix": "prescreen",
        "phrases": ["prescreening", "initial review", "opportunity assessment", "screening report", "deal screening", "initial assessment", "first look"],
        "required_count": 3,
    },
    "meeting_minutes": {
        "prefix": "minutes",
        "phrases": ["meeting minutes", "attendees", "action items", "agenda", "discussed", "follow-up items", "resolved", "board minutes"],
        "required_count": 3,
    },
    "random": {
        "prefix": "doc",
        "phrases": [],
        "required_count": 0,
    },
}

def random_date():
    """Generate random date between 2023-06-01 and 2025-01-01."""
    start = datetime(2023, 6, 1)
    end = datetime(2025, 1, 1)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")

def generate_pitch_deck_content(deal_info):
    """Generate pitch deck content."""
    templates = [
        f"""This {DOC_TYPES['pitch_deck']['phrases'][0]} presents {deal_info['name']}'s vision for transforming the {random.choice(deal_info['keywords'])} industry. 
The {DOC_TYPES['pitch_deck']['phrases'][1]} section outlines our core technology platform and competitive advantages in the market. 
Our {DOC_TYPES['pitch_deck']['phrases'][2]} strategy focuses on direct enterprise sales followed by channel partnerships.

We are currently raising a {random.choice(['seed round', 'Series A', 'Series B'])} to accelerate product development and market expansion. 
The {DOC_TYPES['pitch_deck']['phrases'][3]} targets $15M to achieve key milestones over the next 18 months. 
Our {DOC_TYPES['pitch_deck']['phrases'][8]} highlights strong unit economics and clear path to profitability.

Key metrics include 40% month-over-month growth, $2M ARR, and partnerships with three Fortune 500 companies. 
The founding team brings decades of experience from leading technology companies. 
We project reaching $50M ARR within three years of this funding round.""",

        f"""Welcome to the {deal_info['name']} {DOC_TYPES['pitch_deck']['phrases'][0]}. We are revolutionizing {random.choice(deal_info['keywords'])} through AI-powered automation.
The {DOC_TYPES['pitch_deck']['phrases'][1]} demonstrates our unique approach to solving critical industry pain points.

Our {DOC_TYPES['pitch_deck']['phrases'][3]} is structured as a {random.choice(['seed round', 'Series A'])} with participation from top-tier {DOC_TYPES['pitch_deck']['phrases'][7]} firms.
The {DOC_TYPES['pitch_deck']['phrases'][2]} includes both direct sales and strategic partnerships with system integrators.
Current traction includes pilot programs with five enterprise customers and LOIs totaling $3M.

This {DOC_TYPES['pitch_deck']['phrases'][8]} covers market opportunity, competitive landscape, and financial projections.
We are seeking partners who understand the long-term value creation in this sector.""",

        f"""{deal_info['name']} - {DOC_TYPES['pitch_deck']['phrases'][8]} for {random.choice(deal_info['keywords'])} innovation.

Company Overview: We have developed proprietary technology that reduces operational costs by 60% while improving accuracy.
The {DOC_TYPES['pitch_deck']['phrases'][1]} includes detailed product roadmap and go-to-market timeline.

Our {DOC_TYPES['pitch_deck']['phrases'][2]} strategy leverages existing distribution channels in the {random.choice(deal_info['keywords'])} vertical.
We are pursuing a {random.choice(['seed round', 'Series A', 'Series B'])} to scale operations and expand the engineering team.
The {DOC_TYPES['pitch_deck']['phrases'][3]} terms include standard protective provisions and board composition.

{DOC_TYPES['pitch_deck']['phrases'][7]} partners will benefit from significant upside as we capture market share.
Financial projections show profitability within 24 months post-funding.""",
    ]
    return random.choice(templates)

def generate_investment_memo_content(deal_info):
    """Generate investment memo content."""
    templates = [
        f"""INVESTMENT MEMO: {deal_info['name']}

This {DOC_TYPES['investment_memo']['phrases'][0]} recommends proceeding with a $5M investment in {deal_info['name']}.
The {DOC_TYPES['investment_memo']['phrases'][1]} centers on the company's differentiated technology and strong market position in {random.choice(deal_info['keywords'])}.

{DOC_TYPES['investment_memo']['phrases'][3]} reveals compelling unit economics with 75% gross margins and improving CAC payback periods.
Management has demonstrated execution capability, hitting all milestones from the previous funding round.

The {DOC_TYPES['investment_memo']['phrases'][5]} includes standard terms with a post-money valuation of $25M.
{DOC_TYPES['investment_memo']['phrases'][6]} indicates low regulatory risk and clear competitive moats.
Recommendation: Proceed to {DOC_TYPES['investment_memo']['phrases'][4]} for final approval.""",

        f"""Confidential {DOC_TYPES['investment_memo']['phrases'][0]} - {deal_info['name']}

{DOC_TYPES['investment_memo']['phrases'][2]}: {deal_info['name']} operates in the {random.choice(deal_info['keywords'])} sector with a SaaS-based platform.
The {DOC_TYPES['investment_memo']['phrases'][1]} highlights three key value drivers: technology differentiation, market timing, and team quality.

Our {DOC_TYPES['investment_memo']['phrases'][3]} shows strong revenue growth (3x YoY) and improving retention metrics (120% NRR).
The proposed {DOC_TYPES['investment_memo']['phrases'][5]} terms provide appropriate downside protection through liquidation preferences.

{DOC_TYPES['investment_memo']['phrases'][6]} covers commercial, technical, and legal diligence - all areas show acceptable risk levels.
This memo is submitted to the {DOC_TYPES['investment_memo']['phrases'][4]} for consideration at the next meeting.""",

        f"""Investment Committee Memorandum - {deal_info['name']}

Executive Summary: This {DOC_TYPES['investment_memo']['phrases'][0]} presents an opportunity to invest in a leading {random.choice(deal_info['keywords'])} company.
The {DOC_TYPES['investment_memo']['phrases'][1]} is built on secular tailwinds and the company's #1 market position.

Key {DOC_TYPES['investment_memo']['phrases'][2]} elements include $3M ARR, 95% gross retention, and expanding TAM.
{DOC_TYPES['investment_memo']['phrases'][3]} validates the financial model and confirms management projections are achievable.

The {DOC_TYPES['investment_memo']['phrases'][5]} negotiation is advanced, with key terms agreed including valuation and board seats.
{DOC_TYPES['investment_memo']['phrases'][4]} approval is requested for a $4M investment at a $20M post-money valuation.""",
    ]
    return random.choice(templates)

def generate_prescreening_content(deal_info):
    """Generate prescreening report content."""
    templates = [
        f"""PRESCREENING REPORT - {deal_info['name']}

This {DOC_TYPES['prescreening_report']['phrases'][0]} evaluates {deal_info['name']} for potential investment in the {random.choice(deal_info['keywords'])} sector.
The {DOC_TYPES['prescreening_report']['phrases'][1]} was conducted over a two-week period with management interviews and market research.

{DOC_TYPES['prescreening_report']['phrases'][4]} criteria include market size (> $1B), growth rate (>30%), and defensible technology.
{deal_info['name']} scores favorably on all dimensions with particular strength in team background.

The {DOC_TYPES['prescreening_report']['phrases'][5]} indicates strong product-market fit based on customer references.
Our {DOC_TYPES['prescreening_report']['phrases'][6]} suggests this opportunity warrants full diligence.

Recommendation: Advance to investment committee for term sheet discussion.""",

        f"""Initial Assessment: {deal_info['name']}

This {DOC_TYPES['prescreening_report']['phrases'][6]} covers {deal_info['name']}, a {random.choice(deal_info['keywords'])} company seeking Series A funding.
The {DOC_TYPES['prescreening_report']['phrases'][3]} framework evaluates market, product, team, and traction.

Market analysis shows $5B TAM with fragmented competition - opportunity for category leader.
{DOC_TYPES['prescreening_report']['phrases'][0]} findings indicate 2x revenue growth and improving unit economics.

The {DOC_TYPES['prescreening_report']['phrases'][4]} process identified no major red flags. Reference calls with customers were positive.
{DOC_TYPES['prescreening_report']['phrases'][2]} concludes this is a compelling opportunity aligned with fund thesis.

Next steps: Schedule partner meeting and begin drafting term sheet.""",

        f"""Deal Screening Summary - {deal_info['name']}

Purpose: This {DOC_TYPES['prescreening_report']['phrases'][3]} provides initial evaluation of {deal_info['name']} in the {random.choice(deal_info['keywords'])} space.
The {DOC_TYPES['prescreening_report']['phrases'][0]} was initiated following partner referral and inbound interest.

Key findings from {DOC_TYPES['prescreening_report']['phrases'][5]}:
- Strong founding team with prior exits
- Differentiated IP in core technology
- Early traction with pilot customers
- Reasonable valuation expectations

The {DOC_TYPES['prescreening_report']['phrases'][1]} included competitive analysis and customer interviews.
{DOC_TYPES['prescreening_report']['phrases'][4]} score: 8/10 - recommend proceeding to full diligence.""",
    ]
    return random.choice(templates)

def generate_meeting_minutes_content(deal_info):
    """Generate meeting minutes content."""
    templates = [
        f"""MEETING MINUTES - {deal_info['name']} Investment Discussion

Date: {random_date()}
Attendees: Sarah Chen (Partner), Mike Rodriguez (Principal), James Liu (Associate), External Counsel

Agenda: Review of {deal_info['name']} investment opportunity and term sheet discussion.

The meeting was called to order at 10:00 AM. Sarah presented the {DOC_TYPES['meeting_minutes']['phrases'][5]} for the {deal_info['name']} deal.

Key Discussion Points:
- Valuation range discussed between $18-22M post-money
- Board composition discussed - agreed on 2-2-1 structure
- Liquidation preference terms reviewed and accepted

Action Items:
- Mike to complete reference calls by Friday
- James to coordinate legal diligence kickoff
- Sarah to schedule follow-up with founders

Follow-up Items:
- Term sheet circulation targeted for next week
- Investment committee presentation scheduled for month-end

Meeting adjourned at 11:30 AM. Next meeting scheduled for Thursday.""",

        f"""Board Minutes - {deal_info['name']} Quarterly Review

Attendees: Board Members - David Park (Chair), Emily Watson, Robert Kim, Observer: Lisa Zhang

Agenda: Q4 performance review, 2024 planning, and financing update.

{DOC_TYPES['meeting_minutes']['phrases'][4]} topics included:
1. Revenue performance - 15% above plan
2. Hiring progress - 8 new employees onboarded
3. Product roadmap - two major releases on track
4. Fundraising status - term sheets received from two firms

The board reviewed financial statements and discussed cash runway.
Concerns were raised about competitive dynamics in the {random.choice(deal_info['keywords'])} market.

Action Items:
- Management to provide updated financial model by EOW
- CEO to schedule customer calls with David and Emily
- CFO to prepare board deck for next meeting

Resolved: Board approved the 2024 operating plan and budget.

Follow-up Items: Financing process update at next board meeting.""",

        f"""Investment Committee Meeting Minutes

Date: {random_date()}
Attendees: All Partners, Investment Team, Guest: {deal_info['name']} Founders

Agenda: {deal_info['name']} investment recommendation and vote.

The meeting commenced with management presentation. Founders {DOC_TYPES['meeting_minutes']['phrases'][4]} company history, product, and traction.

Key metrics presented:
- ARR: $2.5M, growing 15% MoM
- Gross margin: 78%
- Net revenue retention: 115%

Partners discussed market opportunity in {random.choice(deal_info['keywords'])} and competitive positioning.
Questions were raised about customer concentration and sales cycle length.

Action Items:
- Associate team to verify customer references
- Legal to begin document review
- Partner lead to negotiate final terms

Follow-up Items: Final vote scheduled for next IC meeting.

The committee discussed valuation and agreed on investment parameters.
Meeting concluded with preliminary approval pending diligence completion.""",
    ]
    return random.choice(templates)

def generate_random_content(deal_info):
    """Generate random document content."""
    templates = [
        f"""Due Diligence Checklist - {deal_info['name']}

This document outlines the due diligence requirements for the {deal_info['name']} transaction.

Corporate Documents:
- Certificate of incorporation and bylaws
- Cap table and stock ledger
- Board consents and meeting minutes
- Material contracts and agreements

Financial Information:
- Historical financial statements (3 years)
- Current year budget and projections
- Tax returns and filings
- Debt schedules and financing documents

Commercial Due Diligence:
- Customer contracts and revenue breakdown
- Pipeline and sales metrics
- Competitive analysis
- Market research reports

Legal Matters:
- Intellectual property portfolio
- Litigation history and pending matters
- Regulatory compliance documentation
- Employment agreements and benefits plans

Timeline: All documents requested by end of week.
Data room access granted to deal team members only.""",

        f"""Financial Summary - {deal_info['name']}

Revenue Analysis:
Total ARR: $2.8M as of Q4 2024
Growth Rate: 45% YoY, 12% QoQ
Gross Margin: 76% (improving from 71% last year)

Customer Metrics:
Total Customers: 47 (up from 28 last year)
Enterprise Customers: 12
Average Contract Value: $60K
Net Revenue Retention: 118%

Unit Economics:
CAC: $18K (blended)
CAC Payback: 14 months
LTV/CAC Ratio: 4.2x

Cash Flow:
Monthly Burn: $180K
Cash on Hand: $3.2M
Runway: 18 months

Key Observations:
- Strong revenue growth with improving efficiency
- Healthy retention indicates product-market fit
- Path to profitability visible within 12 months
- Financing recommended to accelerate growth""",

        f"""Market Analysis - {deal_info['name']} Sector Overview

Industry: {random.choice(deal_info['keywords'])}
Market Size: $8.5B TAM, $2.1B SAM, $450M SOM

Market Dynamics:
The {random.choice(deal_info['keywords'])} sector is experiencing rapid transformation driven by technology adoption and regulatory changes.
Key trends include automation, AI integration, and shift to subscription models.

Competitive Landscape:
- Incumbents: Large enterprises with legacy solutions
- Challengers: Well-funded startups with modern platforms
- {deal_info['name']} Position: Differentiated technology with early mover advantage

Growth Drivers:
1. Increasing demand for efficiency and cost reduction
2. Regulatory requirements driving adoption
3. Technology maturity enabling new use cases
4. Customer willingness to adopt cloud-based solutions

Risks:
- Economic downturn affecting IT budgets
- Increased competition from well-funded players
- Potential regulatory changes

Conclusion: Attractive market with favorable dynamics for innovative solutions.""",

        f"""Technical Due Diligence Report - {deal_info['name']}

Architecture Review:
The platform utilizes modern cloud-native architecture with microservices design.
Technology stack includes Python/Node.js backend, React frontend, PostgreSQL database.

Scalability Assessment:
- Current capacity handles 10x current load
- Auto-scaling configured for peak demand
- Database sharding strategy in place for future growth

Security Evaluation:
- SOC 2 Type II certification in progress
- Encryption at rest and in transit
- Regular penetration testing conducted
- Access controls and audit logging implemented

Code Quality:
- Test coverage: 78%
- CI/CD pipeline established
- Code review process documented
- Technical debt identified and tracked

Team Assessment:
- Engineering team: 12 FTEs
- Strong background from top technology companies
- Clear development processes and documentation

Recommendation: Technology platform is sound with manageable risks.""",
    ]
    return random.choice(templates)

def generate_content(doc_type, deal_info):
    """Generate content based on document type."""
    if doc_type == "pitch_deck":
        return generate_pitch_deck_content(deal_info)
    elif doc_type == "investment_memo":
        return generate_investment_memo_content(deal_info)
    elif doc_type == "prescreening_report":
        return generate_prescreening_content(deal_info)
    elif doc_type == "meeting_minutes":
        return generate_meeting_minutes_content(deal_info)
    else:
        return generate_random_content(deal_info)

def get_deal_info_for_folder(folder):
    """Determine which deal info to use based on folder path."""
    if "Acme" in folder:
        return DEALS["acme"]
    elif "Beta" in folder:
        return DEALS["beta"]
    elif "Gamma" in folder:
        return DEALS["gamma"]
    elif "Zeta" in folder:
        return DEALS["zeta"]
    else:
        # For misc/docs, randomly assign or use None for orphan files
        return random.choice(list(DEALS.values()))

def main():
    files_created = []
    file_count = 0
    
    # Document types (excluding random which is ~10%)
    doc_type_keys = ["pitch_deck", "investment_memo", "prescreening_report", "meeting_minutes"]
    
    # Track deal counts
    deal_counts = {deal: 0 for deal in DEALS.keys()}
    orphan_count = 0
    
    for folder, num_files in FOLDERS.items():
        for i in range(num_files):
            # Determine deal assignment
            folder_deal = get_deal_info_for_folder(folder)
            
            # Handle orphan files (2 total - one in misc, one in docs)
            if folder == "misc" and i == 0:
                deal_info = {"name": "Unknown Corp", "keywords": ["technology"]}
                deal_key = "orphan_misc"
            elif folder == "docs" and i == 0:
                deal_info = {"name": "Stealth Co", "keywords": ["software"]}
                deal_key = "orphan_docs"
            else:
                deal_info = folder_deal
                deal_key = None
                for k, v in DEALS.items():
                    if v["name"] == deal_info["name"]:
                        deal_key = k
                        break
            
            # Select document type (10% random)
            if random.random() < 0.10:
                doc_type = "random"
            else:
                doc_type = random.choice(doc_type_keys)
            
            # Generate filename
            date_str = random_date().replace("-", "")
            if deal_key and deal_key.startswith("orphan"):
                filename = f"{deal_info['name'].lower().replace(' ', '_')}_{DOC_TYPES[doc_type]['prefix']}_{date_str}.txt"
            else:
                deal_prefix = deal_key
                filename = f"{deal_prefix}_{DOC_TYPES[doc_type]['prefix']}_{date_str}.txt"
            
            # Generate content
            date = random_date()
            content = generate_content(doc_type, deal_info)
            
            # Create full file content
            full_content = f"Date: {date}\n\n{content}"
            
            # Write file
            filepath = f"TestDrive/{folder}/{filename}"
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                f.write(full_content)
            
            files_created.append((filepath, date, doc_type, deal_info["name"]))
            file_count += 1
    
    # Print summary
    print(f"Created {file_count} files")
    print("\n=== FILE LIST ===\n")
    
    for filepath, date, doc_type, deal in files_created:
        print(f"=== PATH: {filepath} ===")
        print(f"Date: {date}")
        print(f"Type: {doc_type}")
        print(f"Deal: {deal}")
        print()
    
    # Print content for all files
    print("\n\n=== FULL FILE CONTENTS ===\n")
    for filepath, date, doc_type, deal in files_created:
        with open(filepath, "r") as f:
            content = f.read()
        print(f"=== PATH: {filepath} ===")
        print(content)
        print("\n")

if __name__ == "__main__":
    main()
