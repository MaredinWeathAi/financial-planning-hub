"""
Invoice Engine.

Orchestrates the full invoice lifecycle:
  1. Calculate fees per client per month using their fee schedule
  2. Optionally add passthrough fees from reconciled IBKR/Schwab data
  3. Generate PDF invoices
  4. Send via email
  5. Track status

Usage:
    engine = InvoiceEngine()

    # Generate for all clients for January 2026
    invoices = engine.generate_monthly(2026, 1)

    # Generate for a specific client
    invoice = engine.generate_for_client(client_id, 2026, 1)

    # Send all draft/finalized invoices
    engine.send_all()

    # Or the full pipeline in one call
    engine.run_monthly_billing(2026, 1, send=True)
"""

import calendar
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict

from invoice_models import (
    Client, ClientStore, Invoice, InvoiceLineItem, InvoiceStatus,
    InvoiceStore, FeeScheduleItem, FeeType
)
from invoice_pdf import InvoicePDFGenerator
from invoice_email import InvoiceEmailSender
from models import UnifiedTransaction, TransactionSource, TransactionType
from config import DATA_DIR, PROCESSED_DIR


# ─── Your Company Defaults (customize these) ────────────────────
COMPANY_NAME = os.getenv("COMPANY_NAME", "Your Company Name")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "123 Main St\nSuite 100\nMiami, FL 33101")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "billing@yourcompany.com")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "(305) 555-0100")
COMPANY_LOGO = os.getenv("COMPANY_LOGO", "")
INVOICE_PREFIX = os.getenv("INVOICE_PREFIX", "INV")
DEFAULT_PAYMENT_TERMS = int(os.getenv("DEFAULT_PAYMENT_TERMS", "30"))
DEFAULT_TAX_RATE = float(os.getenv("DEFAULT_TAX_RATE", "0"))
INVOICE_FOOTER = os.getenv("INVOICE_FOOTER", "Thank you for your business.")


class InvoiceEngine:
    """
    Full invoice lifecycle manager.
    """

    def __init__(self):
        self.client_store = ClientStore()
        self.invoice_store = InvoiceStore()
        self.pdf_generator = InvoicePDFGenerator()
        self.email_sender = InvoiceEmailSender()

    # ─── Monthly Billing Pipeline ────────────────────────────────

    def run_monthly_billing(
        self,
        year: int,
        month: int,
        client_ids: List[str] = None,
        send: bool = False,
        dry_run: bool = False,
        cc: List[str] = None,
    ) -> List[Invoice]:
        """
        Full monthly billing pipeline:
        1. Generate invoices for all (or specified) clients
        2. Create PDFs
        3. Optionally send emails

        Returns list of generated invoices.
        """
        month_name = calendar.month_name[month]
        print(f"\n{'='*60}")
        print(f"  MONTHLY BILLING — {month_name} {year}")
        print(f"{'='*60}\n")

        # Generate invoices
        invoices = self.generate_monthly(year, month, client_ids)

        if not invoices:
            print("No invoices generated.")
            return []

        # Summary
        total_amount = sum(inv.total for inv in invoices)
        print(f"\n  Generated: {len(invoices)} invoices")
        print(f"  Total billing: ${total_amount:,.2f}\n")

        # Send
        if send:
            print("Sending invoices...\n")
            results = self.email_sender.send_batch(
                invoices, cc=cc, dry_run=dry_run
            )
            print(f"\n  Email results: {results}")

            # Save updated statuses
            for inv in invoices:
                self.invoice_store.save(inv)

        return invoices

    def generate_monthly(
        self,
        year: int,
        month: int,
        client_ids: List[str] = None,
    ) -> List[Invoice]:
        """Generate invoices for all active clients for a given month."""
        clients = self.client_store.list_all(active_only=True)

        if client_ids:
            clients = [c for c in clients if c.id in client_ids]

        invoices = []
        for client in clients:
            try:
                inv = self.generate_for_client(client.id, year, month)
                if inv and inv.total > 0:
                    invoices.append(inv)
                elif inv:
                    print(f"  [{client.name}] Skipping — $0 total")
            except Exception as e:
                print(f"  [{client.name}] ERROR: {e}")

        return invoices

    def generate_for_client(
        self,
        client_id: str,
        year: int,
        month: int,
        extra_line_items: List[InvoiceLineItem] = None,
    ) -> Optional[Invoice]:
        """
        Generate a single invoice for a client for a specific month.
        """
        client = self.client_store.get(client_id)
        if not client:
            print(f"  Client not found: {client_id}")
            return None

        print(f"  [{client.name}] Generating invoice...")

        # Period
        month_name = calendar.month_name[month]
        _, last_day = calendar.monthrange(year, month)
        period_start = date(year, month, 1)
        period_end = date(year, month, last_day)
        period_label = f"{month_name} {year}"

        # Invoice number
        invoice_number = self.invoice_store.get_next_invoice_number(INVOICE_PREFIX)

        # Issue and due dates
        issue_date = date.today()
        due_date = issue_date + timedelta(days=client.payment_terms or DEFAULT_PAYMENT_TERMS)

        # Calculate fees from schedule
        line_items = self._calculate_fees(client, year, month)

        # Add any passthrough fees from reconciled transactions
        passthrough_items = self._get_passthrough_fees(client, year, month)
        line_items.extend(passthrough_items)

        # Add any extra manual line items
        if extra_line_items:
            line_items.extend(extra_line_items)

        # Build invoice
        invoice = Invoice(
            invoice_number=invoice_number,
            client_id=client.id,
            client_name=client.name,
            client_email=client.email,
            client_address=client.full_address,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            period_label=period_label,
            company_name=COMPANY_NAME,
            company_address=COMPANY_ADDRESS,
            company_email=COMPANY_EMAIL,
            company_phone=COMPANY_PHONE,
            company_logo_path=COMPANY_LOGO,
            line_items=line_items,
            issue_date=issue_date.isoformat(),
            due_date=due_date.isoformat(),
            payment_terms=client.payment_terms or DEFAULT_PAYMENT_TERMS,
            tax_rate=DEFAULT_TAX_RATE,
            status=InvoiceStatus.DRAFT,
            footer_text=INVOICE_FOOTER,
        )

        invoice.calculate_totals()

        # Generate PDF
        pdf_path = self.pdf_generator.generate(invoice)
        invoice.pdf_path = pdf_path

        # Finalize
        invoice.status = InvoiceStatus.FINALIZED

        # Save
        self.invoice_store.save(invoice)

        print(f"    #{invoice_number} — ${invoice.total:,.2f} — {len(line_items)} line items")
        return invoice

    # ─── Fee Calculation ─────────────────────────────────────────

    def _calculate_fees(
        self,
        client: Client,
        year: int,
        month: int,
    ) -> List[InvoiceLineItem]:
        """Calculate fees from the client's fee schedule."""
        items = []

        # Load client's trading activity for the month (if available)
        trade_count = self._get_trade_count(client, year, month)

        for fee in client.fee_schedule:
            if not fee.active:
                continue

            # Determine basis
            if fee.applies_to == "aum":
                basis = client.aum
                # Monthly: divide annual rate by 12
                monthly_rate = fee.rate / 12.0
                amount = basis * (monthly_rate / 100.0)
            elif fee.applies_to == "trades":
                basis = 0
                amount = fee.calculate(0, trade_count)
            elif fee.applies_to == "gains":
                basis = self._get_monthly_gains(client, year, month)
                amount = fee.calculate(basis)
            else:  # fixed
                basis = 0
                amount = fee.rate

            # Apply min/max
            if fee.min_fee > 0:
                amount = max(amount, fee.min_fee)
            if fee.max_fee > 0:
                amount = min(amount, fee.max_fee)

            amount = round(amount, 2)
            if amount <= 0:
                continue

            # Determine display
            if fee.applies_to == "aum":
                unit_label = "% of AUM"
                display_rate = fee.rate / 12.0  # Show monthly rate
            elif fee.applies_to == "trades":
                unit_label = "per trade"
                display_rate = fee.rate
            else:
                unit_label = "flat"
                display_rate = fee.rate

            items.append(InvoiceLineItem(
                description=fee.label or fee.fee_type.value.replace("_", " ").title(),
                fee_type=fee.fee_type.value,
                quantity=trade_count if fee.applies_to == "trades" else 1,
                unit_label=unit_label,
                rate=round(display_rate, 4),
                basis=basis,
                amount=amount,
                notes=fee.notes,
            ))

        return items

    def _get_passthrough_fees(
        self,
        client: Client,
        year: int,
        month: int,
    ) -> List[InvoiceLineItem]:
        """
        Extract broker fees from reconciled transactions to pass through.
        Looks at IBKR and Schwab fees/commissions for this client's accounts.
        """
        items = []

        # Try to load the latest reconciliation data
        from glob import glob
        batch_files = sorted(glob(os.path.join(PROCESSED_DIR, "upload_batch_*.json")))
        if not batch_files:
            return items

        try:
            with open(batch_files[-1]) as f:
                txn_data = json.load(f)
        except Exception:
            return items

        # Filter to this client's accounts and this month's fees
        client_accts = set(client.account_numbers.values())
        _, last_day = calendar.monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)

        fee_types = {"fee", "commission"}
        total_commissions = 0.0
        total_fees = 0.0
        commission_count = 0
        fee_count = 0

        for txn in txn_data:
            try:
                txn_date = date.fromisoformat(txn.get("date", ""))
            except (ValueError, TypeError):
                continue

            if not (start <= txn_date <= end):
                continue

            txn_type = txn.get("txn_type", "")
            source = txn.get("source", "")
            amount = abs(float(txn.get("amount", 0)))

            if txn_type == "commission":
                total_commissions += amount
                commission_count += 1
            elif txn_type == "fee" and source in ("ibkr", "schwab"):
                total_fees += amount
                fee_count += 1

        if total_commissions > 0:
            items.append(InvoiceLineItem(
                description="Brokerage Commissions (Passthrough)",
                fee_type="passthrough",
                quantity=commission_count,
                unit_label="trades",
                rate=round(total_commissions / max(commission_count, 1), 4),
                basis=0,
                amount=round(total_commissions, 2),
                notes=f"{commission_count} trades in period",
            ))

        if total_fees > 0:
            items.append(InvoiceLineItem(
                description="Platform & Data Fees (Passthrough)",
                fee_type="passthrough",
                quantity=fee_count,
                unit_label="items",
                rate=round(total_fees / max(fee_count, 1), 2),
                basis=0,
                amount=round(total_fees, 2),
                notes="IBKR/Schwab fees passed through",
            ))

        return items

    def _get_trade_count(self, client: Client, year: int, month: int) -> int:
        """Count trades for a client in the given month from reconciled data."""
        from glob import glob
        batch_files = sorted(glob(os.path.join(PROCESSED_DIR, "upload_batch_*.json")))
        if not batch_files:
            return 0

        try:
            with open(batch_files[-1]) as f:
                txn_data = json.load(f)
        except Exception:
            return 0

        _, last_day = calendar.monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)
        count = 0

        for txn in txn_data:
            try:
                txn_date = date.fromisoformat(txn.get("date", ""))
            except (ValueError, TypeError):
                continue
            if start <= txn_date <= end and txn.get("txn_type") in ("trade_buy", "trade_sell"):
                count += 1

        return count

    def _get_monthly_gains(self, client: Client, year: int, month: int) -> float:
        """Calculate net gains for the month (placeholder — customize for your logic)."""
        # This would typically come from portfolio performance data.
        # For now, return 0 so performance fees aren't charged without real data.
        return 0.0

    # ─── Email Sending ───────────────────────────────────────────

    def send_all(
        self,
        status_filter: List[str] = None,
        client_ids: List[str] = None,
        cc: List[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """Send all unsent invoices."""
        if not status_filter:
            status_filter = ["finalized"]

        all_inv = self.invoice_store.list_all()
        to_send = [
            self.invoice_store.get(inv["id"])
            for inv in all_inv
            if inv["status"] in status_filter
            and (not client_ids or inv["client_id"] in client_ids)
        ]
        to_send = [inv for inv in to_send if inv is not None]

        if not to_send:
            print("No invoices to send.")
            return {"sent": 0, "failed": 0, "skipped": 0}

        results = self.email_sender.send_batch(to_send, cc=cc, dry_run=dry_run)

        # Save updated statuses
        for inv in to_send:
            self.invoice_store.save(inv)

        return results

    def send_invoice(self, invoice_id: str, dry_run: bool = False) -> bool:
        """Send a specific invoice."""
        invoice = self.invoice_store.get(invoice_id)
        if not invoice:
            print(f"Invoice not found: {invoice_id}")
            return False
        success = self.email_sender.send_invoice(invoice, dry_run=dry_run)
        if success:
            self.invoice_store.save(invoice)
        return success

    # ─── Client Management Helpers ───────────────────────────────

    def add_client(self, **kwargs) -> Client:
        """Add a new client."""
        fee_schedule = kwargs.pop("fee_schedule", [])
        client = Client(**kwargs)
        client.fee_schedule = [
            FeeScheduleItem(**f) if isinstance(f, dict) else f
            for f in fee_schedule
        ]
        self.client_store.add(client)
        print(f"  Client added: {client.name} ({client.id})")
        return client

    def list_clients(self) -> List[Client]:
        """List all active clients."""
        return self.client_store.list_all()

    def list_invoices(self, client_id: str = None) -> List[dict]:
        """List all invoices, optionally filtered by client."""
        return self.invoice_store.list_all(client_id)

    # ─── Reporting ───────────────────────────────────────────────

    def billing_summary(self, year: int, month: int) -> str:
        """Generate a text summary of billing for the month."""
        month_name = calendar.month_name[month]
        period = f"{month_name} {year}"
        all_inv = self.invoice_store.list_all()
        monthly = [i for i in all_inv if i.get("period_label") == period]

        lines = [f"\n{'='*60}", f"  BILLING SUMMARY — {period}", f"{'='*60}", ""]
        total = 0
        for inv in monthly:
            status = inv.get("status", "").upper()
            amt = inv.get("total", 0)
            total += amt
            lines.append(
                f"  {inv.get('invoice_number', ''):12s}  "
                f"{inv.get('client_name', ''):25s}  "
                f"${amt:>10,.2f}  [{status}]"
            )
        lines.append(f"\n  {'TOTAL':38s}  ${total:>10,.2f}")
        lines.append(f"  {'Invoices':38s}  {len(monthly):>10d}")
        lines.append("=" * 60)
        return "\n".join(lines)
