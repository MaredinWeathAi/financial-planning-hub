"""
Business PDF Parser for Financial Planning Application.

Intelligently extracts financial data from business PDFs:
- Tax returns (Form 1120, 1120S, 1065, etc.)
- Profit & Loss statements
- Balance sheets
- Cash flow statements
- Bank statements
- Business valuations
- Accounts receivable/payable aging reports

Uses pdfplumber to extract text and tables, with intelligent pattern matching
and data normalization to produce structured business financial data.
"""

import re
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from decimal import Decimal

try:
    import pdfplumber
except ImportError:
    raise ImportError("pdfplumber required. Install with: pip install pdfplumber")

from biz_models import (
    BusinessClient,
    BusinessFinancials,
    BusinessAccount,
    BusinessDebt,
    IncomeStatementData,
    BalanceSheetData,
    CashFlowData,
    EntityType,
)
from config import DATA_DIR


# ═══════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════

def clean_number(value: str) -> float:
    """
    Convert various number formats to float.
    Handles: "$1,234.56", "(1234)", "1.2M", "1,234", etc.
    """
    if not value or not isinstance(value, str):
        return 0.0

    value = value.strip()
    if not value:
        return 0.0

    # Negative parentheses format
    is_negative = value.startswith("(") and value.endswith(")")
    if is_negative:
        value = value[1:-1]

    # Remove currency symbols
    value = value.replace("$", "").strip()

    # Handle millions/thousands
    if value.upper().endswith("M"):
        value = value[:-1].strip()
        try:
            return (float(value) * 1_000_000) * (-1 if is_negative else 1)
        except ValueError:
            return 0.0

    if value.upper().endswith("K"):
        value = value[:-1].strip()
        try:
            return (float(value) * 1_000) * (-1 if is_negative else 1)
        except ValueError:
            return 0.0

    # Remove commas and convert
    value = value.replace(",", "")
    try:
        result = float(value)
        return result * (-1 if is_negative else 1)
    except ValueError:
        return 0.0


def find_number_in_text(text: str, pattern: str = None) -> float:
    """
    Find first number matching a pattern in text.
    If no pattern, finds first number.
    """
    if not text:
        return 0.0

    if pattern:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_number(match.group(1) if match.groups() else match.group(0))
    else:
        # Find first number
        match = re.search(r"[\$\(]?[\d,\.]+[\)]?", text)
        if match:
            return clean_number(match.group(0))

    return 0.0


def extract_date(text: str) -> Optional[date]:
    """Extract date from text. Handles various formats."""
    if not text:
        return None

    # Try common formats
    patterns = [
        r"(\d{1,2})/(\d{1,2})/(\d{4})",  # MM/DD/YYYY
        r"(\d{1,2})-(\d{1,2})-(\d{4})",  # MM-DD-YYYY
        r"(\d{4})-(\d{1,2})-(\d{1,2})",  # YYYY-MM-DD
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if len(match.groups()) == 3:
                    groups = match.groups()
                    if pattern == patterns[3]:  # Month name format
                        month_map = {
                            "january": 1, "february": 2, "march": 3, "april": 4,
                            "may": 5, "june": 6, "july": 7, "august": 8,
                            "september": 9, "october": 10, "november": 11, "december": 12,
                        }
                        month = month_map.get(groups[0].lower(), 1)
                        day = int(groups[1])
                        year = int(groups[2])
                    elif pattern == patterns[2]:  # YYYY-MM-DD
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    else:  # MM/DD/YYYY or MM-DD-YYYY
                        month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                    return date(year, month, day)
            except (ValueError, IndexError):
                continue

    return None


def extract_ein(text: str) -> Optional[str]:
    """Extract EIN (format: XX-XXXXXXX)."""
    match = re.search(r"(\d{2})-(\d{7})", text)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def detect_document_type(text: str) -> str:
    """
    Detect the type of financial document.
    Returns: "tax_return", "income_statement", "balance_sheet", "cash_flow", "bank_statement", "valuation", "unknown"
    """
    text_lower = text.lower()

    if any(x in text_lower for x in ["form 1120", "form 1120s", "form 1065", "form 1040-es", "tax return"]):
        return "tax_return"
    elif any(x in text_lower for x in ["profit and loss", "income statement", "p&l", "p & l"]):
        return "income_statement"
    elif any(x in text_lower for x in ["balance sheet", "statement of financial position", "assets", "liabilities", "equity"]):
        if "assets" in text_lower and "liabilities" in text_lower:
            return "balance_sheet"
    elif any(x in text_lower for x in ["cash flow", "statement of cash flows", "operating activities", "investing activities"]):
        return "cash_flow"
    elif any(x in text_lower for x in ["bank statement", "account statement", "transaction history"]):
        return "bank_statement"
    elif any(x in text_lower for x in ["valuation", "business value", "enterprise value"]):
        return "valuation"

    return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Business PDF Importer
# ═══════════════════════════════════════════════════════════════════

class BusinessPDFImporter:
    """
    Intelligent parser for business financial PDFs.
    Auto-detects document type and extracts relevant data.
    """

    def __init__(self):
        self.text = ""
        self.tables = []
        self.document_type = ""
        self.metadata = {}

    def parse_pdf(self, filepath: str) -> Dict[str, Any]:
        """
        Main entry point: parse a PDF and return structured data.

        Args:
            filepath: Path to PDF file

        Returns:
            Dictionary with extracted data and metadata
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"PDF not found: {filepath}")

        result = {
            "success": False,
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "document_type": "unknown",
            "business_profile": {},
            "financials": {},
            "accounts": [],
            "debts": [],
            "errors": [],
            "warnings": [],
        }

        try:
            with pdfplumber.open(filepath) as pdf:
                # Extract text and tables
                self.text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                self.tables = []
                for page in pdf.pages:
                    page_tables = page.extract_tables()
                    if page_tables:
                        self.tables.extend(page_tables)

            # Detect document type
            self.document_type = detect_document_type(self.text)
            result["document_type"] = self.document_type

            # Extract business profile
            profile = self.extract_business_profile(self.text)
            if profile:
                result["business_profile"] = profile

            # Route to appropriate parser
            if self.document_type == "income_statement":
                result["financials"] = self.extract_income_statement(self.tables, self.text)
            elif self.document_type == "balance_sheet":
                result["financials"] = self.extract_balance_sheet(self.tables, self.text)
            elif self.document_type == "cash_flow":
                result["financials"] = self.extract_cash_flow(self.tables, self.text)
            elif self.document_type == "tax_return":
                tax_data = self.extract_tax_data(self.text)
                result["financials"] = tax_data
                result["business_profile"].update(tax_data.get("tax_info", {}))
            elif self.document_type == "bank_statement":
                accounts = self.extract_accounts(self.tables)
                result["accounts"] = accounts
            else:
                # Try to extract everything
                result["financials"] = self.extract_income_statement(self.tables, self.text)
                result["business_profile"].update(self.extract_business_profile(self.text))

            # Extract common debt/account info
            debts = self.extract_debt_schedule(self.tables, self.text)
            if debts:
                result["debts"] = debts

            accounts = self.extract_accounts(self.tables)
            if accounts:
                result["accounts"] = accounts

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"PDF parsing error: {str(e)}")

        return result

    def extract_business_profile(self, text: str) -> Dict[str, Any]:
        """
        Extract business information: name, EIN, address, industry, etc.
        """
        profile = {
            "name": "",
            "ein": "",
            "entity_type": "",
            "address": "",
            "phone": "",
        }

        # EIN
        ein = extract_ein(text)
        if ein:
            profile["ein"] = ein

        # Company name (usually near top or after "NAME:" label)
        name_patterns = [
            r"(?:Company Name|Business Name|DBA|Legal Name)[:\s]+([^\n]+)",
            r"^([A-Z][A-Za-z\s&,]+?)\s*(?:EIN|Tax ID|Entity)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                profile["name"] = match.group(1).strip()
                break

        # If still no name, try first line that looks like company name
        if not profile["name"]:
            lines = text.split("\n")
            for line in lines[:20]:
                line = line.strip()
                if len(line) > 5 and line.isupper() and not any(x in line for x in ["FORM", "PAGE", "DATE"]):
                    profile["name"] = line
                    break

        # Address
        address_pattern = r"(?:Address|Location)[:\s]+([^\n]+(?:\n[^\n]+)?)"
        match = re.search(address_pattern, text, re.IGNORECASE)
        if match:
            profile["address"] = match.group(1).strip()

        # Phone
        phone_pattern = r"(?:Phone|Tel)[:\s]*(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"
        match = re.search(phone_pattern, text, re.IGNORECASE)
        if match:
            profile["phone"] = match.group(1).strip()

        return profile

    def extract_income_statement(self, tables: List[List[List]], text: str) -> Dict[str, Any]:
        """
        Extract P&L / Income statement data.
        """
        statement = IncomeStatementData()

        # Try to extract from tables first
        for table in tables:
            for row in table:
                row_text = " ".join(str(cell) for cell in row if cell).lower()

                # Revenue lines
                if "revenue" in row_text or "sales" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.total_revenue = max(statement.total_revenue, clean_number(str(cell)))

                # COGS
                if "cost of goods sold" in row_text or "cogs" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.cogs = max(statement.cogs, clean_number(str(cell)))

                # Operating expenses
                if "operating expense" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.total_operating_expenses = max(statement.total_operating_expenses, clean_number(str(cell)))

                # Net income
                if "net income" in row_text or "net profit" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.net_income = clean_number(str(cell))
                            break

        # Extract from text patterns
        text_lower = text.lower()
        statement.total_revenue = max(
            statement.total_revenue,
            find_number_in_text(text, r"(?:total\s+)?(?:revenue|sales)[:\s]+\$?([\d,\.]+)")
        )
        statement.cogs = max(
            statement.cogs,
            find_number_in_text(text, r"cost of goods sold[:\s]+\$?([\d,\.]+)")
        )
        statement.net_income = find_number_in_text(text, r"net income[:\s]+\$?([\d,\.]+)")

        # Calculate if missing
        if statement.total_revenue and not statement.gross_profit:
            statement.gross_profit = statement.total_revenue - statement.cogs
        if statement.gross_profit and statement.total_revenue:
            statement.gross_profit_margin = statement.gross_profit / statement.total_revenue if statement.total_revenue else 0

        # Extract dates
        dates = re.findall(r"(?:for\s+the\s+(?:year|period)\s+)?(?:ended?|through?)[:\s]*([^\n]+)", text, re.IGNORECASE)
        if dates:
            start_date = extract_date(dates[0])
            end_date = extract_date(dates[-1] if len(dates) > 1 else dates[0])
            if start_date:
                statement.period_start = start_date
            if end_date:
                statement.period_end = end_date

        return {
            "type": "income_statement",
            "data": statement.__dict__,
        }

    def extract_balance_sheet(self, tables: List[List[List]], text: str) -> Dict[str, Any]:
        """
        Extract balance sheet data (Assets, Liabilities, Equity).
        """
        statement = BalanceSheetData()

        for table in tables:
            for row in table:
                row_text = " ".join(str(cell) for cell in row if cell).lower()

                # Assets
                if "total assets" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.total_assets = clean_number(str(cell))
                if "current assets" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.current_assets = clean_number(str(cell))
                if "cash" in row_text and "receivable" not in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.cash_and_equivalents = max(statement.cash_and_equivalents, clean_number(str(cell)))
                if "accounts receivable" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.accounts_receivable = clean_number(str(cell))
                if "inventory" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.inventory = clean_number(str(cell))

                # Fixed assets
                if "property" in row_text and "equipment" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.property_and_equipment = clean_number(str(cell))
                if "accumulated depreciation" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.accumulated_depreciation = clean_number(str(cell))

                # Liabilities
                if "total liabilities" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.total_liabilities = clean_number(str(cell))
                if "current liabilities" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.current_liabilities = clean_number(str(cell))
                if "accounts payable" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.accounts_payable = clean_number(str(cell))
                if "short term debt" in row_text or "current portion" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.short_term_debt = clean_number(str(cell))
                if "long term debt" in row_text and "current" not in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.long_term_debt = clean_number(str(cell))

                # Equity
                if "total" in row_text and "equity" in row_text and "stockholder" not in row_text.lower():
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.total_equity = clean_number(str(cell))
                if "retained earnings" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.retained_earnings = clean_number(str(cell))

        # Calculate ratios
        if statement.current_assets and statement.current_liabilities:
            statement.current_ratio = statement.current_assets / statement.current_liabilities
        if statement.accounts_receivable and statement.current_liabilities:
            statement.quick_ratio = (statement.current_assets - statement.inventory) / statement.current_liabilities
        if statement.total_equity and statement.total_liabilities:
            statement.debt_to_equity = statement.total_liabilities / statement.total_equity

        return {
            "type": "balance_sheet",
            "data": statement.__dict__,
        }

    def extract_cash_flow(self, tables: List[List[List]], text: str) -> Dict[str, Any]:
        """
        Extract cash flow statement data (Operating, Investing, Financing).
        """
        statement = CashFlowData()

        for table in tables:
            for row in table:
                row_text = " ".join(str(cell) for cell in row if cell).lower()

                # Operating activities
                if "operating activities" in row_text or "operating cash" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.operating_cash_flow = clean_number(str(cell))
                if "depreciation" in row_text and "amortization" not in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.depreciation = clean_number(str(cell))
                if "amortization" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.amortization = clean_number(str(cell))

                # Investing activities
                if "investing activities" in row_text or "investing cash" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.investing_cash_flow = clean_number(str(cell))
                if "capital expenditures" in row_text or "capex" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.capital_expenditures = clean_number(str(cell))

                # Financing activities
                if "financing activities" in row_text or "financing cash" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.financing_cash_flow = clean_number(str(cell))
                if "debt" in row_text and ("proceeds" in row_text or "payments" in row_text):
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            if "proceeds" in row_text:
                                statement.debt_proceeds = clean_number(str(cell))
                            else:
                                statement.debt_payments = clean_number(str(cell))

                # Net change
                if "net change" in row_text:
                    for i, cell in enumerate(row):
                        if cell and i > 0:
                            statement.net_change_in_cash = clean_number(str(cell))

        # Extract beginning/ending cash from text
        statement.beginning_cash = find_number_in_text(text, r"(?:cash|beginning balance)[:\s]*\$?([\d,\.]+)")
        statement.ending_cash = find_number_in_text(text, r"(?:ending cash|ending balance)[:\s]*\$?([\d,\.]+)")

        # Extract dates
        dates = re.findall(r"(?:for\s+the\s+(?:year|period)\s+)?(?:ended?)[:\s]*([^\n]+)", text, re.IGNORECASE)
        if dates:
            start_date = extract_date(dates[0])
            end_date = extract_date(dates[-1] if len(dates) > 1 else dates[0])
            if start_date:
                statement.period_start = start_date
            if end_date:
                statement.period_end = end_date

        return {
            "type": "cash_flow",
            "data": statement.__dict__,
        }

    def extract_tax_data(self, text: str) -> Dict[str, Any]:
        """
        Extract tax return data (Form 1120, 1120S, 1065).
        """
        tax_info = {}
        income_data = IncomeStatementData()

        # Detect form type
        if "form 1120s" in text.lower():
            tax_info["form_type"] = "1120S"
            entity_type = "s_corp"
        elif "form 1120" in text.lower():
            tax_info["form_type"] = "1120"
            entity_type = "c_corp"
        elif "form 1065" in text.lower():
            tax_info["form_type"] = "1065"
            entity_type = "partnership"
        elif "form 1040-es" in text.lower():
            tax_info["form_type"] = "1040-ES"
            entity_type = "sole_proprietor"
        else:
            tax_info["form_type"] = "Unknown"
            entity_type = "other"

        tax_info["entity_type"] = entity_type

        # Tax year
        year_match = re.search(r"tax year|for the year ended|20(\d{2})", text, re.IGNORECASE)
        if year_match:
            tax_info["tax_year"] = year_match.group(0)

        # Income lines
        income_data.total_revenue = find_number_in_text(text, r"gross receipts|total receipts[:\s]+\$?([\d,\.]+)")
        income_data.cogs = find_number_in_text(text, r"cost of goods sold[:\s]+\$?([\d,\.]+)")
        income_data.gross_profit = find_number_in_text(text, r"gross profit[:\s]+\$?([\d,\.]+)")

        # Deductions
        deductions = find_number_in_text(text, r"total deductions[:\s]+\$?([\d,\.]+)")
        income_data.total_operating_expenses = deductions

        # Taxable income
        income_data.income_before_tax = find_number_in_text(text, r"taxable income[:\s]+\$?([\d,\.]+)")

        # Income tax
        income_data.income_tax_expense = find_number_in_text(text, r"(?:income\s+)?tax[:\s]+\$?([\d,\.]+)")

        return {
            "type": "tax_return",
            "tax_info": tax_info,
            "data": income_data.__dict__,
        }

    def extract_accounts(self, tables: List[List[List]]) -> List[Dict[str, Any]]:
        """
        Extract bank/investment account information.
        """
        accounts = []

        for table in tables:
            # Check if this looks like an account listing
            table_text = " ".join(str(cell) for cell in table[0] if cell).lower() if table else ""

            if any(x in table_text for x in ["account", "balance", "institution", "type"]):
                for row in table[1:]:  # Skip header
                    if len(row) < 2:
                        continue

                    account = {
                        "account_name": str(row[0]).strip() if row[0] else "",
                        "account_type": "other",
                        "balance": 0.0,
                        "institution": "",
                    }

                    # Try to find balance
                    for cell in row[1:]:
                        if cell:
                            num = clean_number(str(cell))
                            if num > 0:
                                account["balance"] = num
                                break

                    if account["account_name"] and account["balance"]:
                        accounts.append(account)

        return accounts

    def extract_debt_schedule(self, tables: List[List[List]], text: str) -> List[Dict[str, Any]]:
        """
        Extract loan and line of credit information.
        """
        debts = []

        for table in tables:
            # Check if this looks like a debt schedule
            table_text = " ".join(str(cell) for cell in table[0] if cell).lower() if table else ""

            if any(x in table_text for x in ["lender", "loan", "debt", "interest", "payment", "balance"]):
                for row in table[1:]:
                    if len(row) < 2:
                        continue

                    debt = {
                        "lender": str(row[0]).strip() if row[0] else "",
                        "debt_type": "bank_loan",
                        "current_balance": 0.0,
                        "interest_rate": 0.0,
                        "monthly_payment": 0.0,
                    }

                    # Extract numbers from row
                    numbers = []
                    for cell in row[1:]:
                        if cell:
                            num = clean_number(str(cell))
                            if num >= 0:
                                numbers.append(num)

                    # Assign: balance, rate, payment
                    if len(numbers) >= 1:
                        debt["current_balance"] = numbers[0]
                    if len(numbers) >= 2:
                        debt["interest_rate"] = numbers[1] / 100 if numbers[1] > 1 else numbers[1]
                    if len(numbers) >= 3:
                        debt["monthly_payment"] = numbers[2]

                    if debt["lender"] and debt["current_balance"]:
                        debts.append(debt)

        return debts


# ═══════════════════════════════════════════════════════════════════
# Business Data Store
# ═══════════════════════════════════════════════════════════════════

class BusinessDataStore:
    """
    Persist parsed business data to JSON files.
    Similar to ClientStore for individual clients.
    """

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(DATA_DIR, "business")
        self.imports_dir = os.path.join(self.data_dir, "imports")
        self.businesses_file = os.path.join(self.data_dir, "businesses.json")
        self.financials_file = os.path.join(self.data_dir, "financials.json")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.imports_dir, exist_ok=True)

        self._businesses: Dict[str, dict] = {}
        self._financials: Dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load data from JSON files."""
        if os.path.exists(self.businesses_file):
            try:
                with open(self.businesses_file, 'r') as f:
                    data = json.load(f)
                    self._businesses = {b["id"]: b for b in data.get("businesses", [])}
            except Exception as e:
                print(f"Warning: Could not load businesses: {e}")

        if os.path.exists(self.financials_file):
            try:
                with open(self.financials_file, 'r') as f:
                    data = json.load(f)
                    self._financials = {f["id"]: f for f in data.get("financials", [])}
            except Exception as e:
                print(f"Warning: Could not load financials: {e}")

    def _save_businesses(self):
        """Save businesses to JSON."""
        data = {"businesses": list(self._businesses.values())}
        with open(self.businesses_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def _save_financials(self):
        """Save financials to JSON."""
        data = {"financials": list(self._financials.values())}
        with open(self.financials_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def save_import(self, business_id: str, pdf_path: str, parsed_data: Dict[str, Any]) -> str:
        """
        Save parsed PDF data to an import file.
        Returns path to saved import file.
        """
        import_filename = f"{business_id}_{Path(pdf_path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        import_path = os.path.join(self.imports_dir, import_filename)

        with open(import_path, 'w') as f:
            json.dump(parsed_data, f, indent=2, default=str)

        return import_path

    def add_business(self, business: Dict[str, Any]) -> Dict[str, Any]:
        """Add or update a business."""
        self._businesses[business["id"]] = business
        self._save_businesses()
        return business

    def add_financials(self, financials: Dict[str, Any]) -> Dict[str, Any]:
        """Add or update financial data."""
        self._financials[financials["id"]] = financials
        self._save_financials()
        return financials

    def get_business(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a business by ID."""
        return self._businesses.get(business_id)

    def get_all_businesses(self) -> List[Dict[str, Any]]:
        """Get all businesses."""
        return list(self._businesses.values())

    def get_financials_by_business(self, business_id: str) -> List[Dict[str, Any]]:
        """Get all financials for a business."""
        return [f for f in self._financials.values() if f.get("business_id") == business_id]

    def delete_business(self, business_id: str):
        """Delete a business and associated financials."""
        if business_id in self._businesses:
            del self._businesses[business_id]
            self._save_businesses()

        # Delete associated financials
        to_delete = [f_id for f_id, f in self._financials.items() if f.get("business_id") == business_id]
        for f_id in to_delete:
            del self._financials[f_id]
        self._save_financials()


# ═══════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════

def parse_business_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Quick function to parse a business PDF.
    Returns parsed data dictionary.
    """
    parser = BusinessPDFImporter()
    return parser.parse_pdf(pdf_path)


def batch_import_pdfs(pdf_directory: str, business_id: str = None) -> List[Dict[str, Any]]:
    """
    Import all PDFs from a directory.
    Returns list of parsed results.
    """
    results = []
    pdf_dir = Path(pdf_directory)

    for pdf_file in pdf_dir.glob("*.pdf"):
        try:
            result = parse_business_pdf(str(pdf_file))
            results.append(result)
        except Exception as e:
            results.append({
                "success": False,
                "filename": pdf_file.name,
                "error": str(e),
            })

    return results
