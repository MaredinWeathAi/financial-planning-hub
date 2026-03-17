#!/usr/bin/env python3
"""
Test script for the Business PDF Parser.
Demonstrates usage and data model capabilities.
"""

import json
from datetime import date, datetime
from pathlib import Path

from biz_models import (
    BusinessClient,
    BusinessFinancials,
    BusinessAccount,
    BusinessDebt,
    IncomeStatementData,
    BalanceSheetData,
    CashFlowData,
    BusinessPlan,
    EntityType,
)
from biz_pdf_parser import BusinessPDFImporter, BusinessDataStore, parse_business_pdf


def test_models():
    """Test data models."""
    print("=" * 70)
    print("TESTING DATA MODELS")
    print("=" * 70)

    # Create a business client
    business = BusinessClient(
        name="TechStartup Inc.",
        ein="12-3456789",
        entity_type="s_corp",
        industry="Software Development",
        description="SaaS platform for small businesses",
        primary_contact_name="Sarah Johnson",
        primary_contact_email="sarah@techstartup.com",
        primary_contact_phone="(305) 555-1234",
        address_line1="123 Innovation Drive",
        city="Miami",
        state="FL",
        zip_code="33101",
        years_in_business=5,
        number_of_employees=12,
        annual_revenue=2500000.00,
    )
    print(f"✓ Created business: {business.name} ({business.id})")
    print(f"  EIN: {business.ein}, Entity: {business.entity_type}")
    print(f"  Address: {business.full_address}\n")

    # Create financial statements
    income = IncomeStatementData(
        period_start=date(2023, 1, 1),
        period_end=date(2023, 12, 31),
        total_revenue=2500000.00,
        cogs=750000.00,
        gross_profit=1750000.00,
        gross_profit_margin=0.70,
        salaries_and_wages=600000.00,
        rent=120000.00,
        utilities=36000.00,
        marketing=180000.00,
        total_operating_expenses=950000.00,
        operating_income=800000.00,
        interest_expense=25000.00,
        income_before_tax=775000.00,
        income_tax_expense=186000.00,
        net_income=589000.00,
        net_profit_margin=0.236,
    )
    print(f"✓ Income Statement (2023):")
    print(f"  Revenue: ${income.total_revenue:,.2f}")
    print(f"  Net Income: ${income.net_income:,.2f}")
    print(f"  Net Margin: {income.net_profit_margin:.1%}\n")

    balance = BalanceSheetData(
        date=date(2023, 12, 31),
        total_assets=1200000.00,
        cash_and_equivalents=250000.00,
        accounts_receivable=180000.00,
        inventory=50000.00,
        property_and_equipment=500000.00,
        accumulated_depreciation=100000.00,
        total_liabilities=400000.00,
        accounts_payable=150000.00,
        short_term_debt=50000.00,
        long_term_debt=200000.00,
        total_equity=800000.00,
    )
    balance.current_ratio = balance.cash_and_equivalents / (balance.accounts_payable + balance.short_term_debt)
    balance.debt_to_equity = balance.total_liabilities / balance.total_equity
    print(f"✓ Balance Sheet (12/31/2023):")
    print(f"  Total Assets: ${balance.total_assets:,.2f}")
    print(f"  Total Liabilities: ${balance.total_liabilities:,.2f}")
    print(f"  Total Equity: ${balance.total_equity:,.2f}")
    print(f"  Current Ratio: {balance.current_ratio:.2f}")
    print(f"  Debt-to-Equity: {balance.debt_to_equity:.2f}\n")

    cash_flow = CashFlowData(
        period_start=date(2023, 1, 1),
        period_end=date(2023, 12, 31),
        net_income=589000.00,
        depreciation=50000.00,
        accounts_receivable_change=-30000.00,
        inventory_change=-10000.00,
        accounts_payable_change=20000.00,
        operating_cash_flow=619000.00,
        capital_expenditures=-150000.00,
        investing_cash_flow=-150000.00,
        debt_payments=-75000.00,
        financing_cash_flow=-75000.00,
        net_change_in_cash=394000.00,
        beginning_cash=100000.00,
        ending_cash=494000.00,
    )
    print(f"✓ Cash Flow (2023):")
    print(f"  Operating CF: ${cash_flow.operating_cash_flow:,.2f}")
    print(f"  Investing CF: ${cash_flow.investing_cash_flow:,.2f}")
    print(f"  Financing CF: ${cash_flow.financing_cash_flow:,.2f}")
    print(f"  Net Change: ${cash_flow.net_change_in_cash:,.2f}\n")

    # Create financials container
    financials = BusinessFinancials(
        business_id=business.id,
        fiscal_year=2023,
        income_statement=income,
        balance_sheet=balance,
        cash_flow=cash_flow,
        source_document="Form 1120-S 2023 Tax Return",
    )
    print(f"✓ Financials container: {financials.id}\n")

    # Create business accounts
    account1 = BusinessAccount(
        business_id=business.id,
        account_name="Operating Account",
        account_type="business_checking",
        institution="First National Bank",
        account_number="****5678",
        balance=250000.00,
        is_primary=True,
    )

    account2 = BusinessAccount(
        business_id=business.id,
        account_name="Savings Account",
        account_type="business_savings",
        institution="First National Bank",
        account_number="****9012",
        balance=150000.00,
        interest_rate=0.045,
    )
    print(f"✓ Created accounts:")
    print(f"  {account1.account_name}: ${account1.balance:,.2f}")
    print(f"  {account2.account_name}: ${account2.balance:,.2f}\n")

    # Create debt
    debt = BusinessDebt(
        business_id=business.id,
        lender="Commercial Bank",
        debt_type="term_loan",
        description="Equipment and working capital loan",
        original_amount=300000.00,
        current_balance=200000.00,
        interest_rate=0.06,
        term_months=60,
        remaining_term_months=36,
        monthly_payment=5000.00,
    )
    print(f"✓ Created debt:")
    print(f"  Lender: {debt.lender}")
    print(f"  Current Balance: ${debt.current_balance:,.2f}")
    print(f"  Rate: {debt.interest_rate:.1%}")
    print(f"  Monthly Payment: ${debt.monthly_payment:,.2f}\n")

    # Create comprehensive business plan
    plan = BusinessPlan(
        business=business,
        financials=[financials],
        accounts=[account1, account2],
        debts=[debt],
    )
    plan.calculate_metrics()
    print(f"✓ Business Plan created:")
    print(f"  Total Assets: ${plan.total_assets:,.2f}")
    print(f"  Total Debt: ${plan.total_debt:,.2f}")
    print(f"  Annual Revenue: ${plan.annual_revenue:,.2f}")
    print(f"  Annual Net Income: ${plan.annual_net_income:,.2f}\n")

    # Test serialization
    plan_dict = plan.to_dict()
    plan_json = json.dumps(plan_dict, indent=2, default=str)
    print(f"✓ Plan serialized to JSON ({len(plan_json)} chars)\n")

    return plan


def test_pdf_parser():
    """Test PDF parser with sample PDFs."""
    print("=" * 70)
    print("TESTING PDF PARSER")
    print("=" * 70)

    pdf_dir = Path("/sessions/busy-determined-volta/mnt/Financial Planning/Client PDF Reports MGP")
    pdfs = list(pdf_dir.glob("*.pdf"))

    if not pdfs:
        print("⚠ No PDF files found in Client PDF Reports MGP folder\n")
        return

    # Test with first PDF
    pdf_file = pdfs[0]
    print(f"\nParsing: {pdf_file.name}")
    print("-" * 70)

    try:
        parser = BusinessPDFImporter()
        result = parser.parse_pdf(str(pdf_file))

        print(f"✓ Parse successful: {result['success']}")
        print(f"  Document type: {result['document_type']}")
        print(f"  Business profile: {result['business_profile']}")

        if result["financials"]:
            print(f"  Financials extracted: {result['financials'].get('type', 'unknown')}")

        if result["accounts"]:
            print(f"  Accounts found: {len(result['accounts'])}")

        if result["debts"]:
            print(f"  Debts found: {len(result['debts'])}")

        if result["errors"]:
            print(f"  Errors: {result['errors']}")

        # Save to data store
        store = BusinessDataStore()
        import_path = store.save_import("test_business", str(pdf_file), result)
        print(f"  Import saved: {import_path}\n")

    except Exception as e:
        print(f"✗ Parse failed: {e}\n")


def test_data_store():
    """Test BusinessDataStore functionality."""
    print("=" * 70)
    print("TESTING DATA STORE")
    print("=" * 70)

    store = BusinessDataStore()

    # Create sample business
    business = {
        "id": "biz_test001",
        "name": "Example Business LLC",
        "ein": "12-3456789",
        "entity_type": "llc",
        "industry": "Services",
    }

    store.add_business(business)
    print(f"✓ Added business: {business['name']}")

    retrieved = store.get_business("biz_test001")
    print(f"✓ Retrieved business: {retrieved['name']}\n")

    all_businesses = store.get_all_businesses()
    print(f"✓ Total businesses in store: {len(all_businesses)}\n")


if __name__ == "__main__":
    print("\n")
    test_models()
    test_pdf_parser()
    test_data_store()
    print("=" * 70)
    print("ALL TESTS COMPLETE")
    print("=" * 70)
    print("\n")
