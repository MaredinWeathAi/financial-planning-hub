"""
Business financial data models for the Financial Planning application.

Represents business entities, their financial statements, accounts, debt,
goals, and comprehensive business plans for advisory purposes.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from decimal import Decimal


class EntityType(Enum):
    """Business entity structures."""
    SOLE_PROPRIETOR = "sole_proprietor"
    LLC = "llc"
    S_CORP = "s_corp"
    C_CORP = "c_corp"
    PARTNERSHIP = "partnership"
    NONPROFIT = "nonprofit"
    OTHER = "other"


class AccountType(Enum):
    """Business account types."""
    BUSINESS_CHECKING = "business_checking"
    BUSINESS_SAVINGS = "business_savings"
    MONEY_MARKET = "money_market"
    LOAN_ACCOUNT = "loan_account"
    INVESTMENT = "investment"
    TRUST = "trust"
    OTHER = "other"


class DebtType(Enum):
    """Types of business debt."""
    BANK_LOAN = "bank_loan"
    LINE_OF_CREDIT = "line_of_credit"
    EQUIPMENT_FINANCING = "equipment_financing"
    REAL_ESTATE_LOAN = "real_estate_loan"
    SBA_LOAN = "sba_loan"
    SHAREHOLDER_LOAN = "shareholder_loan"
    CREDIT_CARD = "credit_card"
    INVOICE_FINANCING = "invoice_financing"
    OTHER = "other"


class GoalType(Enum):
    """Types of business goals."""
    GROWTH = "growth"
    PROFITABILITY = "profitability"
    CASH_FLOW = "cash_flow"
    DEBT_REDUCTION = "debt_reduction"
    ACQUISITION = "acquisition"
    EXIT = "exit"
    SUCCESSION = "succession"
    EXPANSION = "expansion"
    OTHER = "other"


class GoalPriority(Enum):
    """Goal priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ═══════════════════════════════════════════════════════════════════
# Business Profile
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BusinessClient:
    """
    Represents a business client.
    """
    id: str = ""
    name: str = ""                         # Company legal name
    ein: str = ""                          # Employer Identification Number (Tax ID)
    entity_type: str = "llc"               # EntityType enum value
    industry: str = ""                     # Industry classification
    description: str = ""                  # Business description/overview

    # Contact info
    primary_contact_name: str = ""
    primary_contact_email: str = ""
    primary_contact_phone: str = ""

    # Address
    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = "US"

    # Business info
    fiscal_year_end: str = "12-31"         # MM-DD format
    years_in_business: int = 0
    number_of_employees: int = 0
    annual_revenue: float = 0.0

    # Metadata
    active: bool = True
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            import hashlib
            key = f"{self.name}|{self.ein}|{datetime.now().isoformat()}"
            self.id = "biz_" + hashlib.sha256(key.encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    @property
    def full_address(self) -> str:
        """Format full address."""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        if self.city or self.state or self.zip_code:
            parts.append(f"{self.city}, {self.state} {self.zip_code}")
        if self.country and self.country != "US":
            parts.append(self.country)
        return "\n".join(p for p in parts if p)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessClient":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════
# Financial Statements
# ═══════════════════════════════════════════════════════════════════

@dataclass
class IncomeStatementData:
    """
    Profit & Loss statement data.
    """
    period_start: date = field(default_factory=date.today)
    period_end: date = field(default_factory=date.today)

    # Revenue
    total_revenue: float = 0.0
    product_revenue: float = 0.0
    service_revenue: float = 0.0
    other_revenue: float = 0.0

    # Cost of Goods Sold
    cogs: float = 0.0
    materials: float = 0.0
    labor: float = 0.0
    manufacturing: float = 0.0

    # Gross Profit
    gross_profit: float = 0.0
    gross_profit_margin: float = 0.0

    # Operating Expenses
    total_operating_expenses: float = 0.0

    # Detailed expenses
    salaries_and_wages: float = 0.0
    rent: float = 0.0
    utilities: float = 0.0
    insurance: float = 0.0
    office_supplies: float = 0.0
    marketing: float = 0.0
    depreciation: float = 0.0
    amortization: float = 0.0
    professional_fees: float = 0.0  # Legal, accounting
    repairs_maintenance: float = 0.0
    travel: float = 0.0
    meals_entertainment: float = 0.0
    vehicle_expenses: float = 0.0
    other_expenses: float = 0.0

    # EBITDA
    ebitda: float = 0.0

    # Operating Income
    operating_income: float = 0.0
    operating_margin: float = 0.0

    # Other income/expenses
    interest_income: float = 0.0
    interest_expense: float = 0.0
    other_income: float = 0.0
    other_expense: float = 0.0

    # Pre-tax and Tax
    income_before_tax: float = 0.0
    income_tax_expense: float = 0.0
    tax_rate: float = 0.0

    # Net Income
    net_income: float = 0.0
    net_profit_margin: float = 0.0

    # Additional metrics
    revenue_growth_rate: float = 0.0  # YoY if applicable
    notes: str = ""


@dataclass
class BalanceSheetData:
    """
    Balance sheet snapshot (Assets = Liabilities + Equity).
    """
    date: date = field(default_factory=date.today)

    # ASSETS
    total_assets: float = 0.0

    # Current Assets
    current_assets: float = 0.0
    cash_and_equivalents: float = 0.0
    accounts_receivable: float = 0.0
    inventory: float = 0.0
    prepaid_expenses: float = 0.0
    other_current_assets: float = 0.0

    # Fixed Assets
    fixed_assets: float = 0.0
    property_and_equipment: float = 0.0
    accumulated_depreciation: float = 0.0
    net_fixed_assets: float = 0.0

    # Intangible Assets
    intangible_assets: float = 0.0
    goodwill: float = 0.0
    other_intangibles: float = 0.0

    # Other Assets
    long_term_investments: float = 0.0
    other_long_term_assets: float = 0.0

    # LIABILITIES
    total_liabilities: float = 0.0

    # Current Liabilities
    current_liabilities: float = 0.0
    accounts_payable: float = 0.0
    short_term_debt: float = 0.0
    accrued_expenses: float = 0.0
    current_portion_long_term_debt: float = 0.0
    other_current_liabilities: float = 0.0

    # Long-term Liabilities
    long_term_debt: float = 0.0
    deferred_tax_liabilities: float = 0.0
    other_long_term_liabilities: float = 0.0

    # EQUITY
    total_equity: float = 0.0
    common_stock: float = 0.0
    retained_earnings: float = 0.0
    paid_in_capital: float = 0.0
    other_equity: float = 0.0

    # Key Ratios
    current_ratio: float = 0.0  # Current Assets / Current Liabilities
    quick_ratio: float = 0.0    # (Current Assets - Inventory) / Current Liabilities
    debt_to_equity: float = 0.0

    notes: str = ""


@dataclass
class CashFlowData:
    """
    Cash flow statement (Operating, Investing, Financing activities).
    """
    period_start: date = field(default_factory=date.today)
    period_end: date = field(default_factory=date.today)

    # Operating Activities
    operating_cash_flow: float = 0.0
    net_income: float = 0.0
    depreciation: float = 0.0
    amortization: float = 0.0
    changes_in_working_capital: float = 0.0
    accounts_receivable_change: float = 0.0
    inventory_change: float = 0.0
    accounts_payable_change: float = 0.0

    # Investing Activities
    investing_cash_flow: float = 0.0
    capital_expenditures: float = 0.0
    property_equipment_purchases: float = 0.0
    property_equipment_sales: float = 0.0
    investment_purchases: float = 0.0
    investment_sales: float = 0.0

    # Financing Activities
    financing_cash_flow: float = 0.0
    debt_proceeds: float = 0.0
    debt_payments: float = 0.0
    equity_proceeds: float = 0.0
    dividend_payments: float = 0.0
    owner_distributions: float = 0.0

    # Summary
    net_change_in_cash: float = 0.0
    beginning_cash: float = 0.0
    ending_cash: float = 0.0

    notes: str = ""


@dataclass
class BusinessFinancials:
    """
    Container for all financial statement data.
    """
    id: str = ""
    business_id: str = ""
    fiscal_year: int = 0
    fiscal_year_end: str = "12-31"

    income_statement: IncomeStatementData = field(default_factory=IncomeStatementData)
    balance_sheet: BalanceSheetData = field(default_factory=BalanceSheetData)
    cash_flow: CashFlowData = field(default_factory=CashFlowData)

    # Ratios and metrics
    return_on_assets: float = 0.0
    return_on_equity: float = 0.0
    asset_turnover: float = 0.0

    # Source document info
    source_document: str = ""  # e.g., "Form 1120 2023"
    source_date: date = field(default_factory=date.today)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            import hashlib
            key = f"{self.business_id}|{self.fiscal_year}|{datetime.now().isoformat()}"
            self.id = "finc_" + hashlib.sha256(key.encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["income_statement"] = asdict(self.income_statement)
        data["balance_sheet"] = asdict(self.balance_sheet)
        data["cash_flow"] = asdict(self.cash_flow)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessFinancials":
        data = data.copy()
        if "income_statement" in data:
            data["income_statement"] = IncomeStatementData(**data["income_statement"])
        if "balance_sheet" in data:
            data["balance_sheet"] = BalanceSheetData(**data["balance_sheet"])
        if "cash_flow" in data:
            data["cash_flow"] = CashFlowData(**data["cash_flow"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════
# Accounts and Debt
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BusinessAccount:
    """
    A business bank or investment account.
    """
    id: str = ""
    business_id: str = ""
    account_name: str = ""
    account_type: str = "business_checking"
    institution: str = ""
    account_number: str = ""  # Last 4 digits only
    routing_number: str = ""
    balance: float = 0.0
    available_balance: float = 0.0
    interest_rate: float = 0.0
    apr: float = 0.0
    account_status: str = "active"  # active, closed, frozen
    opened_date: date = field(default_factory=date.today)

    # Metadata
    is_primary: bool = False
    monthly_fees: float = 0.0
    notes: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            import hashlib
            key = f"{self.business_id}|{self.account_number}|{datetime.now().isoformat()}"
            self.id = "acc_" + hashlib.sha256(key.encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessAccount":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BusinessDebt:
    """
    Represents a loan or line of credit.
    """
    id: str = ""
    business_id: str = ""
    lender: str = ""
    debt_type: str = "bank_loan"
    description: str = ""

    # Amount
    original_amount: float = 0.0
    current_balance: float = 0.0

    # Interest
    interest_rate: float = 0.0  # Annual rate as decimal (e.g., 0.05 = 5%)
    fixed: bool = True
    variable_rate_index: str = ""  # e.g., "Prime", "SOFR"
    margin: float = 0.0

    # Terms
    origination_date: date = field(default_factory=date.today)
    maturity_date: date = field(default_factory=date.today)
    term_months: int = 0
    remaining_term_months: int = 0

    # Payments
    monthly_payment: float = 0.0
    annual_payment: float = 0.0

    # Status
    status: str = "active"  # active, paid_off, defaulted, frozen
    next_payment_date: date = field(default_factory=date.today)

    # Covenant/Other
    personal_guarantee: bool = False
    collateral: str = ""
    financial_covenants: str = ""

    # Metadata
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            import hashlib
            key = f"{self.business_id}|{self.lender}|{datetime.now().isoformat()}"
            self.id = "debt_" + hashlib.sha256(key.encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    @property
    def interest_expense_annual(self) -> float:
        """Estimate annual interest expense."""
        return self.current_balance * self.interest_rate

    @property
    def years_to_maturity(self) -> float:
        """Years until maturity."""
        if self.maturity_date:
            delta = (self.maturity_date - date.today()).days
            return max(0, delta / 365.0)
        return 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessDebt":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════
# Goals and Plans
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BusinessGoal:
    """
    A business objective or target.
    """
    id: str = ""
    business_id: str = ""
    name: str = ""
    description: str = ""
    goal_type: str = "growth"
    priority: str = "medium"

    # Target
    target_value: float = 0.0  # Dollar target or percentage
    target_year: int = 0
    target_date: date = field(default_factory=date.today)

    # Tracking
    current_value: float = 0.0
    progress_percent: float = 0.0
    status: str = "active"  # active, on_track, at_risk, completed, abandoned

    # Metadata
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            import hashlib
            key = f"{self.business_id}|{self.name}|{datetime.now().isoformat()}"
            self.id = "goal_" + hashlib.sha256(key.encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessGoal":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════
# Comprehensive Business Plan
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BusinessPlan:
    """
    Complete business profile and financial plan.
    """
    id: str = ""
    business: BusinessClient = field(default_factory=BusinessClient)
    financials: List[BusinessFinancials] = field(default_factory=list)
    accounts: List[BusinessAccount] = field(default_factory=list)
    debts: List[BusinessDebt] = field(default_factory=list)
    goals: List[BusinessGoal] = field(default_factory=list)

    # Aggregated metrics
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    annual_revenue: float = 0.0
    annual_net_income: float = 0.0
    total_debt: float = 0.0

    # Planning info
    last_review_date: date = field(default_factory=date.today)
    next_review_date: date = field(default_factory=date.today)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = self.business.id
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    def calculate_metrics(self):
        """Recalculate aggregated metrics."""
        # Assets from accounts
        self.total_assets = sum(acc.balance for acc in self.accounts if acc.account_status == "active")

        # Debt totals
        self.total_debt = sum(d.current_balance for d in self.debts if d.status == "active")
        self.total_liabilities = self.total_debt

        # Equity
        if self.financials:
            latest = max(self.financials, key=lambda f: f.fiscal_year)
            self.total_equity = latest.balance_sheet.total_equity
            self.annual_revenue = latest.income_statement.total_revenue
            self.annual_net_income = latest.income_statement.net_income

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business": self.business.to_dict(),
            "financials": [f.to_dict() for f in self.financials],
            "accounts": [a.to_dict() for a in self.accounts],
            "debts": [d.to_dict() for d in self.debts],
            "goals": [g.to_dict() for g in self.goals],
            "total_assets": self.total_assets,
            "total_liabilities": self.total_liabilities,
            "total_equity": self.total_equity,
            "annual_revenue": self.annual_revenue,
            "annual_net_income": self.annual_net_income,
            "total_debt": self.total_debt,
            "last_review_date": self.last_review_date.isoformat(),
            "next_review_date": self.next_review_date.isoformat(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessPlan":
        data = data.copy()
        if "business" in data:
            data["business"] = BusinessClient.from_dict(data["business"])
        if "financials" in data:
            data["financials"] = [BusinessFinancials.from_dict(f) for f in data["financials"]]
        if "accounts" in data:
            data["accounts"] = [BusinessAccount.from_dict(a) for a in data["accounts"]]
        if "debts" in data:
            data["debts"] = [BusinessDebt.from_dict(d) for d in data["debts"]]
        if "goals" in data:
            data["goals"] = [BusinessGoal.from_dict(g) for g in data["goals"]]
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
