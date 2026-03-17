"""
DocuSign Importer for Individual Client Intake.

Supports TWO input formats:
  1. **PDF** — Completed DocuSign PDFs downloaded from an envelope.
     Uses pdfplumber to extract text with spatial position, then maps
     field values based on the known form layout.
  2. **JSON** — DocuSign template JSON exports (API/admin use).
     Maps tab values by page + Y/X coordinate.

Two form templates are supported:
  • Initial Overview Form (7 pages)
  • Wealth & Financial Planning Questionnaire (10 pages)
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# Coordinate-based field mapping
# ═══════════════════════════════════════════════════════════════════════════
# Each entry: (page, y_min, y_max, x_min, x_max) → field_name
# Ranges are inclusive and have a tolerance of ±5 to absorb minor shifts.

def _in_range(val, lo, hi, tol=8):
    return lo - tol <= int(val) <= hi + tol


def _match_pos(page, y, x, mapping):
    """Find the field name for a given tab position."""
    p = int(page)
    yy = int(y)
    xx = int(x)
    for (mp, y_lo, y_hi, x_lo, x_hi), fname in mapping.items():
        if p == mp and _in_range(yy, y_lo, y_hi) and _in_range(xx, x_lo, x_hi):
            return fname
    return None


# ───────────────────────────────────────────────────────────────
#  INITIAL OVERVIEW FORM — Text tab mapping
# ───────────────────────────────────────────────────────────────
IO_TEXT_MAP = {
    # Page 2 — Section 1: Personal & Contact Information
    # Applicant side (left, x < 400)
    (2, 48, 55, 120, 140):   "applicant_full_name",
    (2, 107, 115, 150, 165):  "applicant_ssn",
    (2, 123, 130, 150, 165):  "applicant_country_of_residence",
    (2, 174, 182, 112, 125):  "applicant_home_address",
    (2, 209, 218, 55, 70):    "applicant_city",
    (2, 209, 218, 200, 215):  "applicant_state",
    (2, 243, 250, 112, 125):  "applicant_email",
    (2, 264, 272, 112, 125):  "applicant_phone",
    # Co-Applicant side (right, x > 390)
    (2, 48, 55, 410, 425):    "co_applicant_full_name",
    (2, 107, 115, 440, 455):  "co_applicant_ssn",
    (2, 123, 130, 440, 455):  "co_applicant_country_of_residence",
    (2, 174, 182, 400, 415):  "co_applicant_home_address",
    (2, 209, 218, 340, 360):  "co_applicant_city",
    (2, 209, 218, 490, 510):  "co_applicant_state",
    (2, 243, 250, 400, 415):  "co_applicant_email",
    (2, 264, 272, 400, 415):  "co_applicant_phone",

    # Section 2: Dependents (page 2, y ~357-413)
    (2, 353, 362, 60, 80):    "dependent_1_name",
    (2, 372, 380, 60, 80):    "dependent_2_name",
    (2, 390, 398, 60, 80):    "dependent_3_name",
    (2, 409, 417, 60, 80):    "dependent_4_name",

    # Section 3: Employment (page 2)
    # Applicant employment
    (2, 490, 500, 130, 150):  "applicant_professional_status",
    (2, 490, 500, 345, 360):  "applicant_occupation",
    (2, 527, 535, 85, 100):   "applicant_employer",
    (2, 544, 552, 75, 90):    "applicant_employer_address",
    (2, 561, 570, 55, 70):    "applicant_employer_city",
    (2, 561, 570, 179, 195):  "applicant_employer_state",
    (2, 561, 570, 498, 512):  "applicant_employer_country",
    # Co-Applicant employment
    (2, 611, 620, 133, 150):  "co_applicant_professional_status",
    (2, 611, 620, 347, 360):  "co_applicant_occupation",
    (2, 647, 655, 86, 100):   "co_applicant_employer",
    (2, 664, 672, 76, 90):    "co_applicant_employer_address",
    (2, 681, 690, 54, 68):    "co_applicant_employer_city",
    (2, 681, 690, 180, 195):  "co_applicant_employer_state",
    (2, 681, 690, 496, 510):  "co_applicant_employer_country",
    (2, 703, 712, 148, 162):  "other_income_sources",
    (2, 733, 742, 209, 225):  "expected_liquidity_events",

    # Page 3
    (3, 88, 97, 200, 215):    "annual_living_expenses",
    (3, 576, 585, 234, 250):  "special_risk_management_needs",

    # Section 6: Business interests (page 3-4)
    (3, 685, 694, 255, 270):  "business_valuation",

    # Page 4
    (4, 150, 160, 191, 205):  "succession_exit_strategy",
    (4, 189, 198, 250, 265):  "plans_start_sell_business",
    (4, 221, 230, 228, 245):  "life_vision_important",
    (4, 296, 305, 153, 170):  "financial_success_meaning",
    (4, 331, 340, 246, 260):  "ideal_future",
    (4, 401, 410, 418, 432):  "current_retirement_savings",

    # Page 5
    (5, 78, 87, 202, 218):    "retirement_work_plans",
    (5, 282, 290, 28, 42):    "tax_strategies_text",

    # Page 7 — Advisor name on signature page
    (7, 329, 338, 279, 295):  "advisor_name_signature",
}

IO_NUMERICAL_MAP = {
    # Section 2: Dependent ages
    (2, 353, 362, 233, 248):  "dependent_1_age",
    (2, 372, 380, 233, 248):  "dependent_2_age",
    (2, 390, 398, 232, 247):  "dependent_3_age",
    (2, 409, 417, 232, 247):  "dependent_4_age",

    # Section 3: Salaries
    (2, 509, 518, 63, 78):    "applicant_salary",
    (2, 561, 570, 368, 382):  "applicant_zip_code_employer",
    (2, 629, 638, 65, 80):    "co_applicant_salary",
    (2, 681, 690, 369, 382):  "co_applicant_zip_code_employer",

    # Page 3 — Section 3 continued
    (3, 45, 55, 160, 175):    "annual_living_expenses_num",

    # Page 3 — Section 4: Assets
    (3, 153, 162, 176, 192):  "total_estimated_net_worth",
    (3, 192, 200, 100, 115):  "total_assets",
    (3, 225, 234, 122, 140):  "asset_investment_accts",
    (3, 225, 234, 308, 322):  "asset_checking_savings",
    (3, 225, 234, 432, 448):  "asset_home",
    (3, 259, 268, 122, 140):  "asset_retirement_accts",
    (3, 259, 268, 308, 322):  "asset_business_interests",
    (3, 259, 268, 453, 468):  "asset_other_re",
    (3, 312, 320, 90, 105):   "asset_inheritance",
    (3, 312, 320, 263, 278):  "asset_insurance",
    (3, 312, 320, 432, 448):  "asset_other",

    # Page 3 — Liabilities
    (3, 354, 363, 120, 136):  "total_liabilities",
    (3, 389, 398, 97, 112):   "liability_1st_mortgage",
    (3, 389, 398, 309, 324):  "liability_other_mortgages",
    (3, 389, 398, 469, 484):  "liability_credit_cards",
    (3, 422, 432, 65, 80):    "liability_loans",
    (3, 422, 432, 264, 279):  "liability_vehicles",
    (3, 422, 432, 431, 446):  "liability_other",

    # Section 5: Insurance dollar amounts
    (3, 499, 508, 106, 120):  "insurance_life",
    (3, 499, 508, 274, 289):  "insurance_disability",
    (3, 499, 508, 449, 464):  "insurance_key_man",
    (3, 540, 549, 120, 136):  "insurance_ltc",
    (3, 540, 549, 273, 288):  "insurance_umbrella",
    (3, 540, 549, 449, 464):  "insurance_specialty",

    # Section 6: Business valuation
    (3, 720, 729, 189, 204):  "business_valuation_num",
}

IO_DATE_MAP = {
    (2, 78, 87, 99, 112):     "applicant_dob",
    (2, 78, 87, 389, 402):    "co_applicant_dob",
}

IO_LIST_MAP = {
    (2, 81, 90, 249, 265):    "applicant_marital_status",
    (2, 82, 91, 539, 555):    "co_applicant_marital_status",
    (2, 141, 152, 163, 178):  "applicant_us_resident",
    (2, 141, 152, 453, 468):  "co_applicant_us_resident",

    # Section 6
    (3, 652, 661, 218, 233):  "owns_business",

    # Sections 7-12 Yes/No dropdowns (page 4-5)
    (4, 47, 56, 220, 235):    "succession_strategy_yn",
    (4, 82, 91, 198, 213):    "plans_start_sell_yn",
    (4, 372, 381, 320, 335):  "retirement_work_yn",
    (4, 481, 490, 231, 246):  "has_will_trust",
    (4, 516, 525, 324, 339):  "has_healthcare_directive",
    (4, 551, 560, 241, 256):  "charitable_giving_estate",
    (4, 585, 594, 240, 255):  "generational_wealth_plans",
    (4, 686, 695, 322, 337):  "interested_philanthropy",
    (4, 712, 721, 252, 267):  "preferred_charity",

    (5, 30, 39, 176, 191):    "advanced_retirement_strategies",
    (5, 56, 65, 240, 255):    "charitable_tax_efficiency",
    (5, 157, 166, 369, 384):  "estate_tax_reduction",
    (5, 192, 201, 205, 220):  "re_tax_strategies",
    (5, 310, 319, 241, 256):  "preferred_communication",
    (5, 344, 353, 211, 226):  "checkin_frequency",
}

# Checkboxes mapped by page + y position → field name
# Checkboxes on page 5-7 correspond to Risk Profile questions I-IX
IO_CHECKBOX_MAP = {
    # Section 13: Risk Profile
    # I. Primary financial goal
    (5, 447, 456, 97, 112):   "risk_goal_financial_independence",
    (5, 473, 482, 97, 112):   "risk_goal_wealth_accumulation",
    (5, 500, 509, 97, 112):   "risk_goal_retirement_planning",
    (5, 526, 535, 97, 112):   "risk_goal_capital_preservation",
    (5, 553, 562, 97, 112):   "risk_goal_legacy_wealth",

    # II. Investment time horizon
    (5, 623, 632, 95, 110):   "risk_horizon_lt3",
    (5, 649, 658, 95, 110):   "risk_horizon_3_5",
    (5, 676, 685, 95, 110):   "risk_horizon_6_10",
    (5, 702, 711, 95, 110):   "risk_horizon_10plus",

    # III. Current financial situation (page 6)
    (6, 58, 67, 97, 112):     "risk_situation_stable",
    (6, 85, 94, 97, 112):     "risk_situation_comfortable",
    (6, 112, 121, 97, 112):   "risk_situation_uncertain",
    (6, 138, 147, 97, 112):   "risk_situation_unstable",

    # IV. Reaction to 20% correction
    (6, 206, 215, 97, 112):   "risk_reaction_sell",
    (6, 233, 242, 97, 112):   "risk_reaction_wait",
    (6, 259, 268, 97, 112):   "risk_reaction_calm",
    (6, 286, 295, 97, 112):   "risk_reaction_buy_more",

    # V. Risk comfort level
    (6, 355, 364, 97, 112):   "risk_comfort_none",
    (6, 382, 391, 97, 112):   "risk_comfort_low",
    (6, 409, 418, 97, 112):   "risk_comfort_moderate",
    (6, 435, 444, 97, 112):   "risk_comfort_high",

    # VI. Investment familiarity
    (6, 504, 513, 96, 111):   "risk_familiarity_none",
    (6, 530, 539, 96, 111):   "risk_familiarity_somewhat",
    (6, 557, 566, 96, 111):   "risk_familiarity_experienced",
    (6, 583, 592, 96, 111):   "risk_familiarity_highly_experienced",

    # VII. Income dependence
    (6, 653, 662, 96, 111):   "risk_income_not_at_all",
    (6, 680, 689, 96, 111):   "risk_income_somewhat",
    (6, 707, 716, 96, 111):   "risk_income_very",

    # VIII. Near-term access (page 7)
    (7, 73, 82, 96, 111):     "risk_access_1_3",
    (7, 100, 109, 96, 111):   "risk_access_4_7",
    (7, 126, 135, 96, 111):   "risk_access_10plus",

    # IX. Emergency fund
    (7, 195, 204, 96, 111):   "risk_emergency_yes",
    (7, 222, 231, 96, 111):   "risk_emergency_no",
}


# ───────────────────────────────────────────────────────────────
#  WEALTH & FINANCIAL PLANNING FORM — Tab mapping
# ───────────────────────────────────────────────────────────────
# This form is more free-text oriented (10 pages of questions).
# We'll map the text tabs by page/position to their section + question.

def _build_wealth_form_text_map():
    """Build mapping for the Wealth & Financial Planning Form.
    This form has many free-text fields spanning pages 2-9."""
    # We'll map these from the actual tab positions found in the JSON
    # Page 2: Personal & Family Information
    # Page 3: Life Vision & Goals + Major Life Events
    # Page 4: Investments & Wealth Strategy + Real Estate + Retirement
    # Page 5: Estate & Legacy + Tax Planning + Risk Management + Philanthropy
    # Page 6: Open-Ended Considerations
    # Since the text tabs in this form are large text areas with answer blocks,
    # we map by page number and approximate Y position
    return {}  # Will be populated dynamically during parsing


# ═══════════════════════════════════════════════════════════════════════════
# Parsed Client Profile
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class IndividualIntakeProfile:
    """
    Complete parsed profile from one or both DocuSign forms.
    This is the intermediate structure between raw DocuSign JSON and the
    system's Client model.
    """
    # Source tracking
    source_template: str = ""      # "initial_overview" or "wealth_planning"
    source_file: str = ""
    imported_at: str = ""

    # ── Section 1: Personal & Contact ──
    applicant_full_name: str = ""
    applicant_dob: str = ""
    applicant_marital_status: str = ""
    applicant_ssn: str = ""
    applicant_country_of_residence: str = ""
    applicant_us_resident: str = ""
    applicant_home_address: str = ""
    applicant_city: str = ""
    applicant_state: str = ""
    applicant_email: str = ""
    applicant_phone: str = ""

    co_applicant_full_name: str = ""
    co_applicant_dob: str = ""
    co_applicant_marital_status: str = ""
    co_applicant_ssn: str = ""
    co_applicant_country_of_residence: str = ""
    co_applicant_us_resident: str = ""
    co_applicant_home_address: str = ""
    co_applicant_city: str = ""
    co_applicant_state: str = ""
    co_applicant_email: str = ""
    co_applicant_phone: str = ""

    # ── Section 2: Dependents ──
    dependents: List[Dict[str, Any]] = field(default_factory=list)
    # Each: {"name": str, "age": int}

    # ── Section 3: Employment & Income ──
    applicant_professional_status: str = ""
    applicant_occupation: str = ""
    applicant_salary: float = 0.0
    applicant_employer: str = ""
    applicant_employer_address: str = ""
    applicant_employer_city: str = ""
    applicant_employer_state: str = ""
    applicant_employer_country: str = ""

    co_applicant_professional_status: str = ""
    co_applicant_occupation: str = ""
    co_applicant_salary: float = 0.0
    co_applicant_employer: str = ""
    co_applicant_employer_address: str = ""
    co_applicant_employer_city: str = ""
    co_applicant_employer_state: str = ""
    co_applicant_employer_country: str = ""

    other_income_sources: str = ""
    expected_liquidity_events: str = ""
    annual_living_expenses: float = 0.0

    # ── Section 4: Assets & Liabilities ──
    total_estimated_net_worth: float = 0.0
    total_assets: float = 0.0
    asset_investment_accts: float = 0.0
    asset_checking_savings: float = 0.0
    asset_home: float = 0.0
    asset_retirement_accts: float = 0.0
    asset_business_interests: float = 0.0
    asset_other_re: float = 0.0
    asset_inheritance: float = 0.0
    asset_insurance: float = 0.0
    asset_other: float = 0.0

    total_liabilities: float = 0.0
    liability_1st_mortgage: float = 0.0
    liability_other_mortgages: float = 0.0
    liability_credit_cards: float = 0.0
    liability_loans: float = 0.0
    liability_vehicles: float = 0.0
    liability_other: float = 0.0

    # ── Section 5: Insurance ──
    insurance_life: float = 0.0
    insurance_disability: float = 0.0
    insurance_key_man: float = 0.0
    insurance_ltc: float = 0.0
    insurance_umbrella: float = 0.0
    insurance_specialty: float = 0.0
    special_risk_management_needs: str = ""

    # ── Section 6: Business Interests ──
    owns_business: str = ""
    business_type_ownership: str = ""
    business_valuation: float = 0.0
    succession_exit_strategy: str = ""
    plans_start_sell_business: str = ""

    # ── Section 7: Life Vision & Goals ──
    life_vision_important: str = ""
    financial_success_meaning: str = ""
    ideal_future: str = ""

    # ── Section 8: Retirement ──
    target_retirement_age: str = ""
    expected_retirement_spending: str = ""
    current_retirement_savings: str = ""
    retirement_work_plans: str = ""

    # ── Section 9: Estate & Legacy ──
    has_will_trust: str = ""
    has_healthcare_directive: str = ""
    charitable_giving_estate: str = ""
    generational_wealth_plans: str = ""

    # ── Section 10: Tax Strategy ──
    advanced_retirement_strategies: str = ""
    charitable_tax_efficiency: str = ""
    estate_tax_reduction: str = ""
    re_tax_strategies: str = ""
    holds_licenses: str = ""
    tax_strategies_text: str = ""

    # ── Section 11: Philanthropy ──
    interested_philanthropy: str = ""
    preferred_charity: str = ""

    # ── Section 12: Communication Preferences ──
    preferred_communication: str = ""
    checkin_frequency: str = ""
    involvement_level: str = ""

    # ── Section 13: Risk Profile ──
    risk_profile: Dict[str, Any] = field(default_factory=dict)
    # Stores all checkbox selections:
    # primary_goal, time_horizon, financial_situation,
    # correction_reaction, risk_comfort, investment_familiarity,
    # income_dependence, near_term_access, emergency_fund
    risk_score: int = 0  # Calculated 1-10

    # ── Wealth & Financial Planning (Form 2) additional fields ──
    # Beneficiary info
    beneficiaries: List[Dict[str, Any]] = field(default_factory=list)

    # Free-text answers from the wealth questionnaire
    wealth_form_answers: Dict[str, str] = field(default_factory=dict)
    # Keys like: "top_3_priorities", "wealth_meaning", "10_20_50_year_goals",
    # "responsible_for", "lifestyle_changes", "long_term_goals",
    # "income_changes", "debt_obligations", "education_expenses", etc.

    # Investment preferences
    investment_preferences: Dict[str, str] = field(default_factory=dict)
    # Keys: private_equity, venture_capital, hedge_funds, esg, liquidity_preference

    # Real estate
    real_estate_details: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def calculate_risk_score(self) -> int:
        """Calculate a risk score from 1-10 based on checkbox answers."""
        score = 5  # Default moderate
        rp = self.risk_profile

        # Goal scoring
        goal_scores = {
            "financial_independence": 6, "wealth_accumulation": 7,
            "retirement_planning": 5, "capital_preservation": 3,
            "legacy_wealth": 6,
        }
        if rp.get("primary_goal"):
            score = goal_scores.get(rp["primary_goal"], 5)

        # Time horizon adjustment
        horizon_adj = {
            "lt3": -2, "3_5": -1, "6_10": 0, "10plus": 1,
        }
        if rp.get("time_horizon"):
            score += horizon_adj.get(rp["time_horizon"], 0)

        # Financial situation
        situation_adj = {
            "stable": 1, "comfortable": 0, "uncertain": -1, "unstable": -2,
        }
        if rp.get("financial_situation"):
            score += situation_adj.get(rp["financial_situation"], 0)

        # Correction reaction
        reaction_adj = {
            "sell": -2, "wait": -1, "calm": 1, "buy_more": 2,
        }
        if rp.get("correction_reaction"):
            score += reaction_adj.get(rp["correction_reaction"], 0)

        # Risk comfort
        comfort_adj = {
            "none": -2, "low": -1, "moderate": 0, "high": 2,
        }
        if rp.get("risk_comfort"):
            score += comfort_adj.get(rp["risk_comfort"], 0)

        # Clamp to 1-10
        self.risk_score = max(1, min(10, score))
        return self.risk_score


# ═══════════════════════════════════════════════════════════════════════════
# Parser
# ═══════════════════════════════════════════════════════════════════════════

class DocuSignIndividualParser:
    """Parse a DocuSign template JSON into an IndividualIntakeProfile."""

    INITIAL_OVERVIEW_NAMES = [
        "initial overview",
        "initial overview form",
    ]
    WEALTH_PLANNING_NAMES = [
        "wealth and financial planning",
        "wealth & financial planning",
        "comprehensive wealth",
        "financial planning form",
        "wealth and financial planning form",
    ]

    def detect_template_type(self, data: dict) -> str:
        """Detect which template this JSON represents."""
        name = (data.get("name") or "").lower().strip()
        email_subject = (data.get("emailSubject") or "").lower().strip()

        for pattern in self.INITIAL_OVERVIEW_NAMES:
            if pattern in name or pattern in email_subject:
                return "initial_overview"

        for pattern in self.WEALTH_PLANNING_NAMES:
            if pattern in name or pattern in email_subject:
                return "wealth_planning"

        # Fallback: check page count
        page_count = int(data.get("pageCount", 0))
        if page_count == 7:
            return "initial_overview"
        elif page_count == 10:
            return "wealth_planning"

        return "unknown"

    def parse(self, filepath: str) -> IndividualIntakeProfile:
        """Parse a DocuSign file (PDF or JSON) and return a profile."""
        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".pdf":
            return self._parse_pdf(filepath)
        elif ext == ".json":
            return self._parse_json(filepath)
        else:
            # Try JSON first, fall back to PDF
            try:
                return self._parse_json(filepath)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._parse_pdf(filepath)

    def _parse_json(self, filepath: str) -> IndividualIntakeProfile:
        """Parse a DocuSign JSON template export."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        template_type = self.detect_template_type(data)
        profile = IndividualIntakeProfile(
            source_template=template_type,
            source_file=os.path.basename(filepath),
        )

        signers = data.get("recipients", {}).get("signers", [])
        client_signer = None
        for s in signers:
            if (s.get("roleName", "").lower() == "client" or
                    s.get("recipientId") == signers[0].get("recipientId")):
                client_signer = s
                break

        if not client_signer:
            return profile

        tabs = client_signer.get("tabs", {})

        if template_type == "initial_overview":
            self._parse_initial_overview(tabs, profile)
        elif template_type == "wealth_planning":
            self._parse_wealth_planning(tabs, profile, data)
        else:
            self._parse_initial_overview(tabs, profile)

        return profile

    def _parse_pdf(self, filepath: str) -> IndividualIntakeProfile:
        """
        Parse a completed DocuSign PDF.
        Uses pdfplumber to extract all text with positions, then uses
        the known form layout (label positions) to find the filled-in
        values that appear adjacent to each label.
        """
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber is required for PDF parsing. Install with: pip install pdfplumber")

        profile = IndividualIntakeProfile(
            source_file=os.path.basename(filepath),
        )

        with pdfplumber.open(filepath) as pdf:
            num_pages = len(pdf.pages)

            # Detect which form this is
            first_page_text = pdf.pages[0].extract_text() or ""
            if "initial overview" in first_page_text.lower():
                profile.source_template = "initial_overview"
                self._parse_initial_overview_pdf(pdf, profile)
            elif "wealth" in first_page_text.lower() and "financial" in first_page_text.lower():
                profile.source_template = "wealth_planning"
                self._parse_wealth_planning_pdf(pdf, profile)
            else:
                # Try to detect by page count
                if num_pages <= 8:
                    profile.source_template = "initial_overview"
                    self._parse_initial_overview_pdf(pdf, profile)
                else:
                    profile.source_template = "wealth_planning"
                    self._parse_wealth_planning_pdf(pdf, profile)

        return profile

    def _parse_initial_overview_pdf(self, pdf, profile: IndividualIntakeProfile):
        """
        Parse the Initial Overview Form PDF by extracting text near known labels.
        The form has fixed label positions; filled values appear to the right of
        or below each label.
        """
        # Extract all words with positions from each page
        all_words = {}  # page_num -> list of word dicts
        all_text = {}   # page_num -> full text
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            words = page.extract_words(keep_blank_chars=True, x_tolerance=3, y_tolerance=3)
            all_words[page_num] = words
            all_text[page_num] = page.extract_text() or ""

        # Helper: find text value to the right of a label on the same line
        def get_value_after_label(page_num, label, y_tolerance=8):
            """Find text that appears to the right of a given label."""
            words = all_words.get(page_num, [])
            label_lower = label.lower()
            # Find the label word(s)
            for i, w in enumerate(words):
                if label_lower in w["text"].lower():
                    label_right = w["x1"]
                    label_y = w["top"]
                    # Collect words to the right on the same line
                    right_words = []
                    for w2 in words:
                        if (abs(w2["top"] - label_y) < y_tolerance and
                                w2["x0"] > label_right + 2):
                            right_words.append(w2)
                    right_words.sort(key=lambda x: x["x0"])
                    if right_words:
                        return " ".join(rw["text"] for rw in right_words).strip()
            return ""

        def get_value_below_label(page_num, label, y_offset=15, y_max=40):
            """Find text that appears below a label."""
            words = all_words.get(page_num, [])
            label_lower = label.lower()
            for w in words:
                if label_lower in w["text"].lower():
                    label_x = w["x0"]
                    label_y = w["top"]
                    below_words = []
                    for w2 in words:
                        if (label_y + y_offset < w2["top"] < label_y + y_max and
                                abs(w2["x0"] - label_x) < 100):
                            below_words.append(w2)
                    below_words.sort(key=lambda x: x["x0"])
                    if below_words:
                        return " ".join(bw["text"] for bw in below_words).strip()
            return ""

        def extract_by_lines(page_num):
            """Extract text organized by lines from a page."""
            text = all_text.get(page_num, "")
            return [line.strip() for line in text.split("\n") if line.strip()]

        # ── Page 2: Personal & Contact Information ──
        p2_lines = extract_by_lines(2)

        # Parse using line-based extraction with label matching
        for line in p2_lines:
            # Full Legal Name lines
            if "full legal name:" in line.lower():
                val = line.split(":", 1)[1].strip() if ":" in line else ""
                if val and not profile.applicant_full_name:
                    profile.applicant_full_name = val

        # Use label-based extraction for structured fields on page 2
        val = get_value_after_label(2, "Full Legal Name:")
        if val:
            profile.applicant_full_name = val

        val = get_value_after_label(2, "Date of Birth")
        if val:
            profile.applicant_dob = val

        val = get_value_after_label(2, "Marital Status")
        if val:
            profile.applicant_marital_status = val

        val = get_value_after_label(2, "Social Security")
        if val:
            profile.applicant_ssn = val

        val = get_value_after_label(2, "Country of Residence")
        if val:
            profile.applicant_country_of_residence = val

        val = get_value_after_label(2, "Home Address")
        if val:
            profile.applicant_home_address = val

        val = get_value_after_label(2, "Email Address")
        if val:
            profile.applicant_email = val

        val = get_value_after_label(2, "Phone Number")
        if val:
            profile.applicant_phone = val

        # ── Co-Applicant: look for second occurrences in the right half ──
        # The co-applicant fields are in the right column of page 2
        # We use a different approach: parse the full text and look for patterns
        p2_text = all_text.get(2, "")

        # Use regex to find patterns after "Co-Applicant" section
        co_match = re.search(r"Co-Applicant.*?Full Legal Name:\s*(.+?)(?:\n|$)", p2_text, re.DOTALL)
        if co_match:
            profile.co_applicant_full_name = co_match.group(1).strip()

        # ── Section 3: Employment ──
        val = get_value_after_label(2, "Occupation")
        if val:
            profile.applicant_occupation = val

        val = get_value_after_label(2, "Employer")
        if val and "address" not in val.lower():
            profile.applicant_employer = val

        val = get_value_after_label(2, "Salary")
        if val:
            try:
                profile.applicant_salary = float(re.sub(r'[,$\s]', '', val))
            except ValueError:
                pass

        # ── Page 3: Assets & Liabilities ──
        p3_text = all_text.get(3, "")

        def extract_amount(text, label):
            """Extract a dollar amount after a label in text."""
            pattern = rf"{re.escape(label)}\s*\$?([\d,]+\.?\d*)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except ValueError:
                    pass
            return 0.0

        if "Assets and Liabilities" in p3_text or "Total Estimated Net Worth" in p3_text:
            profile.total_estimated_net_worth = extract_amount(p3_text, "Total Estimated Net Worth")
            profile.asset_investment_accts = extract_amount(p3_text, "Investment Accts")
            profile.asset_checking_savings = extract_amount(p3_text, "Checking/Savings")
            profile.asset_home = extract_amount(p3_text, "Home")
            profile.asset_retirement_accts = extract_amount(p3_text, "Retirement Accts")
            profile.asset_business_interests = extract_amount(p3_text, "Business Interests")
            profile.asset_other_re = extract_amount(p3_text, "Other RE")
            profile.asset_inheritance = extract_amount(p3_text, "Inheritance")
            profile.asset_insurance = extract_amount(p3_text, "Insurance")
            profile.liability_1st_mortgage = extract_amount(p3_text, "1st Mortgage")
            profile.liability_other_mortgages = extract_amount(p3_text, "Other Mortgages")
            profile.liability_credit_cards = extract_amount(p3_text, "Credit Cards")
            profile.liability_loans = extract_amount(p3_text, "Loans")
            profile.liability_vehicles = extract_amount(p3_text, "Vehicles")

            # Insurance section
            profile.insurance_life = extract_amount(p3_text, "Life Insurance")
            profile.insurance_disability = extract_amount(p3_text, "Disability")
            profile.insurance_ltc = extract_amount(p3_text, "Long-Term Care")
            profile.insurance_umbrella = extract_amount(p3_text, "Umbrella")
            profile.insurance_key_man = extract_amount(p3_text, "Key Man")
            profile.insurance_specialty = extract_amount(p3_text, "Specialty")

        # ── Pages 4-5: Goals, Retirement, Estate, Tax ──
        for pg in [4, 5]:
            pg_text = all_text.get(pg, "")
            lines = [l.strip() for l in pg_text.split("\n") if l.strip()]

            # Look for answers after known section headers
            for i, line in enumerate(lines):
                if "what's most important" in line.lower() and i + 1 < len(lines):
                    profile.life_vision_important = lines[i + 1]
                elif "financial success mean" in line.lower() and i + 1 < len(lines):
                    profile.financial_success_meaning = lines[i + 1]
                elif "ideal future" in line.lower() and i + 1 < len(lines):
                    profile.ideal_future = lines[i + 1]
                elif "target retirement age" in line.lower() and i + 1 < len(lines):
                    profile.target_retirement_age = lines[i + 1]

        # ── Pages 5-7: Risk Profile checkboxes ──
        # In a filled PDF, checked boxes appear as ☑ or ✓ or X next to the option text
        for pg in [5, 6, 7]:
            pg_text = all_text.get(pg, "")

            # Check for risk profile answers by looking for checked indicators
            risk_checks = {
                "Financial Independence": ("primary_goal", "financial_independence"),
                "Wealth Accumulation": ("primary_goal", "wealth_accumulation"),
                "Retirement Planning": ("primary_goal", "retirement_planning"),
                "Capital Preservation": ("primary_goal", "capital_preservation"),
                "Legacy/Generational": ("primary_goal", "legacy_wealth"),
                "Less than 3 years": ("time_horizon", "lt3"),
                "3–5 years": ("time_horizon", "3_5"),
                "6–10 years": ("time_horizon", "6_10"),
                "More than 10 years": ("time_horizon", "10plus"),
                "Stable, with surplus": ("financial_situation", "stable"),
                "Comfortable, but with": ("financial_situation", "comfortable"),
                "Uncertain, with irregular": ("financial_situation", "uncertain"),
                "Unstable, focused": ("financial_situation", "unstable"),
                "very uncomfortable": ("correction_reaction", "sell"),
                "uneasy but prefer": ("correction_reaction", "wait"),
                "stay calm": ("correction_reaction", "calm"),
                "opportunity to buy": ("correction_reaction", "buy_more"),
                "None—I want capital": ("risk_comfort", "none"),
                "Low—I prefer slow": ("risk_comfort", "low"),
                "Moderate—I can handle": ("risk_comfort", "moderate"),
                "High—I'm comfortable": ("risk_comfort", "high"),
            }

            for pattern, (category, value) in risk_checks.items():
                # Look for checked checkboxes: DocuSign PDFs typically render
                # a filled checkbox as a special character before the text
                # Common patterns: ☑, ✓, X, or the checkbox field is filled
                check_pattern = rf"[☑✓✗X]\s*{re.escape(pattern)}"
                if re.search(check_pattern, pg_text, re.IGNORECASE):
                    profile.risk_profile[category] = value

        if profile.risk_profile:
            profile.calculate_risk_score()

        # ── Page 7: Signature page — extract advisor name ──
        p7_text = all_text.get(7, "")
        adv_match = re.search(r"Advisor Name.*?(?:Date)?\s+(.+?)(?:\n|$)", p7_text)
        if adv_match:
            name = adv_match.group(1).strip()
            if name and "signature" not in name.lower():
                pass  # Advisor name extracted but not stored in client profile

    def _parse_wealth_planning_pdf(self, pdf, profile: IndividualIntakeProfile):
        """Parse Wealth & Financial Planning Questionnaire PDF."""
        answers = {}

        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            if page_num == 2:
                # Personal & Family Info
                for j, line in enumerate(lines):
                    if "client name" in line.lower() and j + 1 < len(lines):
                        val = lines[j + 1]
                        if val and not any(kw in val.lower() for kw in ["preferred", "beneficiary", "name"]):
                            profile.applicant_full_name = val
                    elif "preferred name" in line.lower() and j + 1 < len(lines):
                        answers["preferred_names"] = lines[j + 1]
                    elif "advisor name:" in line.lower():
                        val = line.split(":", 1)[1].strip() if ":" in line else ""
                        if val:
                            answers["advisor_name"] = val

            elif page_num == 3:
                # Life Vision & Goals
                self._extract_qa_pairs(lines, answers, [
                    ("what's most important", "whats_most_important"),
                    ("top 3 personal", "top_3_priorities"),
                    ("wealth mean", "wealth_meaning"),
                    ("10,20,50", "10_20_50_year_goals"),
                    ("people or institutions", "responsible_for"),
                    ("lifestyle changes", "lifestyle_changes"),
                    ("long-term personal", "long_term_goals"),
                ])

            elif page_num == 4:
                # Major Life & Financial Events
                self._extract_qa_pairs(lines, answers, [
                    ("income changes", "income_changes"),
                    ("debt obligations", "debt_obligations"),
                    ("education", "education_expenses"),
                    ("weddings", "future_weddings"),
                    ("second home", "major_purchases"),
                    ("health-related", "health_expenses"),
                    ("other significant", "other_expenses"),
                    ("inheritance", "significant_inheritance"),
                    ("family dynamics", "family_dynamics"),
                ])

            elif page_num == 5:
                # Investments & Real Estate & Retirement
                self._extract_qa_pairs(lines, answers, [
                    ("concentrated stock", "concentrated_positions"),
                    ("investment strategies to mitigate", "tax_efficient_investing"),
                    ("primary residence", "primary_residence_details"),
                    ("other properties", "other_properties"),
                    ("real estate purchases", "re_purchases_planned"),
                    ("REITs", "reits_interest"),
                    ("phased retirement", "phased_full_retirement"),
                    ("international residency", "international_retirement"),
                    ("structure your time", "post_retirement_lifestyle"),
                ])

            elif page_num in [6, 7]:
                # Estate, Tax, Risk, Philanthropy, Open-ended
                for j, line in enumerate(lines):
                    # Skip section headers and questions — capture answers
                    if line and not line.endswith("?") and not line.startswith(("•", "o ", "☐")):
                        if not any(kw in line.lower() for kw in [
                            "docusign", "envelope", "estate", "tax planning",
                            "risk management", "philanthropy", "open-ended",
                        ]):
                            answers[f"page{page_num}_answer_{j}"] = line

        profile.wealth_form_answers = answers

    def _extract_qa_pairs(self, lines, answers, patterns):
        """Extract question-answer pairs from text lines."""
        for question_pattern, answer_key in patterns:
            for i, line in enumerate(lines):
                if question_pattern.lower() in line.lower():
                    # The answer is typically on the next line(s)
                    if i + 1 < len(lines):
                        answer = lines[i + 1]
                        # Skip if the next line looks like another question
                        if not answer.endswith("?") and not answer.startswith(("•", "o ")):
                            answers[answer_key] = answer
                    break

    def _parse_initial_overview(self, tabs: dict, profile: IndividualIntakeProfile):
        """Parse Initial Overview Form tabs."""
        # Text tabs
        for tab in tabs.get("textTabs", []):
            page = tab.get("pageNumber", "")
            y = tab.get("yPosition", "")
            x = tab.get("xPosition", "")
            value = (tab.get("value") or "").strip()
            if not value:
                continue
            fname = _match_pos(page, y, x, IO_TEXT_MAP)
            if fname and hasattr(profile, fname):
                setattr(profile, fname, value)

        # Numerical tabs
        for tab in tabs.get("numericalTabs", []):
            page = tab.get("pageNumber", "")
            y = tab.get("yPosition", "")
            x = tab.get("xPosition", "")
            value = tab.get("value", "")
            if not value:
                continue
            fname = _match_pos(page, y, x, IO_NUMERICAL_MAP)
            if fname and hasattr(profile, fname):
                try:
                    setattr(profile, fname, float(str(value).replace(",", "").replace("$", "")))
                except (ValueError, TypeError):
                    pass

        # Date tabs
        for tab in tabs.get("dateTabs", []):
            page = tab.get("pageNumber", "")
            y = tab.get("yPosition", "")
            x = tab.get("xPosition", "")
            value = (tab.get("value") or "").strip()
            if not value:
                continue
            fname = _match_pos(page, y, x, IO_DATE_MAP)
            if fname and hasattr(profile, fname):
                setattr(profile, fname, value)

        # List/Dropdown tabs
        for tab in tabs.get("listTabs", []):
            page = tab.get("pageNumber", "")
            y = tab.get("yPosition", "")
            x = tab.get("xPosition", "")
            value = (tab.get("value") or "").strip()
            if not value:
                continue
            fname = _match_pos(page, y, x, IO_LIST_MAP)
            if fname and hasattr(profile, fname):
                setattr(profile, fname, value)

        # Checkbox tabs → risk profile
        risk_data = {}
        for tab in tabs.get("checkboxTabs", []):
            page = tab.get("pageNumber", "")
            y = tab.get("yPosition", "")
            x = tab.get("xPosition", "")
            selected = str(tab.get("selected", "")).lower() == "true"
            if not selected:
                continue
            fname = _match_pos(page, y, x, IO_CHECKBOX_MAP)
            if not fname:
                continue

            # Map checkbox field names to risk profile categories
            if fname.startswith("risk_goal_"):
                risk_data["primary_goal"] = fname.replace("risk_goal_", "")
            elif fname.startswith("risk_horizon_"):
                risk_data["time_horizon"] = fname.replace("risk_horizon_", "")
            elif fname.startswith("risk_situation_"):
                risk_data["financial_situation"] = fname.replace("risk_situation_", "")
            elif fname.startswith("risk_reaction_"):
                risk_data["correction_reaction"] = fname.replace("risk_reaction_", "")
            elif fname.startswith("risk_comfort_"):
                risk_data["risk_comfort"] = fname.replace("risk_comfort_", "")
            elif fname.startswith("risk_familiarity_"):
                risk_data["investment_familiarity"] = fname.replace("risk_familiarity_", "")
            elif fname.startswith("risk_income_"):
                risk_data["income_dependence"] = fname.replace("risk_income_", "")
            elif fname.startswith("risk_access_"):
                risk_data["near_term_access"] = fname.replace("risk_access_", "")
            elif fname.startswith("risk_emergency_"):
                risk_data["emergency_fund"] = fname.replace("risk_emergency_", "")

        profile.risk_profile = risk_data
        if risk_data:
            profile.calculate_risk_score()

        # Build dependents list
        deps = []
        for i in range(1, 5):
            name_val = getattr(profile, f"dependent_{i}_name", "")
            age_val = getattr(profile, f"dependent_{i}_age", 0)
            if name_val:
                deps.append({"name": name_val, "age": int(age_val) if age_val else 0})
        profile.dependents = deps

    def _parse_wealth_planning(self, tabs: dict, profile: IndividualIntakeProfile, data: dict):
        """Parse Wealth & Financial Planning Form tabs.
        This form is mostly free-text answers to open-ended questions."""

        # Extract all text tabs sorted by page and position
        text_tabs = sorted(
            tabs.get("textTabs", []),
            key=lambda t: (int(t.get("pageNumber", 0)), int(t.get("yPosition", 0)))
        )

        # Group text values by page to map to the known question sections
        page_texts = {}
        for tab in text_tabs:
            page = int(tab.get("pageNumber", 0))
            value = (tab.get("value") or "").strip()
            if value:
                if page not in page_texts:
                    page_texts[page] = []
                page_texts[page].append({
                    "y": int(tab.get("yPosition", 0)),
                    "x": int(tab.get("xPosition", 0)),
                    "value": value,
                })

        answers = {}

        # Page 2: Personal & Family Info
        # Client Names, Preferred names, Beneficiary info
        p2 = page_texts.get(2, [])
        if p2:
            # First text field on page 2 is usually advisor name, then client names
            for entry in p2:
                y = entry["y"]
                if y < 100:
                    # Advisor name area — skip or capture
                    pass
                elif 100 <= y < 160:
                    if not profile.applicant_full_name:
                        profile.applicant_full_name = entry["value"]
                elif 160 <= y < 220:
                    answers["preferred_names"] = entry["value"]

        # Page 3: Life Vision & Goals
        p3 = page_texts.get(3, [])
        vision_questions = [
            "whats_most_important", "top_3_priorities", "wealth_meaning",
            "10_20_50_year_goals", "responsible_for", "lifestyle_changes",
            "long_term_goals",
        ]
        for i, entry in enumerate(p3):
            if i < len(vision_questions):
                answers[vision_questions[i]] = entry["value"]

        # Page 4: Major Life Events + Investments + Real Estate + Retirement
        p4_texts = page_texts.get(4, [])
        p4_questions = [
            "income_changes", "debt_obligations", "education_expenses",
            "future_weddings", "major_purchases", "health_expenses",
            "other_expenses", "significant_inheritance", "family_dynamics",
        ]
        for i, entry in enumerate(p4_texts):
            if i < len(p4_questions):
                answers[p4_questions[i]] = entry["value"]

        # Page 5: Investments & Real Estate + Retirement
        p5_texts = page_texts.get(5, [])
        p5_questions = [
            "concentrated_positions", "tax_efficient_investing",
            "primary_residence_details", "other_properties",
            "re_purchases_planned", "reits_interest",
            "phased_full_retirement", "international_retirement",
            "post_retirement_lifestyle",
        ]
        for i, entry in enumerate(p5_texts):
            if i < len(p5_questions):
                answers[p5_questions[i]] = entry["value"]

        # Pages 6-7: Estate, Tax, Risk, Philanthropy, Open-ended
        for page_num in [6, 7]:
            p_texts = page_texts.get(page_num, [])
            for i, entry in enumerate(p_texts):
                answers[f"page{page_num}_answer_{i+1}"] = entry["value"]

        profile.wealth_form_answers = answers

        # Parse checkbox tabs for investment preferences (Yes/No/Not Sure)
        for tab in tabs.get("checkboxTabs", []):
            selected = str(tab.get("selected", "")).lower() == "true"
            if not selected:
                continue
            page = int(tab.get("pageNumber", 0))
            y = int(tab.get("yPosition", 0))
            # Map page 4 checkboxes to investment preferences
            # (private equity, VC, hedge funds, ESG — each has Yes/No/Not Sure)

        # Parse list/dropdown tabs
        for tab in tabs.get("listTabs", []):
            value = (tab.get("value") or "").strip()
            if not value:
                continue
            # These could be gender dropdowns, relationship dropdowns, etc.

        # Parse numerical tabs for beneficiary percentages, etc.
        for tab in tabs.get("numericalTabs", []):
            value = tab.get("value", "")
            if not value:
                continue

    def parse_multiple(self, filepaths: List[str]) -> IndividualIntakeProfile:
        """Parse multiple DocuSign JSONs and merge into one profile."""
        merged = IndividualIntakeProfile()

        for filepath in filepaths:
            profile = self.parse(filepath)
            self._merge_profiles(merged, profile)

        if merged.risk_profile:
            merged.calculate_risk_score()

        return merged

    def _merge_profiles(self, target: IndividualIntakeProfile, source: IndividualIntakeProfile):
        """Merge source profile into target, preferring non-empty values."""
        for fname in target.__dataclass_fields__:
            src_val = getattr(source, fname)
            tgt_val = getattr(target, fname)

            # Skip metadata fields
            if fname in ("source_template", "source_file", "imported_at"):
                continue

            # For strings: prefer non-empty
            if isinstance(src_val, str) and src_val and not tgt_val:
                setattr(target, fname, src_val)
            # For numbers: prefer non-zero
            elif isinstance(src_val, (int, float)) and src_val and not tgt_val:
                setattr(target, fname, src_val)
            # For dicts: merge
            elif isinstance(src_val, dict) and src_val:
                if isinstance(tgt_val, dict):
                    merged_dict = {**tgt_val, **src_val}
                    setattr(target, fname, merged_dict)
                else:
                    setattr(target, fname, src_val)
            # For lists: extend if source has items
            elif isinstance(src_val, list) and src_val and not tgt_val:
                setattr(target, fname, src_val)


# ═══════════════════════════════════════════════════════════════════════════
# Client Record Mapper — Convert profile to Client model
# ═══════════════════════════════════════════════════════════════════════════

def profile_to_client_dict(profile: IndividualIntakeProfile) -> dict:
    """
    Convert an IndividualIntakeProfile to a dict compatible with the
    Client model + extended financial planning fields.

    Returns a dict with:
      - core_fields: fields that map directly to the Client dataclass
      - extended_fields: additional financial planning data stored in client.notes
        or a separate JSON structure
    """
    # Build the primary client name
    names = [profile.applicant_full_name]
    if profile.co_applicant_full_name:
        names.append(profile.co_applicant_full_name)
    client_name = " & ".join(n for n in names if n)

    core = {
        "name": client_name,
        "email": profile.applicant_email,
        "phone": profile.applicant_phone,
        "address_line1": profile.applicant_home_address,
        "city": profile.applicant_city,
        "state": profile.applicant_state,
        "country": profile.applicant_country_of_residence or "US",
        "tags": ["individual", "docusign-import"],
    }

    # Extended financial planning data (stored as JSON in a dedicated field)
    extended = {
        "client_type": "individual",
        "import_source": "docusign",

        # Applicant details
        "applicant": {
            "full_name": profile.applicant_full_name,
            "dob": profile.applicant_dob,
            "marital_status": profile.applicant_marital_status,
            "country_of_residence": profile.applicant_country_of_residence,
            "us_resident": profile.applicant_us_resident,
            "email": profile.applicant_email,
            "phone": profile.applicant_phone,
            "employment": {
                "professional_status": profile.applicant_professional_status,
                "occupation": profile.applicant_occupation,
                "salary": profile.applicant_salary,
                "employer": profile.applicant_employer,
                "employer_address": profile.applicant_employer_address,
                "employer_city": profile.applicant_employer_city,
                "employer_state": profile.applicant_employer_state,
                "employer_country": profile.applicant_employer_country,
            },
        },

        # Co-applicant
        "co_applicant": {
            "full_name": profile.co_applicant_full_name,
            "dob": profile.co_applicant_dob,
            "marital_status": profile.co_applicant_marital_status,
            "country_of_residence": profile.co_applicant_country_of_residence,
            "us_resident": profile.co_applicant_us_resident,
            "email": profile.co_applicant_email,
            "phone": profile.co_applicant_phone,
            "employment": {
                "professional_status": profile.co_applicant_professional_status,
                "occupation": profile.co_applicant_occupation,
                "salary": profile.co_applicant_salary,
                "employer": profile.co_applicant_employer,
                "employer_address": profile.co_applicant_employer_address,
                "employer_city": profile.co_applicant_employer_city,
                "employer_state": profile.co_applicant_employer_state,
                "employer_country": profile.co_applicant_employer_country,
            },
        } if profile.co_applicant_full_name else None,

        "dependents": profile.dependents,

        "income": {
            "applicant_salary": profile.applicant_salary,
            "co_applicant_salary": profile.co_applicant_salary,
            "other_sources": profile.other_income_sources,
            "expected_liquidity_events": profile.expected_liquidity_events,
            "annual_living_expenses": profile.annual_living_expenses,
        },

        "assets": {
            "total_net_worth": profile.total_estimated_net_worth,
            "total_assets": profile.total_assets,
            "investment_accounts": profile.asset_investment_accts,
            "checking_savings": profile.asset_checking_savings,
            "home": profile.asset_home,
            "retirement_accounts": profile.asset_retirement_accts,
            "business_interests": profile.asset_business_interests,
            "other_real_estate": profile.asset_other_re,
            "inheritance": profile.asset_inheritance,
            "insurance_value": profile.asset_insurance,
            "other": profile.asset_other,
        },

        "liabilities": {
            "total": profile.total_liabilities,
            "first_mortgage": profile.liability_1st_mortgage,
            "other_mortgages": profile.liability_other_mortgages,
            "credit_cards": profile.liability_credit_cards,
            "loans": profile.liability_loans,
            "vehicles": profile.liability_vehicles,
            "other": profile.liability_other,
        },

        "insurance": {
            "life": profile.insurance_life,
            "disability": profile.insurance_disability,
            "key_man": profile.insurance_key_man,
            "long_term_care": profile.insurance_ltc,
            "umbrella": profile.insurance_umbrella,
            "specialty": profile.insurance_specialty,
            "special_needs": profile.special_risk_management_needs,
        },

        "business": {
            "owns_business": profile.owns_business,
            "type_ownership": profile.business_type_ownership,
            "valuation": profile.business_valuation,
            "succession_strategy": profile.succession_exit_strategy,
            "plans_start_sell": profile.plans_start_sell_business,
        },

        "goals": {
            "life_vision": profile.life_vision_important,
            "financial_success_meaning": profile.financial_success_meaning,
            "ideal_future": profile.ideal_future,
        },

        "retirement": {
            "target_age": profile.target_retirement_age,
            "expected_spending": profile.expected_retirement_spending,
            "current_savings": profile.current_retirement_savings,
            "work_plans": profile.retirement_work_plans,
        },

        "estate": {
            "has_will_trust": profile.has_will_trust,
            "has_healthcare_directive": profile.has_healthcare_directive,
            "charitable_giving": profile.charitable_giving_estate,
            "generational_wealth": profile.generational_wealth_plans,
        },

        "tax_strategy": {
            "advanced_retirement": profile.advanced_retirement_strategies,
            "charitable_efficiency": profile.charitable_tax_efficiency,
            "estate_tax_reduction": profile.estate_tax_reduction,
            "real_estate_strategies": profile.re_tax_strategies,
            "notes": profile.tax_strategies_text,
        },

        "philanthropy": {
            "interested": profile.interested_philanthropy,
            "preferred_charity": profile.preferred_charity,
        },

        "communication": {
            "preferred_method": profile.preferred_communication,
            "checkin_frequency": profile.checkin_frequency,
            "involvement_level": profile.involvement_level,
        },

        "risk_profile": profile.risk_profile,
        "risk_score": profile.risk_score,

        "beneficiaries": profile.beneficiaries,
        "wealth_form_answers": profile.wealth_form_answers,
        "investment_preferences": profile.investment_preferences,
        "real_estate_details": profile.real_estate_details,
    }

    # Remove None co_applicant if not present
    if extended.get("co_applicant") is None:
        del extended["co_applicant"]

    return {"core": core, "extended": extended}
