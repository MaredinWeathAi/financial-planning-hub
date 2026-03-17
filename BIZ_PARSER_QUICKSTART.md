# Business PDF Parser - Quick Start

## Installation

```bash
pip install pdfplumber
```

## 5-Minute Quick Start

### 1. Parse a PDF

```python
from biz_pdf_parser import parse_business_pdf

result = parse_business_pdf("tax_return_2023.pdf")
print(result["document_type"])  # Detects: tax_return, income_statement, etc.
print(result["business_profile"])  # {name, ein, address}
print(result["financials"])  # {type, data}
```

### 2. Create Business Objects

```python
from biz_models import BusinessClient, BusinessFinancials, BusinessPlan

# From parsed data
business = BusinessClient(
    name=result["business_profile"]["name"],
    ein=result["business_profile"]["ein"],
)

financials = BusinessFinancials(
    business_id=business.id,
    fiscal_year=2023,
)

plan = BusinessPlan(business=business, financials=[financials])
plan.calculate_metrics()
```

### 3. Access Data

```python
# Income statement data
print(f"Revenue: ${result['financials']['data']['total_revenue']:,.2f}")
print(f"Net Income: ${result['financials']['data']['net_income']:,.2f}")

# Balance sheet ratios
print(f"Current Ratio: {result['financials']['data']['current_ratio']:.2f}")

# Plan summary
print(f"Total Assets: ${plan.total_assets:,.2f}")
print(f"Total Debt: ${plan.total_debt:,.2f}")
```

### 4. Save Data

```python
from biz_pdf_parser import BusinessDataStore

store = BusinessDataStore()

# Save parsed import
import_path = store.save_import(
    business_id=business.id,
    pdf_path="tax_return_2023.pdf",
    parsed_data=result
)

# Save to data store
store.add_business(business.to_dict())
store.add_financials(financials.to_dict())
```

## Common Tasks

### Extract Income Statement

```python
from biz_pdf_parser import BusinessPDFImporter
from biz_models import IncomeStatementData

parser = BusinessPDFImporter()
result = parser.parse_pdf("p_and_l.pdf")

if result["document_type"] == "income_statement":
    data = IncomeStatementData(**result["financials"]["data"])
    print(f"Margin: {data.net_profit_margin:.1%}")
```

### Extract Balance Sheet

```python
from biz_models import BalanceSheetData

if result["document_type"] == "balance_sheet":
    data = BalanceSheetData(**result["financials"]["data"])
    print(f"D/E Ratio: {data.debt_to_equity:.2f}")
    print(f"Current Ratio: {data.current_ratio:.2f}")
```

### Extract Tax Return Data

```python
if result["document_type"] == "tax_return":
    tax_info = result["financials"]["tax_info"]
    print(f"Form: {tax_info['form_type']}")  # 1120, 1120S, 1065
    print(f"Entity: {tax_info['entity_type']}")
```

### Create Business with Accounts & Debt

```python
from biz_models import BusinessAccount, BusinessDebt
from datetime import date

# Account
account = BusinessAccount(
    business_id=business.id,
    account_name="Operating Account",
    account_type="business_checking",
    balance=250000.00,
)

# Debt
debt = BusinessDebt(
    business_id=business.id,
    lender="First National Bank",
    current_balance=200000.00,
    interest_rate=0.06,
    monthly_payment=5000.00,
    maturity_date=date(2028, 3, 15),
)

plan.accounts = [account]
plan.debts = [debt]
plan.calculate_metrics()
```

### Batch Process Multiple PDFs

```python
from biz_pdf_parser import batch_import_pdfs

results = batch_import_pdfs("/path/to/pdfs")

for result in results:
    if result["success"]:
        print(f"✓ {result['filename']} - {result['document_type']}")
    else:
        print(f"✗ {result['filename']} - {result['error']}")
```

## Data Models Summary

### BusinessClient
Company information: name, EIN, entity type, address, contacts, industry

### IncomeStatementData
Revenue, COGS, expenses, net income, margins

### BalanceSheetData
Assets, liabilities, equity, current/debt ratios

### CashFlowData
Operating/investing/financing cash flows

### BusinessAccount
Bank/investment accounts with balances and interest rates

### BusinessDebt
Loans and lines of credit with terms and payments

### BusinessPlan
Complete profile: client + financials + accounts + debts + goals

## Supported Document Types

- `tax_return` - Forms 1120, 1120S, 1065, 1040-ES
- `income_statement` - P&L statements
- `balance_sheet` - Balance sheets
- `cash_flow` - Cash flow statements
- `bank_statement` - Bank transaction statements
- `valuation` - Business valuation reports
- `unknown` - Unrecognized format

## Key Features

✓ Auto-detect document type
✓ Extract company profile (name, EIN, address)
✓ Parse financial statements (P&L, BS, CF)
✓ Extract tax return data
✓ Identify bank accounts and balances
✓ Find loan details and payment schedules
✓ Calculate financial ratios
✓ Persist to JSON data store
✓ Handle multiple number formats ($1.5M, $500K, etc.)
✓ Recognize common date formats
✓ Error handling and validation

## File Locations

- `biz_models.py` - Data models
- `biz_pdf_parser.py` - PDF extraction engine
- `BUSINESS_PDF_PARSER_GUIDE.md` - Full documentation
- `test_biz_parser.py` - Test examples
- `./data/business/businesses.json` - Business data store
- `./data/business/financials.json` - Financial statements
- `./data/business/imports/` - Parsed PDF imports

## Common Errors & Solutions

| Error | Solution |
|-------|----------|
| `ImportError: No module named 'pdfplumber'` | Run: `pip install pdfplumber` |
| `FileNotFoundError: PDF not found` | Check file path exists |
| `Empty financials extracted` | PDF may be image-based (needs OCR) |
| `Numbers not recognized` | Check number format (supports: 1234, $1,234.56, (1234), 1.5M) |
| `No tables found` | PDF may use text boxes instead of tables |

## Testing

Run the test suite:

```bash
python test_biz_parser.py
```

Expected output:
- Data model tests (creating businesses, statements, etc.)
- PDF parser tests (extracting from sample PDFs)
- Data store tests (saving/retrieving data)

## Next Steps

1. Parse business PDFs: `parse_business_pdf("file.pdf")`
2. Create BusinessPlan objects with extracted data
3. Store in BusinessDataStore
4. Integrate with financial planning dashboard
5. Use for advisor reporting and analysis

## Example: Complete Workflow

```python
from biz_pdf_parser import parse_business_pdf, BusinessDataStore
from biz_models import BusinessClient, BusinessFinancials, BusinessPlan

# 1. Parse PDF
result = parse_business_pdf("1120_2023.pdf")

# 2. Create objects from parsed data
business = BusinessClient(
    name=result["business_profile"]["name"],
    ein=result["business_profile"]["ein"],
)

financials = BusinessFinancials(
    business_id=business.id,
    fiscal_year=2023,
)

# 3. Build plan
plan = BusinessPlan(business=business, financials=[financials])
plan.calculate_metrics()

# 4. Save
store = BusinessDataStore()
store.add_business(business.to_dict())
store.save_import(business.id, "1120_2023.pdf", result)

# 5. Use
print(f"Business: {plan.business.name}")
print(f"Revenue: ${plan.annual_revenue:,.0f}")
print(f"Net Income: ${plan.annual_net_income:,.0f}")
```

---

For complete documentation, see: `BUSINESS_PDF_PARSER_GUIDE.md`
