"""
Invoice Generator.

Creates professional PDF invoices for each client, per billing period.
Invoices are customizable via templates and fee schedules.

Supports:
- Flat fees, AUM-based fees, performance fees, hourly billing
- Automatic line item calculation
- Custom notes, terms, and branding
- PDF generation via reportlab
- Invoice numbering and tracking
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Tuple
from pathlib import Path
import calendar

from config import DATA_DIR

INVOICES_DIR = os.path.join(DATA_DIR, "invoices")
INVOICE_REGISTRY = os.path.join(DATA_DIR, "invoice_registry.json")


# ═══════════════════════════════════════════════════════════════════
# Invoice Data Model
# ═══════════════════════════════════════════════════════════════════

@dataclass
class InvoiceLineItem:
    """A single line on an invoice."""
    description: str
    detail: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    taxable: bool = False

    def __post_init__(self):
        if self.amount == 0:
            self.amount = round(self.quantity * self.unit_price, 2)


@dataclass
class Invoice:
    """A complete invoice."""
    # Identity
    invoice_number: str = ""
    client_id: str = ""
    client_name: str = ""
    client_company: str = ""
    client_email: str = ""
    client_address: str = ""

    # Your business info
    from_name: str = ""
    from_company: str = ""
    from_address: str = ""
    from_email: str = ""
    from_phone: str = ""
    from_logo_path: str = ""       # Optional path to logo image

    # Dates
    issue_date: str = ""
    due_date: str = ""
    period_start: str = ""
    period_end: str = ""

    # Line items
    line_items: List[Dict] = field(default_factory=list)

    # Totals
    subtotal: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    amount_paid: float = 0.0
    balance_due: float = 0.0

    # Customization
    currency: str = "USD"
    notes: str = ""                 # Shown on invoice
    terms: str = ""                 # Payment terms text
    footer: str = ""                # Footer text
    memo: str = ""                  # Internal memo (not shown)

    # Status tracking
    status: str = "draft"           # draft, sent, paid, overdue, void
    sent_at: str = ""
    paid_at: str = ""
    pdf_path: str = ""

    def get_line_items(self) -> List[InvoiceLineItem]:
        return [InvoiceLineItem(**item) for item in self.line_items]

    def add_line_item(self, item: InvoiceLineItem):
        self.line_items.append(asdict(item))
        self._recalculate()

    def _recalculate(self):
        items = self.get_line_items()
        self.subtotal = round(sum(i.amount for i in items), 2)
        taxable = sum(i.amount for i in items if i.taxable)
        self.tax_amount = round(taxable * (self.tax_rate / 100.0), 2)
        self.total = round(self.subtotal + self.tax_amount, 2)
        self.balance_due = round(self.total - self.amount_paid, 2)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Invoice":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════
# Invoice Number Generator
# ═══════════════════════════════════════════════════════════════════

class InvoiceNumbering:
    """Generates unique, sequential invoice numbers."""

    def __init__(self, registry_path: str = None):
        self.registry_path = registry_path or INVOICE_REGISTRY
        self._registry = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.registry_path):
            with open(self.registry_path) as f:
                return json.load(f)
        return {"last_number": 0, "invoices": {}}

    def _save(self):
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, 'w') as f:
            json.dump(self._registry, f, indent=2)

    def next_number(self, prefix: str = "INV") -> str:
        """Generate next invoice number like INV-2026-0001."""
        year = datetime.now().year
        self._registry["last_number"] = self._registry.get("last_number", 0) + 1
        num = self._registry["last_number"]
        invoice_number = f"{prefix}-{year}-{num:04d}"
        self._save()
        return invoice_number

    def register(self, invoice: Invoice):
        """Track an invoice in the registry."""
        self._registry["invoices"][invoice.invoice_number] = {
            "client_id": invoice.client_id,
            "client_name": invoice.client_name,
            "total": invoice.total,
            "issue_date": invoice.issue_date,
            "due_date": invoice.due_date,
            "status": invoice.status,
            "pdf_path": invoice.pdf_path,
        }
        self._save()

    def get_all(self) -> Dict:
        return self._registry.get("invoices", {})


# ═══════════════════════════════════════════════════════════════════
# Invoice Builder
# ═══════════════════════════════════════════════════════════════════

class InvoiceBuilder:
    """
    Builds invoices from clients, fee schedules, and optional
    account data (AUM, P&L) from the reconciliation system.
    """

    def __init__(self, business_info: Dict = None):
        """
        business_info: Your company details for the invoice header.
        {
            "name": "Your Name",
            "company": "Your Company LLC",
            "address": "123 Main St\nMiami, FL 33101",
            "email": "you@yourcompany.com",
            "phone": "(305) 555-1234",
            "logo_path": "./assets/logo.png",
        }
        """
        self.business = business_info or {}
        self.numbering = InvoiceNumbering()

    def build_invoice(
        self,
        client,  # clients.Client
        billing_month: int,
        billing_year: int,
        account_data: Dict[str, float] = None,
        custom_items: List[InvoiceLineItem] = None,
        notes: str = "",
        terms: str = "",
    ) -> Invoice:
        """
        Build an invoice for a client for a specific month.

        account_data: Optional dict with values the fee schedule may need.
            {"aum": 1500000.00, "pnl": 45000.00}
        custom_items: Additional one-off line items to add.
        """
        account_data = account_data or {}

        # Determine billing period
        _, last_day = calendar.monthrange(billing_year, billing_month)
        period_start = date(billing_year, billing_month, 1)
        period_end = date(billing_year, billing_month, last_day)
        issue_date = date.today()
        due_date = issue_date + timedelta(days=client.payment_terms)

        month_name = calendar.month_name[billing_month]

        # Create invoice
        invoice = Invoice(
            invoice_number=self.numbering.next_number(),
            client_id=client.id,
            client_name=client.name,
            client_company=client.company or client.name,
            client_email=client.email,
            client_address=client.full_address,
            from_name=self.business.get("name", ""),
            from_company=self.business.get("company", ""),
            from_address=self.business.get("address", ""),
            from_email=self.business.get("email", ""),
            from_phone=self.business.get("phone", ""),
            from_logo_path=self.business.get("logo_path", ""),
            issue_date=issue_date.isoformat(),
            due_date=due_date.isoformat(),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            tax_rate=client.tax_rate,
            currency=client.currency,
            notes=notes,
            terms=terms or f"Payment due within {client.payment_terms} days of invoice date.",
            footer=self.business.get("footer", "Thank you for your business."),
        )

        # Calculate fees from the client's fee schedule
        schedule = client.get_fee_schedule()
        for item_data in schedule.items:
            from clients import FeeItem
            fee = FeeItem(**item_data)
            if not fee.active:
                continue

            if fee.fee_type == "percent_aum":
                basis = account_data.get("aum", 0)
                amount = fee.calculate(basis)
                detail = f"AUM: ${basis:,.2f} x {fee.rate}% annual / 12"
            elif fee.fee_type == "percent_pnl":
                basis = account_data.get("pnl", 0)
                amount = fee.calculate(basis)
                if amount == 0 and basis <= 0:
                    continue  # Skip performance fee if no profit
                detail = f"Net P&L: ${basis:,.2f} x {fee.rate}%"
            elif fee.fee_type == "hourly":
                amount = fee.calculate()
                detail = f"{fee.quantity} hrs x ${fee.rate}/hr"
            else:
                amount = fee.calculate()
                detail = fee.description

            invoice.add_line_item(InvoiceLineItem(
                description=f"{fee.name} — {month_name} {billing_year}",
                detail=detail,
                quantity=1,
                unit_price=amount,
                amount=amount,
                taxable=fee.taxable,
            ))

        # Add any custom one-off items
        if custom_items:
            for item in custom_items:
                invoice.add_line_item(item)

        # Register it
        self.numbering.register(invoice)

        return invoice

    def build_batch(
        self,
        clients: list,
        billing_month: int,
        billing_year: int,
        account_data_map: Dict[str, Dict[str, float]] = None,
    ) -> List[Invoice]:
        """
        Build invoices for all clients for a given month.

        account_data_map: {client_id: {"aum": ..., "pnl": ...}}
        """
        account_data_map = account_data_map or {}
        invoices = []

        for client in clients:
            if not client.active:
                continue

            client_data = account_data_map.get(client.id, {})
            try:
                invoice = self.build_invoice(
                    client=client,
                    billing_month=billing_month,
                    billing_year=billing_year,
                    account_data=client_data,
                )
                invoices.append(invoice)
                print(f"  ✓ {client.display_name}: {invoice.invoice_number} — ${invoice.total:,.2f}")
            except Exception as e:
                print(f"  ✗ {client.display_name}: {e}")

        return invoices


# ═══════════════════════════════════════════════════════════════════
# PDF Generator
# ═══════════════════════════════════════════════════════════════════

class InvoicePDFGenerator:
    """
    Generate professional PDF invoices using reportlab.
    """

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or INVOICES_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, invoice: Invoice) -> str:
        """Generate a PDF and return the file path."""
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable
        )

        filename = f"{invoice.invoice_number}.pdf"
        filepath = os.path.join(self.output_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
        )

        # ── Colors ──
        PRIMARY = HexColor("#1a1a2e")
        ACCENT = HexColor("#16a34a")
        LIGHT_BG = HexColor("#f8f9fa")
        BORDER = HexColor("#dee2e6")
        MUTED = HexColor("#6b7280")
        DARK_TEXT = HexColor("#111827")

        # ── Styles ──
        styles = getSampleStyleSheet()

        style_header = ParagraphStyle(
            "InvHeader", parent=styles["Normal"],
            fontSize=28, fontName="Helvetica-Bold",
            textColor=PRIMARY, spaceAfter=2,
        )
        style_subtitle = ParagraphStyle(
            "InvSubtitle", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica",
            textColor=MUTED, spaceAfter=6,
        )
        style_section = ParagraphStyle(
            "InvSection", parent=styles["Normal"],
            fontSize=8, fontName="Helvetica-Bold",
            textColor=MUTED, spaceAfter=4,
            spaceBefore=14,
        )
        style_body = ParagraphStyle(
            "InvBody", parent=styles["Normal"],
            fontSize=9.5, fontName="Helvetica",
            textColor=DARK_TEXT, leading=14,
        )
        style_body_right = ParagraphStyle(
            "InvBodyR", parent=style_body,
            alignment=TA_RIGHT,
        )
        style_body_bold = ParagraphStyle(
            "InvBodyBold", parent=style_body,
            fontName="Helvetica-Bold",
        )
        style_total_label = ParagraphStyle(
            "TotalLabel", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica-Bold",
            textColor=DARK_TEXT, alignment=TA_RIGHT,
        )
        style_total_value = ParagraphStyle(
            "TotalValue", parent=styles["Normal"],
            fontSize=14, fontName="Helvetica-Bold",
            textColor=ACCENT, alignment=TA_RIGHT,
        )
        style_small = ParagraphStyle(
            "InvSmall", parent=styles["Normal"],
            fontSize=8, fontName="Helvetica",
            textColor=MUTED, leading=11,
        )
        style_small_bold = ParagraphStyle(
            "InvSmallBold", parent=style_small,
            fontName="Helvetica-Bold",
        )

        story = []

        # ── Header: INVOICE title + number ──
        header_data = [
            [
                Paragraph("INVOICE", style_header),
                Paragraph(f"<b>{invoice.invoice_number}</b>", ParagraphStyle(
                    "InvNum", parent=styles["Normal"],
                    fontSize=11, fontName="Helvetica-Bold",
                    textColor=PRIMARY, alignment=TA_RIGHT,
                )),
            ]
        ]
        header_table = Table(header_data, colWidths=[4 * inch, 3 * inch])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4))

        # ── Date / Period info bar ──
        issue_fmt = self._format_date(invoice.issue_date)
        due_fmt = self._format_date(invoice.due_date)
        period_start_fmt = self._format_date(invoice.period_start)
        period_end_fmt = self._format_date(invoice.period_end)

        info_data = [[
            Paragraph(f"Issued: <b>{issue_fmt}</b>", style_small),
            Paragraph(f"Due: <b>{due_fmt}</b>", style_small),
            Paragraph(f"Period: <b>{period_start_fmt} — {period_end_fmt}</b>", style_small),
        ]]
        info_table = Table(info_data, colWidths=[2.3 * inch, 2.3 * inch, 2.4 * inch])
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 18))

        # ── From / To addresses ──
        from_lines = []
        if invoice.from_company:
            from_lines.append(f"<b>{invoice.from_company}</b>")
        if invoice.from_name and invoice.from_name != invoice.from_company:
            from_lines.append(invoice.from_name)
        if invoice.from_address:
            from_lines.extend(invoice.from_address.split("\n"))
        if invoice.from_email:
            from_lines.append(invoice.from_email)
        if invoice.from_phone:
            from_lines.append(invoice.from_phone)

        to_lines = []
        if invoice.client_company:
            to_lines.append(f"<b>{invoice.client_company}</b>")
        if invoice.client_name and invoice.client_name != invoice.client_company:
            to_lines.append(invoice.client_name)
        if invoice.client_address:
            to_lines.extend(invoice.client_address.split("\n"))
        if invoice.client_email:
            to_lines.append(invoice.client_email)

        addr_data = [[
            [
                Paragraph("FROM", style_section),
                Paragraph("<br/>".join(from_lines), style_body),
            ],
            [
                Paragraph("BILL TO", style_section),
                Paragraph("<br/>".join(to_lines), style_body),
            ],
        ]]
        addr_table = Table(addr_data, colWidths=[3.5 * inch, 3.5 * inch])
        addr_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(addr_table)
        story.append(Spacer(1, 20))

        # ── Line Items Table ──
        items = invoice.get_line_items()

        table_header = [
            Paragraph("<b>Description</b>", style_small_bold),
            Paragraph("<b>Detail</b>", style_small_bold),
            Paragraph("<b>Qty</b>", ParagraphStyle("H", parent=style_small_bold, alignment=TA_CENTER)),
            Paragraph("<b>Rate</b>", ParagraphStyle("H", parent=style_small_bold, alignment=TA_RIGHT)),
            Paragraph("<b>Amount</b>", ParagraphStyle("H", parent=style_small_bold, alignment=TA_RIGHT)),
        ]

        table_data = [table_header]
        for item in items:
            table_data.append([
                Paragraph(item.description, style_body),
                Paragraph(item.detail or "", style_small),
                Paragraph(f"{item.quantity:g}", ParagraphStyle("C", parent=style_body, alignment=TA_CENTER)),
                Paragraph(f"${item.unit_price:,.2f}", style_body_right),
                Paragraph(f"${item.amount:,.2f}", ParagraphStyle("B", parent=style_body_right, fontName="Helvetica-Bold")),
            ])

        col_widths = [2.2 * inch, 2.0 * inch, 0.6 * inch, 1.1 * inch, 1.1 * inch]
        items_table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Table styling
        ts = [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            # Body
            ("VALIGN", (0, 1), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            # Grid
            ("LINEBELOW", (0, 0), (-1, 0), 1, PRIMARY),
        ]
        # Alternating row backgrounds
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                ts.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BG))
            ts.append(("LINEBELOW", (0, i), (-1, i), 0.5, BORDER))

        items_table.setStyle(TableStyle(ts))
        story.append(items_table)
        story.append(Spacer(1, 16))

        # ── Totals ──
        totals_data = []

        totals_data.append([
            "", "",
            Paragraph("Subtotal", style_body_right),
            Paragraph(f"${invoice.subtotal:,.2f}", style_body_right),
        ])

        if invoice.tax_rate > 0:
            totals_data.append([
                "", "",
                Paragraph(f"Tax ({invoice.tax_rate}%)", style_body_right),
                Paragraph(f"${invoice.tax_amount:,.2f}", style_body_right),
            ])

        if invoice.amount_paid > 0:
            totals_data.append([
                "", "",
                Paragraph("Paid", style_body_right),
                Paragraph(f"-${invoice.amount_paid:,.2f}", style_body_right),
            ])

        totals_data.append([
            "", "",
            Paragraph("<b>TOTAL DUE</b>", style_total_label),
            Paragraph(f"<b>${invoice.balance_due:,.2f}</b>", style_total_value),
        ])

        totals_table = Table(
            totals_data,
            colWidths=[2.2 * inch, 2.0 * inch, 1.7 * inch, 1.1 * inch],
        )
        totals_table.setStyle(TableStyle([
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEABOVE", (2, -1), (-1, -1), 1.5, PRIMARY),
            ("TOPPADDING", (0, -1), (-1, -1), 8),
        ]))
        story.append(totals_table)

        # ── Notes ──
        if invoice.notes:
            story.append(Spacer(1, 24))
            story.append(Paragraph("NOTES", style_section))
            story.append(Paragraph(invoice.notes, style_body))

        # ── Terms ──
        if invoice.terms:
            story.append(Spacer(1, 16))
            story.append(Paragraph("TERMS", style_section))
            story.append(Paragraph(invoice.terms, style_small))

        # ── Footer ──
        if invoice.footer:
            story.append(Spacer(1, 30))
            story.append(HRFlowable(
                width="100%", thickness=0.5, color=BORDER,
                spaceAfter=8, spaceBefore=0,
            ))
            story.append(Paragraph(
                invoice.footer,
                ParagraphStyle("Footer", parent=style_small, alignment=TA_CENTER),
            ))

        # Build PDF
        doc.build(story)
        invoice.pdf_path = filepath
        print(f"  ✓ PDF: {filepath}")
        return filepath

    def generate_batch(self, invoices: List[Invoice]) -> List[str]:
        """Generate PDFs for a batch of invoices."""
        paths = []
        for inv in invoices:
            try:
                path = self.generate(inv)
                paths.append(path)
            except Exception as e:
                print(f"  ✗ PDF failed for {inv.invoice_number}: {e}")
        return paths

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Format ISO date to readable format."""
        try:
            d = date.fromisoformat(date_str)
            return d.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return date_str or ""


# ═══════════════════════════════════════════════════════════════════
# Invoice Storage
# ═══════════════════════════════════════════════════════════════════

class InvoiceStore:
    """Persist invoices to JSON."""

    def __init__(self, filepath: str = None):
        self.filepath = filepath or os.path.join(DATA_DIR, "invoices_data.json")
        self._invoices: Dict[str, Invoice] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath) as f:
                    data = json.load(f)
                for item in data.get("invoices", []):
                    inv = Invoice.from_dict(item)
                    self._invoices[inv.invoice_number] = inv
            except Exception as e:
                print(f"Warning: Could not load invoices: {e}")

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        data = {"invoices": [i.to_dict() for i in self._invoices.values()]}
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def save(self, invoice: Invoice):
        self._invoices[invoice.invoice_number] = invoice
        self._save()

    def save_batch(self, invoices: List[Invoice]):
        for inv in invoices:
            self._invoices[inv.invoice_number] = inv
        self._save()

    def get(self, invoice_number: str) -> Optional[Invoice]:
        return self._invoices.get(invoice_number)

    def get_by_client(self, client_id: str) -> List[Invoice]:
        return sorted(
            [i for i in self._invoices.values() if i.client_id == client_id],
            key=lambda i: i.issue_date, reverse=True,
        )

    def get_by_status(self, status: str) -> List[Invoice]:
        return [i for i in self._invoices.values() if i.status == status]

    def get_all(self) -> List[Invoice]:
        return sorted(self._invoices.values(), key=lambda i: i.issue_date, reverse=True)

    def update_status(self, invoice_number: str, status: str):
        if invoice_number in self._invoices:
            self._invoices[invoice_number].status = status
            if status == "sent":
                self._invoices[invoice_number].sent_at = datetime.now().isoformat()
            elif status == "paid":
                self._invoices[invoice_number].paid_at = datetime.now().isoformat()
            self._save()
