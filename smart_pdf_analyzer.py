"""
Smart PDF Analyzer — Universal Financial Document Intelligence Engine.

This module is the brain behind the Upload & Analyze feature. It can read
virtually ANY financial PDF and intelligently extract, classify, and route
data into the correct household or business profile fields.

Supported Document Types:
─────────────────────────
INDIVIDUAL / HOUSEHOLD:
  • Brokerage & Investment Statements (Schwab, Fidelity, Vanguard, IBKR, etc.)
  • Bank Statements (checking, savings, CDs — balances & transactions)
  • Tax Documents (W-2, 1099-INT/DIV/B/R/MISC, K-1, 1040 returns)
  • Insurance Policies (life, health, disability, homeowners, auto, umbrella)
  • Estate Planning Documents (wills, trusts, POA, beneficiary designations)
  • Real Estate & Mortgage Documents (HUD, mortgage notes, tax bills, appraisals)
  • Retirement Plan Documents (401k/IRA statements, SS statements, pensions)
  • Personal Financial Outlines / Net Worth Summaries
  • Pay Stubs / Compensation Summaries

BUSINESS:
  • Income Statements / P&L
  • Balance Sheets
  • Cash Flow Statements
  • Tax Returns (1120, 1120S, 1065)
  • Bank Statements
  • Business Valuations
  • AR/AP Aging Reports

Architecture:
  1. PDF text & table extraction via pdfplumber
  2. Document type classification via keyword scoring
  3. Specialized extractors per document type
  4. Data normalization and validation
  5. Routing into the correct profile fields
"""

import re
import os
import json
import hashlib
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict

try:
    import pdfplumber
except ImportError:
    raise ImportError("pdfplumber required: pip install pdfplumber")


# ═══════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════

def clean_currency(value: str) -> float:
    """Convert any currency string to float. Handles $, (), commas, M/K suffixes."""
    if not value or not isinstance(value, str):
        return 0.0
    value = value.strip()
    if not value:
        return 0.0

    is_negative = value.startswith("(") and value.endswith(")")
    if is_negative:
        value = value[1:-1]
    if value.startswith("-"):
        is_negative = True
        value = value[1:]

    value = value.replace("$", "").replace(",", "").strip()

    if value.upper().endswith("M"):
        try:
            return float(value[:-1]) * 1_000_000 * (-1 if is_negative else 1)
        except ValueError:
            return 0.0
    if value.upper().endswith("K"):
        try:
            return float(value[:-1]) * 1_000 * (-1 if is_negative else 1)
        except ValueError:
            return 0.0
    if value.upper().endswith("B"):
        try:
            return float(value[:-1]) * 1_000_000_000 * (-1 if is_negative else 1)
        except ValueError:
            return 0.0

    try:
        result = float(value)
        return result * (-1 if is_negative else 1)
    except ValueError:
        return 0.0


def find_value_after_label(text: str, label_pattern: str, is_currency: bool = True) -> Any:
    """Find a value on the same line or next line after a label."""
    match = re.search(
        label_pattern + r"[:\s]*[\$]?([\d,\.]+(?:\.\d{2})?)",
        text, re.IGNORECASE
    )
    if match:
        val = match.group(1) if match.lastindex else match.group(0)
        return clean_currency(val) if is_currency else val.strip()
    return 0.0 if is_currency else ""


def find_all_currency_values(text: str, label_pattern: str) -> List[float]:
    """Find all currency values near a label."""
    results = []
    for match in re.finditer(
        label_pattern + r"[:\s]*[\$]?([\d,]+(?:\.\d{2})?)",
        text, re.IGNORECASE
    ):
        val = clean_currency(match.group(1) if match.lastindex else "0")
        if val != 0:
            results.append(val)
    return results


def extract_date_from_text(text: str) -> Optional[str]:
    """Extract the first recognizable date from text."""
    patterns = [
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "mdy"),
        (r"(\d{1,2})-(\d{1,2})-(\d{4})", "mdy"),
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"),
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", "named"),
        (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[.\s]+(\d{1,2}),?\s+(\d{4})", "named_short"),
    ]

    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    for pattern, fmt in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                groups = match.groups()
                if fmt == "mdy":
                    return f"{int(groups[0]):02d}/{int(groups[1]):02d}/{groups[2]}"
                elif fmt == "ymd":
                    return f"{int(groups[1]):02d}/{int(groups[2]):02d}/{groups[0]}"
                elif fmt in ("named", "named_short"):
                    m = month_map.get(groups[0].lower(), 1)
                    return f"{m:02d}/{int(groups[1]):02d}/{groups[2]}"
            except (ValueError, IndexError):
                continue
    return None


def extract_period_dates(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract statement period start and end dates."""
    # "for the period MM/DD/YYYY through MM/DD/YYYY"
    period_match = re.search(
        r"(?:for the (?:period|year)|period|statement period)[:\s]*"
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|through|thru|-|–)\s*"
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        text, re.IGNORECASE
    )
    if period_match:
        return period_match.group(1), period_match.group(2)

    # "as of MM/DD/YYYY"
    as_of_match = re.search(
        r"(?:as of|ending|ended|through)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        text, re.IGNORECASE
    )
    if as_of_match:
        return None, as_of_match.group(1)

    return None, None


# ═══════════════════════════════════════════════════════════════════
# Document Classification
# ═══════════════════════════════════════════════════════════════════

# Keywords with weights for each document type
DOCUMENT_SIGNATURES = {
    # ── Individual Document Types ──
    "brokerage_statement": {
        "keywords": [
            ("account statement", 3), ("brokerage", 3), ("investment account", 3),
            ("portfolio summary", 3), ("holdings", 2), ("market value", 2),
            ("shares", 2), ("ticker", 2), ("cusip", 2), ("unrealized", 2),
            ("realized gain", 2), ("dividend", 1), ("interest income", 1),
            ("schwab", 3), ("fidelity", 3), ("vanguard", 3), ("td ameritrade", 3),
            ("merrill", 3), ("morgan stanley", 3), ("interactive brokers", 3),
            ("edward jones", 3), ("raymond james", 3), ("etrade", 3),
            ("asset allocation", 2), ("total account value", 2),
            ("estimated annual income", 2), ("cost basis", 2),
        ],
        "category": "individual",
        "profile_section": "assets",
    },
    "bank_statement": {
        "keywords": [
            ("bank statement", 4), ("checking account", 3), ("savings account", 3),
            ("account summary", 2), ("beginning balance", 3), ("ending balance", 3),
            ("deposits and credits", 2), ("withdrawals and debits", 2),
            ("daily balance", 2), ("overdraft", 1), ("direct deposit", 1),
            ("bank of america", 3), ("chase", 3), ("wells fargo", 3),
            ("citibank", 3), ("pnc", 3), ("us bank", 3), ("capital one", 3),
            ("available balance", 2), ("current balance", 2),
            ("certificate of deposit", 2), ("money market", 2),
        ],
        "category": "individual",
        "profile_section": "assets",
    },
    "tax_return_individual": {
        "keywords": [
            ("form 1040", 5), ("u.s. individual income tax return", 5),
            ("adjusted gross income", 3), ("taxable income", 3),
            ("filing status", 3), ("standard deduction", 2),
            ("itemized deductions", 2), ("schedule a", 2), ("schedule b", 2),
            ("schedule c", 2), ("schedule d", 2), ("schedule e", 2),
            ("tax refund", 2), ("amount you owe", 2), ("estimated tax", 2),
            ("total income", 2), ("wages, salaries", 2),
        ],
        "category": "individual",
        "profile_section": "tax",
    },
    "w2": {
        "keywords": [
            ("form w-2", 5), ("wage and tax statement", 5),
            ("employer identification", 3), ("federal income tax withheld", 3),
            ("social security wages", 3), ("medicare wages", 2),
            ("employee's social security", 2), ("employer's name", 2),
            ("wages, tips, other compensation", 3),
        ],
        "category": "individual",
        "profile_section": "income",
    },
    "1099": {
        "keywords": [
            ("form 1099", 5), ("1099-int", 4), ("1099-div", 4),
            ("1099-b", 4), ("1099-r", 4), ("1099-misc", 4), ("1099-nec", 4),
            ("1099-sa", 3), ("1099-q", 3),
            ("interest income", 2), ("dividend income", 2),
            ("proceeds from broker", 2), ("distributions from pensions", 2),
            ("nonemployee compensation", 2), ("ordinary dividends", 2),
            ("qualified dividends", 2), ("capital gain distributions", 2),
            ("total ordinary dividends", 2), ("federal income tax withheld", 2),
        ],
        "category": "individual",
        "profile_section": "income",
    },
    "k1": {
        "keywords": [
            ("schedule k-1", 5), ("form 1065", 3), ("form 1120s", 3),
            ("partner's share", 4), ("shareholder's share", 4),
            ("ordinary business income", 3), ("net rental real estate", 2),
            ("guaranteed payments", 2), ("partner's share of income", 2),
            ("tax-exempt income", 2), ("distributions", 2),
        ],
        "category": "individual",
        "profile_section": "income",
    },
    "insurance_life": {
        "keywords": [
            ("life insurance", 5), ("death benefit", 4), ("cash value", 3),
            ("face amount", 3), ("policy number", 2), ("premium", 2),
            ("beneficiary", 2), ("insured", 2), ("policy owner", 2),
            ("term life", 3), ("whole life", 3), ("universal life", 3),
            ("variable life", 3), ("surrender value", 3),
            ("annual premium", 2), ("coverage amount", 2),
        ],
        "category": "individual",
        "profile_section": "insurance",
    },
    "insurance_property": {
        "keywords": [
            ("homeowners insurance", 4), ("property insurance", 4),
            ("dwelling coverage", 3), ("personal property", 2),
            ("liability coverage", 2), ("declarations page", 3),
            ("auto insurance", 4), ("vehicle insurance", 3),
            ("umbrella policy", 4), ("excess liability", 3),
            ("policy period", 2), ("deductible", 2), ("premium", 2),
            ("coverage limits", 2), ("collision", 2), ("comprehensive", 2),
        ],
        "category": "individual",
        "profile_section": "insurance",
    },
    "insurance_health_disability": {
        "keywords": [
            ("health insurance", 4), ("medical insurance", 4),
            ("disability insurance", 5), ("long-term disability", 4),
            ("short-term disability", 4), ("long-term care", 4),
            ("monthly benefit", 3), ("elimination period", 3),
            ("benefit period", 2), ("own occupation", 3),
            ("group coverage", 2), ("cobra", 2), ("hsa", 2),
        ],
        "category": "individual",
        "profile_section": "insurance",
    },
    "estate_will_trust": {
        "keywords": [
            ("last will and testament", 5), ("revocable trust", 5),
            ("irrevocable trust", 5), ("living trust", 4),
            ("trust agreement", 4), ("trustee", 3), ("beneficiary", 2),
            ("executor", 3), ("personal representative", 3),
            ("power of attorney", 4), ("healthcare directive", 4),
            ("advance directive", 4), ("durable power", 3),
            ("guardianship", 2), ("estate plan", 3),
            ("testamentary", 2), ("probate", 2), ("bequest", 2),
        ],
        "category": "individual",
        "profile_section": "estate",
    },
    "mortgage_real_estate": {
        "keywords": [
            ("mortgage", 4), ("deed of trust", 4), ("promissory note", 3),
            ("hud-1", 4), ("closing disclosure", 4), ("settlement statement", 3),
            ("property tax", 3), ("property appraisal", 4),
            ("real estate", 2), ("loan amount", 2), ("interest rate", 2),
            ("monthly payment", 2), ("escrow", 2), ("principal balance", 2),
            ("amortization", 2), ("lien", 2), ("title insurance", 2),
            ("assessed value", 2), ("fair market value", 2),
        ],
        "category": "individual",
        "profile_section": "liabilities",
    },
    "retirement_401k_ira": {
        "keywords": [
            ("401(k)", 5), ("401k", 5), ("403(b)", 4), ("457", 3),
            ("ira", 4), ("roth ira", 5), ("traditional ira", 5),
            ("sep ira", 4), ("simple ira", 4),
            ("retirement account", 4), ("retirement plan", 3),
            ("vesting", 2), ("employer match", 3), ("contribution", 2),
            ("required minimum distribution", 3), ("rmd", 3),
            ("rollover", 2), ("beneficiary", 1),
            ("target date fund", 2), ("plan summary", 2),
        ],
        "category": "individual",
        "profile_section": "retirement",
    },
    "social_security": {
        "keywords": [
            ("social security", 5), ("social security statement", 5),
            ("estimated benefits", 3), ("retirement benefits", 3),
            ("disability benefits", 2), ("survivor benefits", 2),
            ("full retirement age", 4), ("earnings record", 3),
            ("ssa.gov", 3), ("social security administration", 4),
            ("your estimated benefits", 3),
        ],
        "category": "individual",
        "profile_section": "retirement",
    },
    "pension": {
        "keywords": [
            ("pension", 5), ("pension plan", 5), ("pension benefit", 4),
            ("defined benefit", 4), ("annuity", 3),
            ("monthly pension", 3), ("pension statement", 4),
            ("vested benefit", 3), ("accrued benefit", 3),
            ("joint and survivor", 3), ("single life", 2),
            ("pension calculation", 2), ("years of service", 2),
        ],
        "category": "individual",
        "profile_section": "retirement",
    },
    "personal_financial_statement": {
        "keywords": [
            ("personal financial statement", 5), ("net worth statement", 5),
            ("statement of financial condition", 4),
            ("total assets", 3), ("total liabilities", 3),
            ("net worth", 3), ("financial summary", 3),
            ("asset summary", 2), ("liability summary", 2),
            ("personal balance sheet", 4), ("household net worth", 4),
        ],
        "category": "individual",
        "profile_section": "assets",
    },
    "pay_stub": {
        "keywords": [
            ("pay stub", 5), ("paycheck", 4), ("earnings statement", 4),
            ("gross pay", 3), ("net pay", 3), ("ytd earnings", 3),
            ("federal tax", 2), ("state tax", 2), ("fica", 2),
            ("deductions", 2), ("pay period", 3), ("pay date", 2),
            ("regular hours", 2), ("overtime", 1),
        ],
        "category": "individual",
        "profile_section": "income",
    },

    # ── Business Document Types ──
    "business_income_statement": {
        "keywords": [
            ("profit and loss", 4), ("income statement", 4), ("p&l", 3),
            ("revenue", 2), ("cost of goods sold", 3), ("gross profit", 3),
            ("operating expenses", 2), ("net income", 2), ("ebitda", 3),
            ("operating income", 2), ("total expenses", 2),
        ],
        "category": "business",
        "profile_section": "financials",
    },
    "business_balance_sheet": {
        "keywords": [
            ("balance sheet", 4), ("statement of financial position", 4),
            ("total assets", 3), ("total liabilities", 3),
            ("stockholders equity", 3), ("shareholders equity", 3),
            ("current assets", 2), ("current liabilities", 2),
            ("retained earnings", 2), ("accounts receivable", 2),
            ("accounts payable", 2), ("working capital", 2),
        ],
        "category": "business",
        "profile_section": "financials",
    },
    "business_cash_flow": {
        "keywords": [
            ("cash flow statement", 4), ("statement of cash flows", 4),
            ("operating activities", 3), ("investing activities", 3),
            ("financing activities", 3), ("net change in cash", 3),
            ("capital expenditures", 2), ("depreciation", 1),
            ("free cash flow", 3),
        ],
        "category": "business",
        "profile_section": "financials",
    },
    "business_tax_return": {
        "keywords": [
            ("form 1120", 5), ("form 1120s", 5), ("form 1065", 5),
            ("corporate tax return", 4), ("partnership return", 4),
            ("business tax return", 4), ("gross receipts", 3),
            ("total deductions", 2), ("taxable income", 2),
            ("officer compensation", 2), ("cost of goods sold", 2),
        ],
        "category": "business",
        "profile_section": "financials",
    },
    "business_bank_statement": {
        "keywords": [
            ("business checking", 4), ("commercial account", 3),
            ("business account", 3), ("operating account", 3),
            ("beginning balance", 2), ("ending balance", 2),
            ("deposits", 1), ("withdrawals", 1),
        ],
        "category": "business",
        "profile_section": "accounts",
    },
    "business_valuation": {
        "keywords": [
            ("business valuation", 5), ("enterprise value", 4),
            ("fair market value", 3), ("valuation report", 4),
            ("ebitda multiple", 3), ("discounted cash flow", 3),
            ("comparable transactions", 2), ("goodwill", 2),
        ],
        "category": "business",
        "profile_section": "valuation",
    },
}


def classify_document(text: str) -> Dict[str, Any]:
    """
    Score the text against all document signatures and return the best match.
    Returns: {"doc_type": str, "category": str, "profile_section": str, "confidence": float, "scores": dict}
    """
    text_lower = text.lower()
    scores = {}

    for doc_type, config in DOCUMENT_SIGNATURES.items():
        score = 0
        matched_keywords = []
        for keyword, weight in config["keywords"]:
            if keyword.lower() in text_lower:
                score += weight
                matched_keywords.append(keyword)
        scores[doc_type] = {
            "score": score,
            "matched_keywords": matched_keywords,
            "category": config["category"],
            "profile_section": config["profile_section"],
        }

    # Find the best match
    best_type = max(scores, key=lambda k: scores[k]["score"])
    best = scores[best_type]

    # Calculate confidence (0-100)
    max_possible = sum(w for _, w in DOCUMENT_SIGNATURES[best_type]["keywords"])
    confidence = min(100, round((best["score"] / max(max_possible, 1)) * 100 * 2))

    return {
        "doc_type": best_type,
        "category": best["category"],
        "profile_section": best["profile_section"],
        "confidence": confidence,
        "matched_keywords": best["matched_keywords"],
        "score": best["score"],
        "all_scores": {k: v["score"] for k, v in scores.items() if v["score"] > 0},
    }


# ═══════════════════════════════════════════════════════════════════
# Specialized Extractors — Individual Documents
# ═══════════════════════════════════════════════════════════════════

class BrokerageExtractor:
    """Extract data from brokerage/investment account statements."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "account_name": "",
            "account_number": "",
            "institution": "",
            "account_type": "investment",
            "total_value": 0.0,
            "cash_balance": 0.0,
            "holdings": [],
            "period_start": None,
            "period_end": None,
            "income_ytd": 0.0,
            "realized_gains": 0.0,
            "unrealized_gains": 0.0,
        }

        # Institution detection
        institutions = {
            "schwab": "Charles Schwab", "fidelity": "Fidelity",
            "vanguard": "Vanguard", "td ameritrade": "TD Ameritrade",
            "merrill": "Merrill Lynch", "morgan stanley": "Morgan Stanley",
            "interactive brokers": "Interactive Brokers", "ibkr": "Interactive Brokers",
            "edward jones": "Edward Jones", "raymond james": "Raymond James",
            "etrade": "E*TRADE", "e\\*trade": "E*TRADE",
            "robinhood": "Robinhood", "wealthfront": "Wealthfront",
            "betterment": "Betterment",
        }
        text_lower = text.lower()
        for key, name in institutions.items():
            if key in text_lower:
                result["institution"] = name
                break

        # Account number
        acct_match = re.search(r"(?:account|acct)[#:\s]*([A-Z0-9\-\*]+\d{4})", text, re.IGNORECASE)
        if acct_match:
            result["account_number"] = acct_match.group(1)

        # Total value
        for pattern in [
            r"(?:total (?:account|market|portfolio) value)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:total value|ending value|total assets)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:account value)[:\s]*\$?([\d,]+\.?\d*)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_value"] = clean_currency(match.group(1))
                break

        # Cash / money market balance
        cash_match = re.search(
            r"(?:cash|money market|cash & equivalents)[:\s]*\$?([\d,]+\.?\d*)",
            text, re.IGNORECASE
        )
        if cash_match:
            result["cash_balance"] = clean_currency(cash_match.group(1))

        # Income & gains
        result["income_ytd"] = find_value_after_label(text, r"(?:total income|income ytd|dividend income)")
        result["realized_gains"] = find_value_after_label(text, r"(?:realized gain|net realized)")
        result["unrealized_gains"] = find_value_after_label(text, r"(?:unrealized gain|net unrealized)")

        # Period dates
        result["period_start"], result["period_end"] = extract_period_dates(text)

        # Holdings from tables
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = " ".join(str(c) for c in table[0] if c).lower()
            if any(k in header for k in ["symbol", "ticker", "security", "description", "shares", "quantity"]):
                for row in table[1:]:
                    if len(row) >= 3:
                        holding = {
                            "name": str(row[0] or "").strip(),
                            "shares": 0.0,
                            "value": 0.0,
                            "cost_basis": 0.0,
                        }
                        for cell in row[1:]:
                            if cell:
                                val = clean_currency(str(cell))
                                if val > 0:
                                    if holding["shares"] == 0 and val < 1_000_000:
                                        holding["shares"] = val
                                    elif holding["value"] == 0:
                                        holding["value"] = val
                                    elif holding["cost_basis"] == 0:
                                        holding["cost_basis"] = val
                        if holding["name"] and (holding["value"] > 0 or holding["shares"] > 0):
                            result["holdings"].append(holding)

        return result


class BankStatementExtractor:
    """Extract data from bank statements."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "account_name": "",
            "account_number": "",
            "institution": "",
            "account_type": "checking",
            "beginning_balance": 0.0,
            "ending_balance": 0.0,
            "total_deposits": 0.0,
            "total_withdrawals": 0.0,
            "period_start": None,
            "period_end": None,
            "interest_earned": 0.0,
        }

        text_lower = text.lower()

        # Account type
        if "savings" in text_lower:
            result["account_type"] = "savings"
        elif "money market" in text_lower:
            result["account_type"] = "money_market"
        elif "certificate" in text_lower or "cd " in text_lower:
            result["account_type"] = "cd"

        # Institution
        banks = {
            "bank of america": "Bank of America", "chase": "JPMorgan Chase",
            "wells fargo": "Wells Fargo", "citibank": "Citibank",
            "pnc": "PNC Bank", "us bank": "US Bank",
            "capital one": "Capital One", "td bank": "TD Bank",
            "regions": "Regions Bank", "truist": "Truist",
            "suntrust": "SunTrust", "bb&t": "BB&T",
        }
        for key, name in banks.items():
            if key in text_lower:
                result["institution"] = name
                break

        # Account number
        acct_match = re.search(r"(?:account|acct)[#:\s]*([*X\-\d]{4,})", text, re.IGNORECASE)
        if acct_match:
            result["account_number"] = acct_match.group(1)

        # Balances
        result["beginning_balance"] = find_value_after_label(text, r"(?:beginning|opening|previous) balance")
        result["ending_balance"] = find_value_after_label(text, r"(?:ending|closing|current|available) balance")
        result["total_deposits"] = find_value_after_label(text, r"(?:total deposits|deposits and credits)")
        result["total_withdrawals"] = find_value_after_label(text, r"(?:total withdrawals|withdrawals and debits|checks and debits)")
        result["interest_earned"] = find_value_after_label(text, r"(?:interest earned|interest paid|interest credited)")

        # Period
        result["period_start"], result["period_end"] = extract_period_dates(text)

        return result


class TaxReturnExtractor:
    """Extract data from individual tax returns (1040)."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "form_type": "1040",
            "tax_year": "",
            "filing_status": "",
            "wages": 0.0,
            "interest_income": 0.0,
            "dividend_income": 0.0,
            "capital_gains": 0.0,
            "business_income": 0.0,
            "rental_income": 0.0,
            "social_security_income": 0.0,
            "other_income": 0.0,
            "total_income": 0.0,
            "adjusted_gross_income": 0.0,
            "taxable_income": 0.0,
            "total_tax": 0.0,
            "federal_withheld": 0.0,
            "refund_or_owed": 0.0,
            "effective_tax_rate": 0.0,
            "deductions": 0.0,
            "deduction_type": "",
        }

        # Tax year
        year_match = re.search(r"20\d{2}", text[:500])
        if year_match:
            result["tax_year"] = year_match.group(0)

        # Filing status
        statuses = ["single", "married filing jointly", "married filing separately",
                     "head of household", "qualifying widow"]
        text_lower = text.lower()
        for status in statuses:
            if status in text_lower:
                result["filing_status"] = status.title()
                break

        # Income
        result["wages"] = find_value_after_label(text, r"(?:wages|salaries|tips|compensation)")
        result["interest_income"] = find_value_after_label(text, r"(?:taxable interest|interest income)")
        result["dividend_income"] = find_value_after_label(text, r"(?:ordinary dividends|qualified dividends|dividend income)")
        result["capital_gains"] = find_value_after_label(text, r"(?:capital gain|net capital)")
        result["business_income"] = find_value_after_label(text, r"(?:business income|schedule c|self-employment)")
        result["rental_income"] = find_value_after_label(text, r"(?:rental|royalty)")
        result["social_security_income"] = find_value_after_label(text, r"(?:social security benefits|taxable social security)")
        result["total_income"] = find_value_after_label(text, r"(?:total income)")
        result["adjusted_gross_income"] = find_value_after_label(text, r"(?:adjusted gross income|agi)")
        result["taxable_income"] = find_value_after_label(text, r"(?:taxable income)")
        result["total_tax"] = find_value_after_label(text, r"(?:total tax)")
        result["federal_withheld"] = find_value_after_label(text, r"(?:federal (?:income )?tax withheld)")
        result["deductions"] = find_value_after_label(text, r"(?:total deductions|standard deduction|itemized deductions)")

        if "standard deduction" in text_lower:
            result["deduction_type"] = "standard"
        elif "itemized" in text_lower:
            result["deduction_type"] = "itemized"

        # Calculate effective rate
        if result["adjusted_gross_income"] > 0 and result["total_tax"] > 0:
            result["effective_tax_rate"] = round(result["total_tax"] / result["adjusted_gross_income"] * 100, 2)

        return result


class W2Extractor:
    """Extract data from W-2 forms."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "employer_name": "",
            "employer_ein": "",
            "employee_name": "",
            "employee_ssn": "",
            "wages": 0.0,
            "federal_tax_withheld": 0.0,
            "social_security_wages": 0.0,
            "social_security_tax": 0.0,
            "medicare_wages": 0.0,
            "medicare_tax": 0.0,
            "state": "",
            "state_wages": 0.0,
            "state_tax_withheld": 0.0,
            "retirement_plan": False,
            "year": "",
        }

        # Employer name
        emp_match = re.search(r"(?:employer'?s? name)[:\s]*([^\n]+)", text, re.IGNORECASE)
        if emp_match:
            result["employer_name"] = emp_match.group(1).strip()

        # EIN
        ein_match = re.search(r"(\d{2}-\d{7})", text)
        if ein_match:
            result["employer_ein"] = ein_match.group(1)

        # Wages
        result["wages"] = find_value_after_label(text, r"(?:wages|tips|other compensation)")
        result["federal_tax_withheld"] = find_value_after_label(text, r"(?:federal income tax withheld)")
        result["social_security_wages"] = find_value_after_label(text, r"(?:social security wages)")
        result["social_security_tax"] = find_value_after_label(text, r"(?:social security tax withheld)")
        result["medicare_wages"] = find_value_after_label(text, r"(?:medicare wages)")
        result["medicare_tax"] = find_value_after_label(text, r"(?:medicare tax withheld)")
        result["state_wages"] = find_value_after_label(text, r"(?:state wages)")
        result["state_tax_withheld"] = find_value_after_label(text, r"(?:state income tax)")

        # Year
        year_match = re.search(r"20\d{2}", text[:200])
        if year_match:
            result["year"] = year_match.group(0)

        # Retirement plan indicator
        if re.search(r"retirement plan.*(?:checked|yes|x)", text, re.IGNORECASE):
            result["retirement_plan"] = True

        return result


class Form1099Extractor:
    """Extract data from 1099 forms (INT, DIV, B, R, MISC, NEC)."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        text_lower = text.lower()
        result = {
            "form_subtype": "",
            "payer_name": "",
            "payer_tin": "",
            "recipient_name": "",
            "year": "",
            "amounts": {},
        }

        # Detect subtype
        subtypes = ["1099-int", "1099-div", "1099-b", "1099-r", "1099-misc", "1099-nec", "1099-sa", "1099-q"]
        for st in subtypes:
            if st in text_lower:
                result["form_subtype"] = st.upper()
                break

        # Year
        year_match = re.search(r"20\d{2}", text[:300])
        if year_match:
            result["year"] = year_match.group(0)

        # Payer
        payer_match = re.search(r"(?:payer'?s? name)[:\s]*([^\n]+)", text, re.IGNORECASE)
        if payer_match:
            result["payer_name"] = payer_match.group(1).strip()

        # Extract amounts based on form type
        if "1099-int" in text_lower:
            result["amounts"]["interest_income"] = find_value_after_label(text, r"(?:interest income)")
            result["amounts"]["early_withdrawal_penalty"] = find_value_after_label(text, r"(?:early withdrawal penalty)")
            result["amounts"]["federal_tax_withheld"] = find_value_after_label(text, r"(?:federal income tax withheld)")
        elif "1099-div" in text_lower:
            result["amounts"]["ordinary_dividends"] = find_value_after_label(text, r"(?:total ordinary dividends|ordinary dividends)")
            result["amounts"]["qualified_dividends"] = find_value_after_label(text, r"(?:qualified dividends)")
            result["amounts"]["capital_gain_distributions"] = find_value_after_label(text, r"(?:capital gain dist)")
            result["amounts"]["federal_tax_withheld"] = find_value_after_label(text, r"(?:federal income tax withheld)")
        elif "1099-r" in text_lower:
            result["amounts"]["gross_distribution"] = find_value_after_label(text, r"(?:gross distribution)")
            result["amounts"]["taxable_amount"] = find_value_after_label(text, r"(?:taxable amount)")
            result["amounts"]["federal_tax_withheld"] = find_value_after_label(text, r"(?:federal income tax withheld)")
        elif "1099-b" in text_lower:
            result["amounts"]["total_proceeds"] = find_value_after_label(text, r"(?:total proceeds|proceeds)")
            result["amounts"]["total_cost_basis"] = find_value_after_label(text, r"(?:cost|basis)")
            result["amounts"]["total_gain_loss"] = find_value_after_label(text, r"(?:gain|loss|wash)")
        elif "1099-misc" in text_lower or "1099-nec" in text_lower:
            result["amounts"]["nonemployee_compensation"] = find_value_after_label(text, r"(?:nonemployee compensation)")
            result["amounts"]["rents"] = find_value_after_label(text, r"(?:^rents)")
            result["amounts"]["royalties"] = find_value_after_label(text, r"(?:royalties)")
            result["amounts"]["other_income"] = find_value_after_label(text, r"(?:other income)")

        return result


class InsuranceExtractor:
    """Extract data from insurance policies (life, property, health, disability)."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        text_lower = text.lower()
        result = {
            "policy_type": "",
            "policy_number": "",
            "carrier": "",
            "insured_name": "",
            "coverage_amount": 0.0,
            "premium": 0.0,
            "premium_frequency": "",
            "effective_date": None,
            "expiration_date": None,
            "beneficiaries": [],
            "deductible": 0.0,
            "cash_value": 0.0,
            "details": {},
        }

        # Policy type classification
        if "life insurance" in text_lower:
            if "term" in text_lower:
                result["policy_type"] = "term_life"
            elif "whole" in text_lower:
                result["policy_type"] = "whole_life"
            elif "universal" in text_lower:
                result["policy_type"] = "universal_life"
            elif "variable" in text_lower:
                result["policy_type"] = "variable_life"
            else:
                result["policy_type"] = "life"
        elif "disability" in text_lower:
            if "long-term" in text_lower or "long term" in text_lower:
                result["policy_type"] = "long_term_disability"
            else:
                result["policy_type"] = "short_term_disability"
        elif "long-term care" in text_lower or "long term care" in text_lower:
            result["policy_type"] = "long_term_care"
        elif "homeowner" in text_lower or "dwelling" in text_lower:
            result["policy_type"] = "homeowners"
        elif "auto" in text_lower or "vehicle" in text_lower:
            result["policy_type"] = "auto"
        elif "umbrella" in text_lower or "excess liability" in text_lower:
            result["policy_type"] = "umbrella"
        elif "health" in text_lower or "medical" in text_lower:
            result["policy_type"] = "health"

        # Policy number
        pol_match = re.search(r"(?:policy|certificate)\s*(?:#|number|no)[:\s]*([A-Z0-9\-]+)", text, re.IGNORECASE)
        if pol_match:
            result["policy_number"] = pol_match.group(1)

        # Coverage / face amount / death benefit
        for pattern in [
            r"(?:death benefit|face amount|coverage amount|sum insured)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:dwelling coverage|coverage a)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:liability limit|coverage limit)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:monthly benefit)[:\s]*\$?([\d,]+\.?\d*)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["coverage_amount"] = clean_currency(match.group(1))
                break

        # Premium
        result["premium"] = find_value_after_label(text, r"(?:premium|annual premium|monthly premium)")
        if "monthly" in text_lower and result["premium"]:
            result["premium_frequency"] = "monthly"
        elif "annual" in text_lower:
            result["premium_frequency"] = "annual"
        elif "quarterly" in text_lower:
            result["premium_frequency"] = "quarterly"

        # Cash value (life insurance)
        result["cash_value"] = find_value_after_label(text, r"(?:cash value|surrender value|account value)")

        # Deductible
        result["deductible"] = find_value_after_label(text, r"(?:deductible)")

        return result


class EstateExtractor:
    """Extract data from estate planning documents."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        text_lower = text.lower()
        result = {
            "document_type": "",
            "grantor_name": "",
            "trust_name": "",
            "date_executed": None,
            "has_will": False,
            "has_trust": False,
            "trust_type": "",
            "has_poa_financial": False,
            "has_poa_healthcare": False,
            "has_healthcare_directive": False,
            "beneficiaries": [],
            "executor_trustee": "",
            "successor_trustee": "",
            "notes": "",
        }

        if "will" in text_lower and "testament" in text_lower:
            result["document_type"] = "will"
            result["has_will"] = True
        elif "trust" in text_lower:
            result["document_type"] = "trust"
            result["has_trust"] = True
            if "revocable" in text_lower:
                result["trust_type"] = "revocable"
            elif "irrevocable" in text_lower:
                result["trust_type"] = "irrevocable"
        elif "power of attorney" in text_lower:
            if "healthcare" in text_lower or "medical" in text_lower:
                result["document_type"] = "healthcare_poa"
                result["has_poa_healthcare"] = True
            else:
                result["document_type"] = "financial_poa"
                result["has_poa_financial"] = True
        elif "healthcare directive" in text_lower or "advance directive" in text_lower:
            result["document_type"] = "healthcare_directive"
            result["has_healthcare_directive"] = True

        # Grantor/testator name
        grantor_match = re.search(
            r"(?:grantor|trustor|testator|principal)[:\s]*([A-Z][a-zA-Z\s]+)",
            text, re.IGNORECASE
        )
        if grantor_match:
            result["grantor_name"] = grantor_match.group(1).strip()

        # Trust name
        trust_match = re.search(r"(?:the\s+)([A-Z][a-zA-Z\s]+(?:Trust|Family Trust|Living Trust))", text)
        if trust_match:
            result["trust_name"] = trust_match.group(1).strip()

        # Executor / Trustee
        for pattern in [
            r"(?:executor|personal representative)[:\s]*([A-Z][a-zA-Z\s,]+)",
            r"(?:trustee)[:\s]*([A-Z][a-zA-Z\s,]+)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["executor_trustee"] = match.group(1).strip()[:100]
                break

        # Date
        result["date_executed"] = extract_date_from_text(text)

        return result


class MortgageRealEstateExtractor:
    """Extract data from mortgage and real estate documents."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "document_type": "",
            "property_address": "",
            "property_value": 0.0,
            "loan_amount": 0.0,
            "original_loan_amount": 0.0,
            "interest_rate": 0.0,
            "monthly_payment": 0.0,
            "loan_type": "",
            "lender": "",
            "maturity_date": None,
            "escrow_amount": 0.0,
            "property_tax_annual": 0.0,
            "insurance_annual": 0.0,
            "principal_balance": 0.0,
        }

        text_lower = text.lower()

        if "hud-1" in text_lower or "closing disclosure" in text_lower or "settlement" in text_lower:
            result["document_type"] = "closing_disclosure"
        elif "appraisal" in text_lower:
            result["document_type"] = "appraisal"
        elif "property tax" in text_lower or "tax bill" in text_lower:
            result["document_type"] = "property_tax_bill"
        elif "mortgage statement" in text_lower:
            result["document_type"] = "mortgage_statement"
        else:
            result["document_type"] = "mortgage_note"

        # Property value / appraised value
        for pattern in [
            r"(?:appraised value|market value|assessed value|property value)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:purchase price|sale price)[:\s]*\$?([\d,]+\.?\d*)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["property_value"] = clean_currency(match.group(1))
                break

        # Loan amount
        result["loan_amount"] = find_value_after_label(text, r"(?:loan amount|principal balance|unpaid principal)")
        result["original_loan_amount"] = find_value_after_label(text, r"(?:original (?:loan|principal) amount)")
        result["monthly_payment"] = find_value_after_label(text, r"(?:monthly payment|payment amount)")
        result["escrow_amount"] = find_value_after_label(text, r"(?:escrow|escrow payment)")
        result["property_tax_annual"] = find_value_after_label(text, r"(?:property tax|real estate tax|annual tax)")
        result["principal_balance"] = find_value_after_label(text, r"(?:principal balance|outstanding balance)")

        # Interest rate
        rate_match = re.search(r"(?:interest rate|annual percentage|apr)[:\s]*(\d+\.?\d*)[\s]*%?", text, re.IGNORECASE)
        if rate_match:
            result["interest_rate"] = float(rate_match.group(1))

        # Loan type
        if "fixed" in text_lower:
            result["loan_type"] = "fixed"
        elif "adjustable" in text_lower or "arm" in text_lower:
            result["loan_type"] = "adjustable"
        elif "fha" in text_lower:
            result["loan_type"] = "FHA"
        elif "va " in text_lower:
            result["loan_type"] = "VA"

        # Lender
        lender_match = re.search(r"(?:lender|servicer|mortgagee)[:\s]*([^\n]+)", text, re.IGNORECASE)
        if lender_match:
            result["lender"] = lender_match.group(1).strip()[:100]

        # Address
        addr_match = re.search(
            r"(?:property address|subject property|property location)[:\s]*([^\n]+(?:\n[^\n]+)?)",
            text, re.IGNORECASE
        )
        if addr_match:
            result["property_address"] = addr_match.group(1).strip()[:200]

        return result


class RetirementExtractor:
    """Extract data from retirement account statements (401k, IRA, pension, SS)."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        text_lower = text.lower()
        result = {
            "account_type": "",
            "plan_name": "",
            "account_number": "",
            "institution": "",
            "total_balance": 0.0,
            "vested_balance": 0.0,
            "employee_contributions_ytd": 0.0,
            "employer_contributions_ytd": 0.0,
            "loan_balance": 0.0,
            "rate_of_return": 0.0,
            "holdings": [],
            "beneficiaries": [],
            "rmd_amount": 0.0,
            "period_end": None,
            # Social Security specific
            "ss_monthly_at_62": 0.0,
            "ss_monthly_at_fra": 0.0,
            "ss_monthly_at_70": 0.0,
            "ss_full_retirement_age": "",
            # Pension specific
            "pension_monthly_benefit": 0.0,
            "pension_years_of_service": 0.0,
        }

        # Detect account type
        if "401(k)" in text_lower or "401k" in text_lower:
            result["account_type"] = "401k"
        elif "403(b)" in text_lower:
            result["account_type"] = "403b"
        elif "457" in text_lower:
            result["account_type"] = "457"
        elif "roth ira" in text_lower:
            result["account_type"] = "roth_ira"
        elif "sep ira" in text_lower:
            result["account_type"] = "sep_ira"
        elif "simple ira" in text_lower:
            result["account_type"] = "simple_ira"
        elif "traditional ira" in text_lower or "ira" in text_lower:
            result["account_type"] = "traditional_ira"
        elif "social security" in text_lower:
            result["account_type"] = "social_security"
        elif "pension" in text_lower:
            result["account_type"] = "pension"

        # Balances
        result["total_balance"] = find_value_after_label(text, r"(?:total (?:account )?(?:balance|value)|ending (?:balance|value)|account value)")
        result["vested_balance"] = find_value_after_label(text, r"(?:vested balance|vested value)")
        result["employee_contributions_ytd"] = find_value_after_label(text, r"(?:employee contribution|your contribution)")
        result["employer_contributions_ytd"] = find_value_after_label(text, r"(?:employer (?:contribution|match))")
        result["loan_balance"] = find_value_after_label(text, r"(?:loan balance|outstanding loan)")
        result["rmd_amount"] = find_value_after_label(text, r"(?:required minimum distribution|rmd)")

        # Rate of return
        ror_match = re.search(r"(?:rate of return|return)[:\s]*(-?[\d.]+)\s*%", text, re.IGNORECASE)
        if ror_match:
            result["rate_of_return"] = float(ror_match.group(1))

        # Social Security
        if result["account_type"] == "social_security":
            result["ss_monthly_at_62"] = find_value_after_label(text, r"(?:age 62|at 62|early retirement)")
            result["ss_monthly_at_fra"] = find_value_after_label(text, r"(?:full retirement|at full|at 66|at 67)")
            result["ss_monthly_at_70"] = find_value_after_label(text, r"(?:age 70|at 70|delayed)")
            fra_match = re.search(r"full retirement age[:\s]*(\d+(?:\s*and\s*\d+\s*months?)?)", text, re.IGNORECASE)
            if fra_match:
                result["ss_full_retirement_age"] = fra_match.group(1)

        # Pension
        if result["account_type"] == "pension":
            result["pension_monthly_benefit"] = find_value_after_label(text, r"(?:monthly (?:pension )?benefit|estimated (?:monthly )?benefit)")
            yos_match = re.search(r"(?:years of service|credited service)[:\s]*([\d.]+)", text, re.IGNORECASE)
            if yos_match:
                result["pension_years_of_service"] = float(yos_match.group(1))

        # Plan name
        plan_match = re.search(r"(?:plan name)[:\s]*([^\n]+)", text, re.IGNORECASE)
        if plan_match:
            result["plan_name"] = plan_match.group(1).strip()

        # Period
        _, result["period_end"] = extract_period_dates(text)

        return result


class PersonalFinancialStatementExtractor:
    """Extract data from personal financial statements / net worth summaries."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "total_assets": 0.0,
            "total_liabilities": 0.0,
            "net_worth": 0.0,
            "assets": {
                "cash_and_equivalents": 0.0,
                "investments": 0.0,
                "retirement_accounts": 0.0,
                "real_estate": 0.0,
                "personal_property": 0.0,
                "business_interests": 0.0,
                "other_assets": 0.0,
            },
            "liabilities": {
                "mortgages": 0.0,
                "auto_loans": 0.0,
                "student_loans": 0.0,
                "credit_cards": 0.0,
                "other_loans": 0.0,
                "other_liabilities": 0.0,
            },
            "income": {
                "employment": 0.0,
                "self_employment": 0.0,
                "investment_income": 0.0,
                "rental_income": 0.0,
                "other_income": 0.0,
                "total_annual_income": 0.0,
            },
            "expenses": {
                "total_annual_expenses": 0.0,
            },
            "as_of_date": None,
        }

        # Totals
        result["total_assets"] = find_value_after_label(text, r"(?:total assets)")
        result["total_liabilities"] = find_value_after_label(text, r"(?:total liabilities)")
        result["net_worth"] = find_value_after_label(text, r"(?:net worth|total net worth)")

        # Assets
        result["assets"]["cash_and_equivalents"] = find_value_after_label(text, r"(?:cash|checking|savings|money market)")
        result["assets"]["investments"] = find_value_after_label(text, r"(?:investments|stocks|bonds|mutual funds)")
        result["assets"]["retirement_accounts"] = find_value_after_label(text, r"(?:retirement|401k|ira|pension)")
        result["assets"]["real_estate"] = find_value_after_label(text, r"(?:real estate|property|home value|residence)")
        result["assets"]["business_interests"] = find_value_after_label(text, r"(?:business interest|business value|ownership)")
        result["assets"]["personal_property"] = find_value_after_label(text, r"(?:personal property|automobile|vehicle|jewelry)")

        # Liabilities
        result["liabilities"]["mortgages"] = find_value_after_label(text, r"(?:mortgage|home loan)")
        result["liabilities"]["auto_loans"] = find_value_after_label(text, r"(?:auto loan|car loan|vehicle loan)")
        result["liabilities"]["student_loans"] = find_value_after_label(text, r"(?:student loan|education loan)")
        result["liabilities"]["credit_cards"] = find_value_after_label(text, r"(?:credit card|revolving)")
        result["liabilities"]["other_loans"] = find_value_after_label(text, r"(?:other loan|personal loan)")

        # Income
        result["income"]["employment"] = find_value_after_label(text, r"(?:salary|wages|employment income)")
        result["income"]["self_employment"] = find_value_after_label(text, r"(?:self-employment|business income)")
        result["income"]["investment_income"] = find_value_after_label(text, r"(?:investment income|dividend|interest)")
        result["income"]["rental_income"] = find_value_after_label(text, r"(?:rental income)")
        result["income"]["total_annual_income"] = find_value_after_label(text, r"(?:total (?:annual )?income)")

        # Expenses
        result["expenses"]["total_annual_expenses"] = find_value_after_label(text, r"(?:total (?:annual )?expenses)")

        # Date
        result["as_of_date"] = extract_date_from_text(text)

        # Try table extraction for more structured data
        for table in tables:
            if not table or len(table) < 2:
                continue
            for row in table:
                if not row or len(row) < 2:
                    continue
                label = str(row[0] or "").strip().lower()
                for cell in row[1:]:
                    if cell:
                        val = clean_currency(str(cell))
                        if val > 0:
                            if "total assets" in label:
                                result["total_assets"] = max(result["total_assets"], val)
                            elif "total liabilities" in label:
                                result["total_liabilities"] = max(result["total_liabilities"], val)
                            elif "net worth" in label:
                                result["net_worth"] = max(result["net_worth"], val)
                            break

        # Calculate net worth if not found
        if not result["net_worth"] and result["total_assets"] and result["total_liabilities"]:
            result["net_worth"] = result["total_assets"] - result["total_liabilities"]

        return result


class PayStubExtractor:
    """Extract data from pay stubs."""

    def extract(self, text: str, tables: List) -> Dict[str, Any]:
        result = {
            "employer_name": "",
            "employee_name": "",
            "pay_period_start": None,
            "pay_period_end": None,
            "pay_date": None,
            "gross_pay": 0.0,
            "net_pay": 0.0,
            "ytd_gross": 0.0,
            "ytd_net": 0.0,
            "federal_tax": 0.0,
            "state_tax": 0.0,
            "social_security": 0.0,
            "medicare": 0.0,
            "retirement_contribution": 0.0,
            "health_insurance": 0.0,
        }

        result["gross_pay"] = find_value_after_label(text, r"(?:gross pay|gross earnings|total earnings)")
        result["net_pay"] = find_value_after_label(text, r"(?:net pay|take home)")
        result["ytd_gross"] = find_value_after_label(text, r"(?:ytd gross|ytd earnings|year.to.date gross)")
        result["ytd_net"] = find_value_after_label(text, r"(?:ytd net|year.to.date net)")
        result["federal_tax"] = find_value_after_label(text, r"(?:federal (?:income )?tax|fed (?:income )?tax|fit)")
        result["state_tax"] = find_value_after_label(text, r"(?:state (?:income )?tax|sit)")
        result["social_security"] = find_value_after_label(text, r"(?:social security|oasdi|fica)")
        result["medicare"] = find_value_after_label(text, r"(?:medicare)")
        result["retirement_contribution"] = find_value_after_label(text, r"(?:401k|403b|retirement|tsp)")
        result["health_insurance"] = find_value_after_label(text, r"(?:health|medical|dental|vision)")

        return result


# ═══════════════════════════════════════════════════════════════════
# Main Analyzer Class
# ═══════════════════════════════════════════════════════════════════

class SmartPDFAnalyzer:
    """
    The main analysis engine. Reads any financial PDF, classifies it,
    extracts data, and returns a structured result ready to be routed
    into the correct household/business profile fields.
    """

    # Map document types to their specialized extractors
    EXTRACTORS = {
        "brokerage_statement": BrokerageExtractor(),
        "bank_statement": BankStatementExtractor(),
        "tax_return_individual": TaxReturnExtractor(),
        "w2": W2Extractor(),
        "1099": Form1099Extractor(),
        "k1": Form1099Extractor(),  # Similar extraction patterns
        "insurance_life": InsuranceExtractor(),
        "insurance_property": InsuranceExtractor(),
        "insurance_health_disability": InsuranceExtractor(),
        "estate_will_trust": EstateExtractor(),
        "mortgage_real_estate": MortgageRealEstateExtractor(),
        "retirement_401k_ira": RetirementExtractor(),
        "social_security": RetirementExtractor(),
        "pension": RetirementExtractor(),
        "personal_financial_statement": PersonalFinancialStatementExtractor(),
        "pay_stub": PayStubExtractor(),
    }

    def __init__(self):
        self.raw_text = ""
        self.tables = []
        self.page_count = 0

    def analyze(self, filepath: str) -> Dict[str, Any]:
        """
        Analyze a PDF file and return comprehensive extracted data.

        Args:
            filepath: Path to the PDF file

        Returns:
            Dict with classification, extracted data, routing info, and metadata
        """
        if not os.path.exists(filepath):
            return self._error_result(filepath, f"File not found: {filepath}")

        result = {
            "success": False,
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "file_id": hashlib.md5(f"{filepath}_{datetime.now().isoformat()}".encode()).hexdigest()[:12],
            "analyzed_at": datetime.now().isoformat(),
            "classification": {},
            "extracted_data": {},
            "raw_text_preview": "",
            "page_count": 0,
            "routing": {},
            "warnings": [],
            "errors": [],
        }

        try:
            # Extract text and tables
            with pdfplumber.open(filepath) as pdf:
                self.page_count = len(pdf.pages)
                result["page_count"] = self.page_count

                pages_text = []
                self.tables = []

                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
                    page_tables = page.extract_tables()
                    if page_tables:
                        self.tables.extend(page_tables)

                self.raw_text = "\n".join(pages_text)

            if not self.raw_text.strip():
                result["warnings"].append("PDF appears to be image-based (no extractable text). OCR may be needed.")
                result["success"] = True
                result["classification"] = {
                    "doc_type": "unknown",
                    "category": "unknown",
                    "confidence": 0,
                }
                return result

            result["raw_text_preview"] = self.raw_text[:500] + ("..." if len(self.raw_text) > 500 else "")

            # Classify the document
            classification = classify_document(self.raw_text)
            result["classification"] = classification

            # Extract data using the appropriate extractor
            doc_type = classification["doc_type"]
            extractor = self.EXTRACTORS.get(doc_type)

            if extractor:
                extracted = extractor.extract(self.raw_text, self.tables)
                result["extracted_data"] = extracted
            else:
                result["warnings"].append(f"No specialized extractor for type: {doc_type}")
                result["extracted_data"] = self._generic_extract()

            # Build routing information
            result["routing"] = self._build_routing(classification, result["extracted_data"])

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Analysis error: {str(e)}")

        return result

    def analyze_batch(self, filepaths: List[str]) -> Dict[str, Any]:
        """Analyze multiple PDFs and return combined results."""
        batch_result = {
            "success": True,
            "analyzed_at": datetime.now().isoformat(),
            "total_files": len(filepaths),
            "successful": 0,
            "failed": 0,
            "results": [],
            "combined_routing": {
                "individual": {},
                "business": {},
            },
        }

        for filepath in filepaths:
            result = self.analyze(filepath)
            batch_result["results"].append(result)

            if result["success"]:
                batch_result["successful"] += 1
                # Merge routing
                category = result["classification"].get("category", "")
                section = result["classification"].get("profile_section", "")
                if category and section:
                    routing_target = batch_result["combined_routing"].get(category, {})
                    if section not in routing_target:
                        routing_target[section] = []
                    routing_target[section].append({
                        "file": result["filename"],
                        "doc_type": result["classification"]["doc_type"],
                        "data": result["extracted_data"],
                    })
                    batch_result["combined_routing"][category] = routing_target
            else:
                batch_result["failed"] += 1

        return batch_result

    def _build_routing(self, classification: Dict, extracted_data: Dict) -> Dict[str, Any]:
        """
        Build routing instructions that tell the frontend/API exactly
        where to place the extracted data in the household or business profile.
        """
        doc_type = classification["doc_type"]
        category = classification["category"]
        section = classification["profile_section"]

        routing = {
            "target": category,  # "individual" or "business"
            "profile_section": section,
            "doc_type": doc_type,
            "field_mappings": {},
            "summary": "",
        }

        # Build human-readable summary
        if doc_type == "brokerage_statement":
            inst = extracted_data.get("institution", "Unknown")
            val = extracted_data.get("total_value", 0)
            routing["summary"] = f"{inst} investment account — ${val:,.2f}"
            routing["field_mappings"] = {
                "assets.investment_accts": val,
                "accounts": {
                    "type": "investment",
                    "institution": inst,
                    "balance": val,
                    "account_number": extracted_data.get("account_number", ""),
                },
            }

        elif doc_type == "bank_statement":
            inst = extracted_data.get("institution", "Unknown")
            bal = extracted_data.get("ending_balance", 0)
            acct_type = extracted_data.get("account_type", "checking")
            routing["summary"] = f"{inst} {acct_type} account — ${bal:,.2f}"
            routing["field_mappings"] = {
                "assets.checking_savings": bal,
                "accounts": {
                    "type": acct_type,
                    "institution": inst,
                    "balance": bal,
                    "account_number": extracted_data.get("account_number", ""),
                },
            }

        elif doc_type in ("tax_return_individual", "w2", "1099", "k1", "pay_stub"):
            if doc_type == "tax_return_individual":
                agi = extracted_data.get("adjusted_gross_income", 0)
                yr = extracted_data.get("tax_year", "")
                routing["summary"] = f"Tax return {yr} — AGI ${agi:,.2f}"
                routing["field_mappings"] = {
                    "tax.filing_status": extracted_data.get("filing_status", ""),
                    "tax.adjusted_gross_income": agi,
                    "tax.total_tax": extracted_data.get("total_tax", 0),
                    "tax.effective_rate": extracted_data.get("effective_tax_rate", 0),
                    "income.wages": extracted_data.get("wages", 0),
                    "income.investment": extracted_data.get("interest_income", 0) + extracted_data.get("dividend_income", 0),
                    "income.business": extracted_data.get("business_income", 0),
                    "income.rental": extracted_data.get("rental_income", 0),
                }
            elif doc_type == "w2":
                wages = extracted_data.get("wages", 0)
                emp = extracted_data.get("employer_name", "Unknown")
                routing["summary"] = f"W-2 from {emp} — ${wages:,.2f}"
                routing["field_mappings"] = {
                    "income.employment": wages,
                    "income.employer": emp,
                }
            elif doc_type in ("1099", "k1"):
                subtype = extracted_data.get("form_subtype", "1099")
                payer = extracted_data.get("payer_name", "Unknown")
                routing["summary"] = f"{subtype} from {payer}"
                routing["field_mappings"] = {
                    "income.1099s": extracted_data.get("amounts", {}),
                }
            elif doc_type == "pay_stub":
                gross = extracted_data.get("gross_pay", 0)
                routing["summary"] = f"Pay stub — gross ${gross:,.2f}"
                routing["field_mappings"] = {
                    "income.gross_pay": gross,
                    "income.retirement_contribution": extracted_data.get("retirement_contribution", 0),
                }

        elif doc_type in ("insurance_life", "insurance_property", "insurance_health_disability"):
            pol_type = extracted_data.get("policy_type", "unknown")
            coverage = extracted_data.get("coverage_amount", 0)
            routing["summary"] = f"{pol_type.replace('_', ' ').title()} policy — ${coverage:,.2f}"
            routing["field_mappings"] = {
                f"insurance.{pol_type}": {
                    "coverage": coverage,
                    "premium": extracted_data.get("premium", 0),
                    "carrier": extracted_data.get("carrier", ""),
                    "policy_number": extracted_data.get("policy_number", ""),
                    "cash_value": extracted_data.get("cash_value", 0),
                },
            }

        elif doc_type == "estate_will_trust":
            doc_subtype = extracted_data.get("document_type", "estate document")
            routing["summary"] = f"Estate document — {doc_subtype.replace('_', ' ').title()}"
            routing["field_mappings"] = {
                "estate.has_will": extracted_data.get("has_will", False),
                "estate.has_trust": extracted_data.get("has_trust", False),
                "estate.trust_type": extracted_data.get("trust_type", ""),
                "estate.has_poa_financial": extracted_data.get("has_poa_financial", False),
                "estate.has_poa_healthcare": extracted_data.get("has_poa_healthcare", False),
                "estate.executor_trustee": extracted_data.get("executor_trustee", ""),
            }

        elif doc_type == "mortgage_real_estate":
            loan_amt = extracted_data.get("loan_amount", 0) or extracted_data.get("principal_balance", 0)
            prop_val = extracted_data.get("property_value", 0)
            routing["summary"] = f"Real estate — value ${prop_val:,.2f}, mortgage ${loan_amt:,.2f}"
            routing["field_mappings"] = {
                "assets.home": prop_val,
                "liabilities.1st_mortgage": loan_amt,
                "liabilities.mortgage_rate": extracted_data.get("interest_rate", 0),
                "liabilities.mortgage_payment": extracted_data.get("monthly_payment", 0),
            }

        elif doc_type in ("retirement_401k_ira", "social_security", "pension"):
            acct_type = extracted_data.get("account_type", "retirement")
            balance = extracted_data.get("total_balance", 0)
            if acct_type == "social_security":
                fra_benefit = extracted_data.get("ss_monthly_at_fra", 0)
                routing["summary"] = f"Social Security statement — ${fra_benefit:,.0f}/mo at FRA"
                routing["field_mappings"] = {
                    "retirement.ss_monthly_62": extracted_data.get("ss_monthly_at_62", 0),
                    "retirement.ss_monthly_fra": fra_benefit,
                    "retirement.ss_monthly_70": extracted_data.get("ss_monthly_at_70", 0),
                    "retirement.ss_fra": extracted_data.get("ss_full_retirement_age", ""),
                }
            elif acct_type == "pension":
                monthly = extracted_data.get("pension_monthly_benefit", 0)
                routing["summary"] = f"Pension — ${monthly:,.0f}/mo estimated benefit"
                routing["field_mappings"] = {
                    "retirement.pension_monthly": monthly,
                    "retirement.pension_years_service": extracted_data.get("pension_years_of_service", 0),
                }
            else:
                routing["summary"] = f"{acct_type.upper()} — ${balance:,.2f}"
                routing["field_mappings"] = {
                    "retirement.accounts": {
                        "type": acct_type,
                        "balance": balance,
                        "vested": extracted_data.get("vested_balance", 0),
                        "plan_name": extracted_data.get("plan_name", ""),
                    },
                    "assets.retirement_accts": balance,
                }

        elif doc_type == "personal_financial_statement":
            nw = extracted_data.get("net_worth", 0)
            routing["summary"] = f"Personal financial statement — net worth ${nw:,.2f}"
            routing["field_mappings"] = {
                "assets": extracted_data.get("assets", {}),
                "liabilities": extracted_data.get("liabilities", {}),
                "income": extracted_data.get("income", {}),
                "net_worth": nw,
            }

        # Business documents
        elif doc_type == "business_income_statement":
            routing["summary"] = "Business income statement / P&L"
            routing["field_mappings"] = {"financials.income_statement": extracted_data}

        elif doc_type == "business_balance_sheet":
            routing["summary"] = "Business balance sheet"
            routing["field_mappings"] = {"financials.balance_sheet": extracted_data}

        elif doc_type == "business_cash_flow":
            routing["summary"] = "Business cash flow statement"
            routing["field_mappings"] = {"financials.cash_flow": extracted_data}

        elif doc_type == "business_tax_return":
            routing["summary"] = "Business tax return"
            routing["field_mappings"] = {"financials.tax_return": extracted_data}

        elif doc_type == "business_bank_statement":
            routing["summary"] = "Business bank statement"
            routing["field_mappings"] = {"accounts": extracted_data}

        elif doc_type == "business_valuation":
            routing["summary"] = "Business valuation report"
            routing["field_mappings"] = {"valuation": extracted_data}

        else:
            routing["summary"] = f"Document analyzed — type: {doc_type}"
            routing["field_mappings"] = extracted_data

        return routing

    def _generic_extract(self) -> Dict[str, Any]:
        """Fallback extraction for unrecognized documents."""
        result = {
            "raw_numbers": [],
            "dates_found": [],
            "names_found": [],
            "accounts_found": [],
        }

        # Extract all dollar amounts
        for match in re.finditer(r"\$[\d,]+\.?\d*", self.raw_text):
            val = clean_currency(match.group(0))
            if val > 0:
                result["raw_numbers"].append(val)
        result["raw_numbers"] = sorted(set(result["raw_numbers"]), reverse=True)[:20]

        # Extract dates
        for match in re.finditer(r"\d{1,2}/\d{1,2}/\d{2,4}", self.raw_text):
            result["dates_found"].append(match.group(0))
        result["dates_found"] = list(set(result["dates_found"]))[:10]

        # Extract potential account numbers
        for match in re.finditer(r"(?:account|acct)[#:\s]*([A-Z0-9\-\*]+\d{3,})", self.raw_text, re.IGNORECASE):
            result["accounts_found"].append(match.group(1))

        return result

    def _error_result(self, filepath: str, error: str) -> Dict[str, Any]:
        return {
            "success": False,
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "errors": [error],
            "classification": {},
            "extracted_data": {},
            "routing": {},
        }


# ═══════════════════════════════════════════════════════════════════
# Profile Merger — Routes extracted data into household/business profiles
# ═══════════════════════════════════════════════════════════════════

class ProfileMerger:
    """
    Takes analyzed PDF results and merges them into an existing
    household (individual) or business profile, updating the correct fields.
    """

    @staticmethod
    def merge_into_individual_profile(
        existing_profile: Dict[str, Any],
        analysis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge extracted data into an individual/household financial profile.
        Non-destructive: only updates fields that have new data, never erases existing.
        """
        if not analysis_result.get("success"):
            return existing_profile

        routing = analysis_result.get("routing", {})
        mappings = routing.get("field_mappings", {})
        doc_type = analysis_result.get("classification", {}).get("doc_type", "")

        profile = dict(existing_profile)

        # Track what was imported
        if "import_history" not in profile:
            profile["import_history"] = []

        profile["import_history"].append({
            "filename": analysis_result.get("filename", ""),
            "doc_type": doc_type,
            "summary": routing.get("summary", ""),
            "imported_at": datetime.now().isoformat(),
            "file_id": analysis_result.get("file_id", ""),
        })

        # Apply field mappings
        for key, value in mappings.items():
            if not value:
                continue

            parts = key.split(".")
            target = profile

            # Navigate / create nested structure
            for i, part in enumerate(parts[:-1]):
                if part not in target or not isinstance(target[part], dict):
                    target[part] = {}
                target = target[part]

            final_key = parts[-1]

            # Smart merge logic
            if isinstance(value, dict) and isinstance(target.get(final_key), dict):
                # Merge dicts, preferring new non-zero/non-empty values
                existing = target[final_key]
                for vk, vv in value.items():
                    if vv and (vv != 0 or vk not in existing):
                        existing[vk] = vv
                target[final_key] = existing
            elif isinstance(value, list):
                # Append to lists
                existing = target.get(final_key, [])
                if isinstance(existing, list):
                    target[final_key] = existing + value
                else:
                    target[final_key] = value
            elif isinstance(value, (int, float)) and value > 0:
                # Only overwrite numbers if new value is non-zero
                target[final_key] = value
            elif isinstance(value, str) and value:
                # Only overwrite strings if new value is non-empty
                target[final_key] = value
            elif isinstance(value, bool):
                target[final_key] = value

        # Update last_updated timestamp
        profile["last_updated"] = datetime.now().isoformat()

        return profile

    @staticmethod
    def merge_into_business_profile(
        existing_profile: Dict[str, Any],
        analysis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge extracted data into a business profile.
        """
        if not analysis_result.get("success"):
            return existing_profile

        routing = analysis_result.get("routing", {})
        mappings = routing.get("field_mappings", {})
        doc_type = analysis_result.get("classification", {}).get("doc_type", "")

        profile = dict(existing_profile)

        if "import_history" not in profile:
            profile["import_history"] = []

        profile["import_history"].append({
            "filename": analysis_result.get("filename", ""),
            "doc_type": doc_type,
            "summary": routing.get("summary", ""),
            "imported_at": datetime.now().isoformat(),
            "file_id": analysis_result.get("file_id", ""),
        })

        # Apply field mappings (same logic as individual)
        for key, value in mappings.items():
            if not value:
                continue

            parts = key.split(".")
            target = profile

            for i, part in enumerate(parts[:-1]):
                if part not in target or not isinstance(target[part], dict):
                    target[part] = {}
                target = target[part]

            final_key = parts[-1]

            if isinstance(value, dict) and isinstance(target.get(final_key), dict):
                existing = target[final_key]
                for vk, vv in value.items():
                    if vv and (vv != 0 or vk not in existing):
                        existing[vk] = vv
                target[final_key] = existing
            elif isinstance(value, list):
                existing = target.get(final_key, [])
                if isinstance(existing, list):
                    target[final_key] = existing + value
                else:
                    target[final_key] = value
            elif isinstance(value, (int, float)) and value > 0:
                target[final_key] = value
            elif isinstance(value, str) and value:
                target[final_key] = value
            elif isinstance(value, bool):
                target[final_key] = value

        profile["last_updated"] = datetime.now().isoformat()
        return profile


# ═══════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════

def analyze_pdf(filepath: str) -> Dict[str, Any]:
    """Quick function to analyze a single PDF."""
    analyzer = SmartPDFAnalyzer()
    return analyzer.analyze(filepath)


def analyze_pdfs(filepaths: List[str]) -> Dict[str, Any]:
    """Analyze multiple PDFs in batch."""
    analyzer = SmartPDFAnalyzer()
    return analyzer.analyze_batch(filepaths)


def merge_to_individual(profile: Dict, result: Dict) -> Dict:
    """Merge analysis result into individual profile."""
    return ProfileMerger.merge_into_individual_profile(profile, result)


def merge_to_business(profile: Dict, result: Dict) -> Dict:
    """Merge analysis result into business profile."""
    return ProfileMerger.merge_into_business_profile(profile, result)
