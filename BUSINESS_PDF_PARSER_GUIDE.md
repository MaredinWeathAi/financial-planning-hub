# Business PDF Parser Guide

## Overview

The Business PDF Parser system provides intelligent extraction of financial data from PDF documents into structured Python objects. It automatically detects document types (tax returns, P&L statements, balance sheets, etc.) and extracts relevant financial metrics.

## Components

### 1. `biz_models.py` - Data Models

Comprehensive dataclasses representing business financial entities:

#### Business Profile
- **BusinessClient**: Company information (name, EIN, entity type, address, contacts)

#### Financial Statements
- **IncomeStatementData**: P&L statement (revenue, expenses, net income)
- **BalanceSheetData**: Assets, liabilities, equity with key ratios
- **CashFlowData**: Operating, investing, and financing activities
- **BusinessFinancials**: Container for all three statement types

#### Accounts & Debt
- **BusinessAccount**: Bank and investment accounts with balances
- **BusinessDebt**: Loans and lines of credit with terms and rates

#### Planning
- **BusinessGoal**: Business objectives and targets
- **BusinessPlan**: Complete profile with all financial data integrated

### 2. `biz_pdf_parser.py` - PDF Extraction

#### BusinessPDFImporter Class

Main entry point for PDF parsing:

```python
from biz_pdf_parser import BusinessPDFImporter

parser = BusinessPDFImporter()
result = parser.parse_pdf("path/to/financial_statement.pdf")
```

**Supported Document Types:**
- Tax returns (Form 1120, 1120S, 1065)
- Profit & Loss statements
- Balance sheets
- Cash flow statements
- Bank statements
- Business valuations

**Key Methods:**

- `parse_pdf(filepath)` - Main entry point, auto-detects type and extracts data
- `extract_business_profile(text)` - Company name, EIN, address, industry
- `extract_income_statement(tables, text)` - Revenue, COGS, expenses, net income
- `extract_balance_sheet(tables, text)` - Assets, liabilities, equity
- `extract_cash_flow(tables, text)` - Cash activities
- `extract_tax_data(text)` - Tax return specific data
- `extract_accounts(tables)` - Bank and investment accounts
- `extract_debt_schedule(tables, text)` - Loans and credit lines

#### BusinessDataStore Class

Persists parsed data to JSON:

```python
from biz_pdf_parser import BusinessDataStore

store = BusinessDataStore()
store.add_business(business_dict)
store.add_financials(financials_dict)

# Retrieve
business = store.get_business("biz_xyz")
financials = store.get_financials_by_business("biz_xyz")
```

## Usage Examples

### Basic PDF Import

```python
from biz_pdf_parser import parse_business_pdf
from biz_models import BusinessClient, BusinessPlan

# Parse a PDF
result = parse_business_pdf("statements.pdf")

if result["success"]:
    profile_data = result["business_profile"]
    financials_data = result["financials"]
    accounts_data = result["accounts"]
    debts_data = result["debts"]

    # Create business object
    business = BusinessClient(
        name=profile_data.get("name", "Unknown"),
        ein=profile_data.get("ein", ""),
        # ... map other fields
    )
```

### Creating Business Plan from Parsed Data

```python
from biz_pdf_parser import parse_business_pdf
from biz_models import (
    BusinessClient,
    BusinessFinancials,
    BusinessAccount,
    BusinessDebt,
    BusinessPlan,
    IncomeStatementData,
)

# Parse PDF
result = parse_business_pdf("1120_tax_return.pdf")

# Create business
business = BusinessClient(
    name=result["business_profile"]["name"],
    ein=result["business_profile"]["ein"],
)

# Create financials
financials = BusinessFinancials(
    business_id=business.id,
    fiscal_year=2023,
    income_statement=IncomeStatementData(**result["financials"]["data"])
)

# Create accounts and debts from parsed data
accounts = [
    BusinessAccount(
        business_id=business.id,
        **account_data
    )
    for account_data in result.get("accounts", [])
]

debts = [
    BusinessDebt(
        business_id=business.id,
        **debt_data
    )
    for debt_data in result.get("debts", [])
]

# Create comprehensive plan
plan = BusinessPlan(
    business=business,
    financials=[financials],
    accounts=accounts,
    debts=debts,
)

plan.calculate_metrics()
```

### Working with Income Statements

```python
from biz_models import IncomeStatementData
from datetime import date

income = IncomeStatementData(
    period_start=date(2023, 1, 1),
    period_end=date(2023, 12, 31),
    total_revenue=2500000.00,
    cogs=750000.00,
    gross_profit=1750000.00,
    salaries_and_wages=600000.00,
    marketing=180000.00,
    net_income=589000.00,
)

# Calculate margins
income.gross_profit_margin = income.gross_profit / income.total_revenue
income.net_profit_margin = income.net_income / income.total_revenue

print(f"Net Margin: {income.net_profit_margin:.1%}")
```

### Working with Balance Sheets

```python
from biz_models import BalanceSheetData
from datetime import date

balance = BalanceSheetData(
    date=date(2023, 12, 31),
    total_assets=1200000.00,
    cash_and_equivalents=250000.00,
    current_assets=480000.00,
    current_liabilities=400000.00,
    total_liabilities=400000.00,
    total_equity=800000.00,
)

# Calculate key ratios
balance.current_ratio = balance.current_assets / balance.current_liabilities
balance.debt_to_equity = balance.total_liabilities / balance.total_equity

print(f"Current Ratio: {balance.current_ratio:.2f}")  # Liquidity
print(f"D/E Ratio: {balance.debt_to_equity:.2f}")     # Leverage
```

### Batch Processing PDFs

```python
from biz_pdf_parser import batch_import_pdfs, BusinessDataStore

# Import all PDFs from directory
results = batch_import_pdfs("/path/to/pdf/folder")

store = BusinessDataStore()

for result in results:
    if result["success"]:
        # Save to data store
        store.save_import(
            result["business_profile"].get("name", "unknown"),
            result["filepath"],
            result
        )
        print(f"✓ {result['filename']}")
    else:
        print(f"✗ {result['filename']}: {result['error']}")
```

### Working with Debt

```python
from biz_models import BusinessDebt
from datetime import date

loan = BusinessDebt(
    business_id="biz_123",
    lender="First National Bank",
    debt_type="term_loan",
    original_amount=300000.00,
    current_balance=200000.00,
    interest_rate=0.06,  # 6%
    term_months=60,
    remaining_term_months=36,
    monthly_payment=5000.00,
    origination_date=date(2021, 3, 15),
    maturity_date=date(2026, 3, 15),
)

# Calculate annual interest expense
annual_interest = loan.interest_expense_annual
print(f"Annual Interest: ${annual_interest:,.2f}")

# Check time to maturity
years_to_maturity = loan.years_to_maturity
print(f"Years to Maturity: {years_to_maturity:.1f}")
```

### Managing Business Accounts

```python
from biz_models import BusinessAccount
from datetime import date

# Operating account
operating = BusinessAccount(
    business_id="biz_123",
    account_name="Operating Account",
    account_type="business_checking",
    institution="First National Bank",
    account_number="****5678",
    balance=250000.00,
    is_primary=True,
)

# Savings account
savings = BusinessAccount(
    business_id="biz_123",
    account_name="Savings Account",
    account_type="business_savings",
    institution="First National Bank",
    account_number="****9012",
    balance=150000.00,
    interest_rate=0.045,  # 4.5% APY
)

# Investment account
investments = BusinessAccount(
    business_id="biz_123",
    account_name="Investment Account",
    account_type="investment",
    institution="Schwab",
    account_number="****1234",
    balance=500000.00,
)

accounts = [operating, savings, investments]
total_liquid = sum(a.balance for a in accounts if a.account_type != "investment")
```

## Data Store Operations

### Initialize Store

```python
from biz_pdf_parser import BusinessDataStore

store = BusinessDataStore()
# Or specify custom data directory:
# store = BusinessDataStore("/custom/data/path")
```

### Add and Retrieve Data

```python
# Add business
business_dict = {
    "id": "biz_001",
    "name": "TechStartup Inc.",
    "ein": "12-3456789",
    "entity_type": "s_corp",
}
store.add_business(business_dict)

# Retrieve single business
biz = store.get_business("biz_001")

# Get all businesses
all_biz = store.get_all_businesses()

# Get financials for specific business
financials = store.get_financials_by_business("biz_001")
```

### Save PDF Imports

```python
# Save parsed PDF data
import_path = store.save_import(
    business_id="biz_001",
    pdf_path="/path/to/statement.pdf",
    parsed_data=result
)
print(f"Import saved to: {import_path}")
```

## Data Extraction Capabilities

### Number Formats Supported

The parser handles various number formats:
- Standard: `1234.56` → 1234.56
- Currency: `$1,234.56` → 1234.56
- Negative: `(1234.56)` → -1234.56
- Millions: `$1.5M` → 1500000.00
- Thousands: `$500K` → 500000.00

### Date Recognition

Automatically recognizes dates in formats:
- `MM/DD/YYYY`: 12/31/2023
- `MM-DD-YYYY`: 12-31-2023
- `YYYY-MM-DD`: 2023-12-31
- `Month DD, YYYY`: December 31, 2023

### Document Type Detection

Automatically identifies:
- Tax returns (Form 1120, 1120S, 1065)
- Income statements / P&L
- Balance sheets
- Cash flow statements
- Bank statements
- Business valuations

## Field Mapping Reference

### Income Statement Fields

- `total_revenue` - Total sales/revenue
- `product_revenue`, `service_revenue` - Revenue by type
- `cogs` - Cost of goods sold
- `gross_profit` - Revenue minus COGS
- `total_operating_expenses` - Sum of all operating expenses
- `salaries_and_wages` - Employee compensation
- `depreciation`, `amortization` - Non-cash charges
- `operating_income` - EBIT
- `interest_expense` - Interest on debt
- `income_before_tax` - Taxable income
- `income_tax_expense` - Taxes paid
- `net_income` - Bottom line profit
- Profitability ratios: `gross_profit_margin`, `operating_margin`, `net_profit_margin`

### Balance Sheet Fields

Assets:
- `cash_and_equivalents` - Cash, money market
- `accounts_receivable` - Amounts owed by customers
- `inventory` - Finished goods, WIP, raw materials
- `property_and_equipment` - Fixed assets (gross)
- `accumulated_depreciation` - Cumulative depreciation
- `intangible_assets` - Goodwill, patents, trademarks

Liabilities:
- `accounts_payable` - Amounts owed to suppliers
- `short_term_debt` - Debt due within 1 year
- `long_term_debt` - Debt due after 1 year
- `accrued_expenses` - Expenses incurred but not paid

Equity:
- `common_stock` - Paid-in capital
- `retained_earnings` - Accumulated profits
- `paid_in_capital` - Above par value stock sales

Key Ratios:
- `current_ratio` - Short-term liquidity (Current Assets / Current Liabilities)
- `quick_ratio` - Acid test (excludes inventory)
- `debt_to_equity` - Leverage ratio

### Cash Flow Fields

Operating Activities:
- `net_income` - Starting point
- `depreciation`, `amortization` - Add back non-cash items
- `changes_in_working_capital` - Changes in current assets/liabilities
- `operating_cash_flow` - Cash from operations

Investing Activities:
- `capital_expenditures` - Purchases of fixed assets
- `investing_cash_flow` - Cash from investing

Financing Activities:
- `debt_proceeds`, `debt_payments` - Borrowing and repayment
- `equity_proceeds` - Stock sales
- `dividend_payments`, `owner_distributions` - Payouts
- `financing_cash_flow` - Cash from financing

## Error Handling

```python
from biz_pdf_parser import parse_business_pdf

result = parse_business_pdf("document.pdf")

if not result["success"]:
    print(f"Errors: {result['errors']}")
    for error in result["errors"]:
        print(f"  - {error}")

if result["warnings"]:
    for warning in result["warnings"]:
        print(f"Warning: {warning}")
```

## Best Practices

1. **Always validate extracted data**: Numbers may need verification
2. **Check document_type**: Ensure correct detection
3. **Handle missing fields**: PDFs may not contain all information
4. **Use error checking**: Review errors and warnings
5. **Persist regularly**: Save to data store frequently
6. **Version control**: Track PDF sources and import dates
7. **Audit trail**: Keep records of what was imported and when

## Troubleshooting

### PDF Not Extracting Tables

Some PDFs may have images instead of searchable text. Consider:
- Converting with OCR first
- Manually entering key numbers
- Using different PDF extraction tool

### Numbers Not Recognized

If numbers aren't being extracted:
- Check format (supports USD, percentages, K/M suffixes)
- Try copying directly from PDF to verify format
- May need manual override

### Entity Type Not Detected

If business entity type isn't detected:
- Look for "Form 1120", "1120S", or "1065" text
- May need to be entered manually
- Check extracted text for entity type clues

## File Locations

- **Models**: `/mnt/Financial Planning/biz_models.py`
- **Parser**: `/mnt/Financial Planning/biz_pdf_parser.py`
- **Data Store**: `./data/business/businesses.json`
- **Financials**: `./data/business/financials.json`
- **Imports**: `./data/business/imports/`

## Integration with Individual Client System

The business PDF parser mirrors the individual client system:
- Same JSON-based persistence as `clients.py`
- Similar dataclass structure as individual models
- Compatible with existing reconciliation pipeline
- Can be integrated with invoice generation system

## Next Steps

1. Process business PDFs through parser
2. Review extracted data for accuracy
3. Create BusinessPlan objects
4. Integrate with financial planning module
5. Use for advisor dashboards and reporting
