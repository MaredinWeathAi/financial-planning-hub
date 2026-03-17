"""
Configuration for the Financial Reconciliation System.
Update these values with your actual credentials and settings.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List

# ─── QuickBooks Online OAuth2 Credentials ───────────────────────────
# Get these from https://developer.intuit.com
QBO_CLIENT_ID = os.getenv("QBO_CLIENT_ID", "your_client_id")
QBO_CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET", "your_client_secret")
QBO_REDIRECT_URI = os.getenv("QBO_REDIRECT_URI", "http://localhost:5000/callback")
QBO_ENVIRONMENT = os.getenv("QBO_ENVIRONMENT", "sandbox")  # "sandbox" or "production"
QBO_REALM_ID = os.getenv("QBO_REALM_ID", "your_company_id")

# ─── Interactive Brokers Flex Query ─────────────────────────────────
# Get these from IBKR Client Portal > Performance & Reports > Flex Queries
IBKR_FLEX_TOKEN = os.getenv("IBKR_FLEX_TOKEN", "your_flex_token")
IBKR_QUERY_ID = os.getenv("IBKR_QUERY_ID", "your_query_id")

# ─── Schwab Developer API (optional, CSV fallback available) ────────
SCHWAB_API_KEY = os.getenv("SCHWAB_API_KEY", "")
SCHWAB_API_SECRET = os.getenv("SCHWAB_API_SECRET", "")

# ─── Plaid (optional unified layer for BofA + others) ──────────────
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.getenv("PLAID_SECRET", "")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")  # sandbox, development, production

# ─── File Paths ─────────────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "./data")
IMPORT_DIR = os.path.join(DATA_DIR, "imports")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# ─── Chart of Accounts Mapping ──────────────────────────────────────
# Map source transaction categories → QBO account names/IDs
# You'll customize this to match YOUR QuickBooks chart of accounts

@dataclass
class AccountMapping:
    """Maps external transaction types to QuickBooks accounts."""

    # Bank of America mappings
    bofa: Dict[str, str] = field(default_factory=lambda: {
        "CHECK": "Checking",
        "DEBIT": "Checking",
        "CREDIT": "Checking",
        "TRANSFER": "Checking",
        "FEE": "Bank Charges & Fees",
        "INTEREST": "Interest Income",
        "ATM": "Checking",
        "WIRE": "Checking",
        "ACH": "Checking",
    })

    # Interactive Brokers mappings
    ibkr: Dict[str, str] = field(default_factory=lambda: {
        "TRADE": "Investment Trading",
        "COMMISSION": "Trading Commissions",
        "DIVIDEND": "Dividend Income",
        "INTEREST": "Interest Income",
        "FEE": "Broker Fees",
        "DEPOSIT": "Investment Account",
        "WITHDRAWAL": "Investment Account",
        "WITHHOLDING_TAX": "Tax Withholding",
        "OTHER_FEE": "Broker Fees",
        "CASH_SETTLING": "Investment Account",
        "OPTION_ASSIGNMENT": "Investment Trading",
        "OPTION_EXERCISE": "Investment Trading",
    })

    # Schwab mappings
    schwab: Dict[str, str] = field(default_factory=lambda: {
        "BUY": "Investment Trading",
        "SELL": "Investment Trading",
        "DIVIDEND": "Dividend Income",
        "INTEREST": "Interest Income",
        "TRANSFER": "Investment Account",
        "FEE": "Broker Fees",
        "JOURNAL": "Investment Account",
        "ADJ": "Investment Adjustments",
        "REINVEST": "Dividend Income",
        "CASH_DIVIDEND": "Dividend Income",
        "QUAL_DIV": "Qualified Dividend Income",
    })

    # QuickBooks existing transaction types (for reconciliation matching)
    qbo_match_fields: List[str] = field(default_factory=lambda: [
        "TxnDate", "Amount", "Description", "DocNumber"
    ])


ACCOUNT_MAPPING = AccountMapping()

# ─── Email / SMTP Configuration ─────────────────────────────────────
# Gmail: use App Passwords (https://myaccount.google.com/apppasswords)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
FROM_NAME = os.getenv("FROM_NAME", "")

# Always CC these addresses on every invoice email (e.g., your CPA)
GLOBAL_CC_EMAILS: List[str] = []
GLOBAL_BCC_EMAILS: List[str] = []

# ─── Your Business Info (appears on invoices) ───────────────────────
BUSINESS_INFO = {
    "name": "Your Name",
    "company": "Your Company LLC",
    "address": "123 Main Street\nMiami, FL 33101",
    "email": FROM_EMAIL,
    "phone": "(305) 555-1234",
    "logo_path": "",                    # Optional: path to logo.png
    "footer": "Thank you for your business.",
}

# ─── Invoice Defaults ───────────────────────────────────────────────
DEFAULT_PAYMENT_TERMS = 30              # Net 30
DEFAULT_INVOICE_PREFIX = "INV"
DEFAULT_TAX_RATE = 0.0                  # Sales tax % (if applicable)

# ─── Reconciliation Rules ───────────────────────────────────────────
# Tolerance for matching amounts (cents)
MATCH_TOLERANCE = 0.01
# Days window for date matching
DATE_MATCH_WINDOW = 3
# Minimum confidence score (0-1) to auto-match
AUTO_MATCH_THRESHOLD = 0.85
