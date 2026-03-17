#!/usr/bin/env python3
"""
Financial Reconciliation System — Main Entry Point

Usage:
    # Import and reconcile CSV files from all sources
    python main.py import --bofa ./data/bofa_checking.csv --ibkr ./data/ibkr_flex.csv --schwab ./data/schwab_history.csv

    # Reconcile against existing QuickBooks data
    python main.py import --bofa ./data/bofa.csv --qbo ./data/qbo_export.csv

    # Push reconciled transactions to QuickBooks Online
    python main.py push --use-api

    # Export for manual QBO import
    python main.py export --format csv --output ./output/for_qbo.csv

    # Auto-detect and process all files in a directory
    python main.py auto ./data/imports/

    # ── Client & Invoice Commands ──

    # Manage clients
    python main.py clients list
    python main.py clients add
    python main.py clients init-samples

    # Generate invoices for a billing month
    python main.py invoice generate --month 1 --year 2026
    python main.py invoice generate --month 1 --year 2026 --client "Smith Family Trust"

    # Send invoices via email
    python main.py invoice send --month 1 --year 2026
    python main.py invoice send --month 1 --year 2026 --dry-run

    # List all invoices
    python main.py invoice list
    python main.py invoice list --status sent
"""

import argparse
import json
import os
import sys
from datetime import datetime
from glob import glob
from pathlib import Path

from models import UnifiedTransaction, ReconciliationStatus
from parsers import get_parser, auto_detect_source, PARSERS
from reconciler import ReconciliationEngine
from qbo_integration import QuickBooksClient, QBOFileExporter
from config import (
    IMPORT_DIR, PROCESSED_DIR, ARCHIVE_DIR, LOG_DIR, DATA_DIR,
    BUSINESS_INFO,
)


def ensure_dirs():
    """Create required directories."""
    for d in [DATA_DIR, IMPORT_DIR, PROCESSED_DIR, ARCHIVE_DIR, LOG_DIR]:
        os.makedirs(d, exist_ok=True)


def cmd_import(args):
    """Import and reconcile transactions from CSV files."""
    ensure_dirs()
    engine = ReconciliationEngine()
    total_imported = 0

    sources = {
        "bofa": args.bofa,
        "ibkr": args.ibkr,
        "schwab": args.schwab,
        "qbo": args.qbo,
    }

    for source_name, filepath in sources.items():
        if not filepath:
            continue
        if not os.path.exists(filepath):
            print(f"⚠ File not found: {filepath}")
            continue

        print(f"\n▸ Parsing {source_name.upper()}: {filepath}")
        parser = get_parser(source_name)
        transactions = parser.parse_file(filepath)
        engine.add_transactions(transactions)
        total_imported += len(transactions)
        print(f"  ✓ Imported {len(transactions)} transactions")

    if total_imported == 0:
        print("\n⚠ No transactions imported. Check your file paths.")
        return

    # Run reconciliation
    print(f"\n{'='*60}")
    print("Running reconciliation...")
    print(f"{'='*60}")
    summary = engine.reconcile()

    # Print report
    print(engine.generate_report())

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(PROCESSED_DIR, f"reconciliation_{timestamp}.json")
    with open(results_file, 'w') as f:
        f.write(engine.to_json())
    print(f"\n✓ Results saved to: {results_file}")

    # Save upload batch
    upload_batch = engine.get_upload_batch()
    if upload_batch:
        batch_file = os.path.join(PROCESSED_DIR, f"upload_batch_{timestamp}.json")
        with open(batch_file, 'w') as f:
            json.dump([t.to_dict() for t in upload_batch], f, indent=2, default=str)
        print(f"✓ Upload batch ({len(upload_batch)} txns) saved to: {batch_file}")

    return engine


def cmd_auto(args):
    """Auto-detect and process all files in a directory."""
    ensure_dirs()
    directory = args.directory

    if not os.path.isdir(directory):
        print(f"⚠ Not a directory: {directory}")
        return

    files = glob(os.path.join(directory, "*.csv")) + glob(os.path.join(directory, "*.xml"))
    if not files:
        print(f"⚠ No CSV/XML files found in: {directory}")
        return

    engine = ReconciliationEngine()

    for filepath in files:
        source = auto_detect_source(filepath)
        if source:
            print(f"▸ Auto-detected {source.upper()}: {os.path.basename(filepath)}")
            parser = get_parser(source)
            transactions = parser.parse_file(filepath)
            engine.add_transactions(transactions)
            print(f"  ✓ Imported {len(transactions)} transactions")
        else:
            print(f"⚠ Could not detect source for: {os.path.basename(filepath)}")
            print(f"  Skipping. Use --bofa/--ibkr/--schwab flags to specify manually.")

    if engine.all_transactions:
        summary = engine.reconcile()
        print(engine.generate_report())


def cmd_export(args):
    """Export reconciled transactions for QBO import."""
    ensure_dirs()

    # Find the latest upload batch
    batch_files = sorted(glob(os.path.join(PROCESSED_DIR, "upload_batch_*.json")))
    if not batch_files:
        print("⚠ No upload batch found. Run 'import' first.")
        return

    latest = batch_files[-1]
    print(f"▸ Loading batch: {os.path.basename(latest)}")

    with open(latest) as f:
        data = json.load(f)

    transactions = [UnifiedTransaction.from_dict(d) for d in data]
    print(f"  ✓ Loaded {len(transactions)} transactions")

    output = args.output
    fmt = args.format

    if fmt == "csv":
        QBOFileExporter.to_csv(transactions, output)
    elif fmt == "iif":
        QBOFileExporter.to_iif(transactions, output)
    elif fmt == "qbo":
        QBOFileExporter.to_qbo_ofx(transactions, output)
    else:
        print(f"⚠ Unknown format: {fmt}. Use csv, iif, or qbo.")


def cmd_push(args):
    """Push transactions to QuickBooks Online via API."""
    ensure_dirs()

    # Find the latest upload batch
    batch_files = sorted(glob(os.path.join(PROCESSED_DIR, "upload_batch_*.json")))
    if not batch_files:
        print("⚠ No upload batch found. Run 'import' first.")
        return

    latest = batch_files[-1]
    with open(latest) as f:
        data = json.load(f)

    transactions = [UnifiedTransaction.from_dict(d) for d in data]
    print(f"▸ Loaded {len(transactions)} transactions to push")

    client = QuickBooksClient()
    if not client.authenticate():
        print("⚠ Authentication failed.")
        return

    if not args.yes:
        print(f"\nAbout to push {len(transactions)} transactions to QuickBooks Online.")
        confirm = input("Continue? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            return

    results = client.push_transactions(transactions)
    print(f"\n✓ Push complete: {results}")


def cmd_serve(args):
    """Run the Financial Planning Hub (unified Flask app)."""
    try:
        from app import app
        import webbrowser
    except ImportError as e:
        print(f"Error: {e}")
        print("Install dependencies: pip install flask flask-cors pdfplumber")
        return

    port = args.port or 5000

    print(f"\n{'='*60}")
    print(f"  Financial Planning Hub")
    print(f"  Running at http://localhost:{port}")
    print(f"{'='*60}")
    print(f"  Login:          http://localhost:{port}/login")
    print(f"  Client Portal:  http://localhost:{port}/portal")
    print(f"  Advisor Portal: http://localhost:{port}/advisor")
    print(f"  Dashboard:      http://localhost:{port}/dashboard")
    print(f"  API Health:     http://localhost:{port}/api/health")
    print(f"{'='*60}")
    print(f"  Default login:  admin@mgp.com / admin")
    print(f"{'='*60}\n")

    webbrowser.open(f"http://localhost:{port}/login")
    app.run(host="0.0.0.0", port=port, debug=True)


# ═══════════════════════════════════════════════════════════════════
# Client Commands
# ═══════════════════════════════════════════════════════════════════

def cmd_clients(args):
    """Manage clients."""
    from clients import ClientStore, Client, create_sample_clients

    store = ClientStore()
    action = args.client_action

    if action == "list":
        clients = store.get_all(active_only=not args.all)
        if not clients:
            print("No clients found. Run 'clients init-samples' to add sample clients.")
            return
        print(f"\n{'ID':<16s} {'Name':<25s} {'Company':<25s} {'Email':<30s} {'Fee Schedule'}")
        print("-" * 130)
        for c in clients:
            sched = c.get_fee_schedule()
            print(f"{c.id:<16s} {c.name:<25s} {c.company:<25s} {c.email:<30s} {sched.name}")
        print(f"\n{len(clients)} clients total")

    elif action == "init-samples":
        samples = create_sample_clients()
        for c in samples:
            store.add(c)
            print(f"  ✓ Added: {c.display_name} ({c.email})")
        print(f"\n✓ Created {len(samples)} sample clients")

    elif action == "add":
        print("\n── Add New Client ──")
        name = input("  Name: ").strip()
        company = input("  Company (optional): ").strip()
        email = input("  Email: ").strip()
        phone = input("  Phone (optional): ").strip()
        addr1 = input("  Address Line 1: ").strip()
        city = input("  City: ").strip()
        state = input("  State: ").strip()
        zipcode = input("  Zip: ").strip()

        client = Client(
            name=name, company=company, email=email, phone=phone,
            address_line1=addr1, city=city, state=state, zip_code=zipcode,
        )
        store.add(client)
        print(f"\n✓ Client added: {client.display_name} (ID: {client.id})")
        print("  Use the Python API to set up their fee schedule:")
        print(f"    from clients import ClientStore, FeeSchedule, FeeItem")
        print(f"    store = ClientStore()")
        print(f"    client = store.get('{client.id}')")
        print(f"    schedule = FeeSchedule(name='Custom')")
        print(f"    schedule.add_item(FeeItem(name='Monthly Fee', fee_type='flat', rate=1000.00))")
        print(f"    client.set_fee_schedule(schedule)")
        print(f"    store.update(client)")

    elif action == "show":
        if not args.name:
            print("Specify client: --name 'Client Name'")
            return
        client = store.get_by_name(args.name)
        if not client:
            print(f"Client not found: {args.name}")
            return
        print(f"\n── {client.display_name} ──")
        print(f"  ID:       {client.id}")
        print(f"  Email:    {client.email}")
        if client.cc_emails:
            print(f"  CC:       {', '.join(client.cc_emails)}")
        print(f"  Address:  {client.full_address}")
        print(f"  Terms:    Net {client.payment_terms}")
        print(f"  Accounts: {json.dumps(client.accounts)}")
        sched = client.get_fee_schedule()
        print(f"\n  Fee Schedule: {sched.name}")
        for item_data in sched.items:
            from clients import FeeItem
            fee = FeeItem(**item_data)
            if fee.fee_type == "flat":
                rate_str = f"${fee.rate:,.2f}"
            elif fee.fee_type in ("percent_aum", "percent_pnl"):
                rate_str = f"{fee.rate}%"
            elif fee.fee_type == "hourly":
                rate_str = f"${fee.rate}/hr"
            else:
                rate_str = f"${fee.rate:,.2f}"
            print(f"    {'✓' if fee.active else '✗'} {fee.name}: {rate_str} ({fee.fee_type})")
            if fee.minimum:
                print(f"      Min: ${fee.minimum:,.2f}")

    else:
        print("Unknown action. Use: list, add, show, init-samples")


# ═══════════════════════════════════════════════════════════════════
# Invoice Commands
# ═══════════════════════════════════════════════════════════════════

def cmd_invoice(args):
    """Generate, send, and manage invoices."""
    from clients import ClientStore
    from invoices import (
        InvoiceBuilder, InvoicePDFGenerator, InvoiceStore, InvoiceLineItem
    )
    from emailer import InvoiceEmailer, EmailConfig

    store = ClientStore()
    inv_store = InvoiceStore()
    action = args.invoice_action

    if action == "generate":
        month = args.month or datetime.now().month
        year = args.year or datetime.now().year

        # Filter to specific client if requested
        clients = store.get_all(active_only=True)
        if args.client:
            clients = [c for c in clients if
                       args.client.lower() in c.name.lower() or
                       args.client.lower() in c.company.lower()]
            if not clients:
                print(f"No client found matching: {args.client}")
                return

        if not clients:
            print("No active clients. Run 'clients init-samples' first.")
            return

        # Account data (AUM, P&L) — you'd pull this from reconciliation data
        # For now, use provided values or defaults
        account_data_map = {}
        if args.aum or args.pnl:
            for c in clients:
                account_data_map[c.id] = {
                    "aum": args.aum or 0,
                    "pnl": args.pnl or 0,
                }

        print(f"\n▸ Generating invoices for {datetime(year, month, 1).strftime('%B %Y')}")
        print(f"  Clients: {len(clients)}")
        print()

        builder = InvoiceBuilder(business_info=BUSINESS_INFO)
        invoices = builder.build_batch(
            clients=clients,
            billing_month=month,
            billing_year=year,
            account_data_map=account_data_map,
        )

        # Generate PDFs
        if invoices:
            print(f"\n▸ Generating PDFs...")
            pdf_gen = InvoicePDFGenerator()
            pdf_gen.generate_batch(invoices)

            # Save invoice records
            inv_store.save_batch(invoices)

            print(f"\n✓ Generated {len(invoices)} invoices")
            total = sum(i.total for i in invoices)
            print(f"  Total billed: ${total:,.2f}")
            print(f"  PDFs saved to: {pdf_gen.output_dir}")

    elif action == "send":
        month = args.month or datetime.now().month
        year = args.year or datetime.now().year

        # Find invoices for this period
        all_invoices = inv_store.get_all()
        period_prefix = f"{year}-{month:02d}"
        invoices = [
            i for i in all_invoices
            if i.period_start and i.period_start.startswith(period_prefix)
            and i.status in ("draft", "sent")  # Allow re-sending
        ]

        if args.client:
            invoices = [i for i in invoices if
                        args.client.lower() in i.client_name.lower() or
                        args.client.lower() in i.client_company.lower()]

        if not invoices:
            print(f"No invoices found for {period_prefix}. Run 'invoice generate' first.")
            return

        print(f"\n▸ Sending {len(invoices)} invoices")
        if args.dry_run:
            print("  [DRY RUN — no emails will be sent]\n")

        # Build client map for CC lookups
        clients = store.get_all(active_only=False)
        client_map = {c.id: c for c in clients}

        from config import SMTP_HOST, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, FROM_NAME
        from config import GLOBAL_CC_EMAILS, GLOBAL_BCC_EMAILS

        email_config = EmailConfig(
            smtp_host=SMTP_HOST,
            smtp_user=SMTP_USER,
            smtp_password=SMTP_PASSWORD,
            from_email=FROM_EMAIL or SMTP_USER,
            from_name=FROM_NAME,
            company_name=BUSINESS_INFO.get("company", ""),
            global_cc=GLOBAL_CC_EMAILS,
            global_bcc=GLOBAL_BCC_EMAILS,
        )

        emailer = InvoiceEmailer(email_config)
        results = emailer.send_batch(
            invoices=invoices,
            client_map=client_map,
            custom_message=args.message or "",
            dry_run=args.dry_run,
        )

        # Update invoice statuses
        if not args.dry_run:
            inv_store.save_batch(invoices)

        print(f"\n✓ Email results: {results}")

    elif action == "list":
        invoices = inv_store.get_all()
        if args.status:
            invoices = [i for i in invoices if i.status == args.status]

        if not invoices:
            print("No invoices found.")
            return

        print(f"\n{'Invoice #':<18s} {'Client':<25s} {'Period':<12s} {'Total':>10s} {'Status':<10s} {'Sent'}")
        print("-" * 100)
        for inv in invoices:
            period = inv.period_start[:7] if inv.period_start else "—"
            sent = inv.sent_at[:10] if inv.sent_at else "—"
            print(
                f"{inv.invoice_number:<18s} {inv.client_company[:24]:<25s} "
                f"{period:<12s} ${inv.total:>9,.2f} {inv.status:<10s} {sent}"
            )
        total = sum(i.total for i in invoices)
        print(f"\n{len(invoices)} invoices — Total: ${total:,.2f}")

    elif action == "preview":
        if not args.invoice_num:
            print("Specify invoice: --invoice-num INV-2026-0001")
            return
        inv = inv_store.get(args.invoice_num)
        if not inv:
            print(f"Invoice not found: {args.invoice_num}")
            return
        print(f"\n── Invoice {inv.invoice_number} ──")
        print(f"  Client:  {inv.client_company} ({inv.client_name})")
        print(f"  Period:  {inv.period_start} to {inv.period_end}")
        print(f"  Issued:  {inv.issue_date}")
        print(f"  Due:     {inv.due_date}")
        print(f"  Status:  {inv.status}")
        print(f"\n  Line Items:")
        for item_data in inv.line_items:
            from invoices import InvoiceLineItem
            item = InvoiceLineItem(**item_data)
            print(f"    {item.description:<50s} ${item.amount:>10,.2f}")
            if item.detail:
                print(f"      {item.detail}")
        print(f"\n  {'Subtotal:':<52s} ${inv.subtotal:>10,.2f}")
        if inv.tax_amount > 0:
            print(f"  {'Tax:':<52s} ${inv.tax_amount:>10,.2f}")
        print(f"  {'TOTAL DUE:':<52s} ${inv.balance_due:>10,.2f}")
        if inv.pdf_path:
            print(f"\n  PDF: {inv.pdf_path}")

    else:
        print("Unknown action. Use: generate, send, list, preview")


def main():
    parser = argparse.ArgumentParser(
        description="Financial Reconciliation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # import command
    p_import = subparsers.add_parser("import", help="Import and reconcile CSVs")
    p_import.add_argument("--bofa", help="Bank of America CSV file")
    p_import.add_argument("--ibkr", help="Interactive Brokers Flex Query CSV/XML")
    p_import.add_argument("--schwab", help="Charles Schwab CSV export")
    p_import.add_argument("--qbo", help="QuickBooks export CSV (for reconciliation baseline)")

    # auto command
    p_auto = subparsers.add_parser("auto", help="Auto-detect and process all files in a directory")
    p_auto.add_argument("directory", help="Directory containing CSV/XML files")

    # export command
    p_export = subparsers.add_parser("export", help="Export for QBO import")
    p_export.add_argument("--format", choices=["csv", "iif", "qbo"], default="csv")
    p_export.add_argument("--output", required=True, help="Output file path")

    # push command
    p_push = subparsers.add_parser("push", help="Push to QuickBooks Online via API")
    p_push.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    # serve command
    p_serve = subparsers.add_parser("serve", help="Run web dashboard")
    p_serve.add_argument("--port", type=int, default=5000)

    # ── Client commands ──
    p_clients = subparsers.add_parser("clients", help="Manage clients")
    p_clients.add_argument("client_action", choices=["list", "add", "show", "init-samples"],
                           help="Client action")
    p_clients.add_argument("--name", help="Client name (for 'show')")
    p_clients.add_argument("--all", action="store_true", help="Include inactive clients")

    # ── Invoice commands ──
    p_invoice = subparsers.add_parser("invoice", help="Generate, send, and manage invoices")
    p_invoice.add_argument("invoice_action", choices=["generate", "send", "list", "preview"],
                           help="Invoice action")
    p_invoice.add_argument("--month", type=int, help="Billing month (1-12)")
    p_invoice.add_argument("--year", type=int, help="Billing year")
    p_invoice.add_argument("--client", help="Filter to specific client name")
    p_invoice.add_argument("--aum", type=float, help="AUM value for percent-based fees")
    p_invoice.add_argument("--pnl", type=float, help="P&L value for performance fees")
    p_invoice.add_argument("--dry-run", action="store_true", help="Preview without sending emails")
    p_invoice.add_argument("--message", help="Custom message to include in email body")
    p_invoice.add_argument("--status", help="Filter invoices by status (for 'list')")
    p_invoice.add_argument("--invoice-num", help="Invoice number (for 'preview')")

    args = parser.parse_args()

    if args.command == "import":
        cmd_import(args)
    elif args.command == "auto":
        cmd_auto(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "push":
        cmd_push(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "clients":
        cmd_clients(args)
    elif args.command == "invoice":
        cmd_invoice(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
