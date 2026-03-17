"""
PDF Invoice Generator.

Creates professional, customizable fee invoices using ReportLab.
The template is clean and CPA-friendly with full line-item detail.

Usage:
    from invoice_pdf import InvoicePDFGenerator
    generator = InvoicePDFGenerator()
    pdf_path = generator.generate(invoice)
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from invoice_models import Invoice, InvoiceLineItem, InvoiceStatus
from config import DATA_DIR

OUTPUT_DIR = os.path.join(DATA_DIR, "invoices", "pdf")


# ─── Color Palette (customizable) ───────────────────────────────
class InvoiceTheme:
    """Modern, clean invoice theme — light and refined."""
    primary = colors.HexColor("#1a1a2e")        # Deep navy for headers/accents
    accent = colors.HexColor("#2563eb")          # Clean blue accent
    highlight = colors.HexColor("#f0f4ff")       # Light blue row highlight
    text_dark = colors.HexColor("#1e293b")       # Slate-900
    text_medium = colors.HexColor("#475569")     # Slate-600
    text_light = colors.HexColor("#94a3b8")      # Slate-400
    line_color = colors.HexColor("#e2e8f0")      # Slate-200 — subtle borders
    bg_light = colors.HexColor("#f8fafc")        # Slate-50 — alternating rows
    white = colors.white
    green = colors.HexColor("#10b981")           # Emerald-500
    amount_color = colors.HexColor("#1a1a2e")    # Deep navy for totals
    brand_gold = colors.HexColor("#b8964e")      # Brand accent (sparingly)


class InvoicePDFGenerator:
    """
    Generates professional PDF invoices.

    Customize:
    - theme: InvoiceTheme instance for colors
    - company defaults: set in generate() or config
    """

    def __init__(self, theme: InvoiceTheme = None):
        self.theme = theme or InvoiceTheme()

    def generate(self, invoice: Invoice, output_dir: str = None) -> str:
        """
        Generate a PDF for the given invoice.
        Returns the file path of the created PDF.
        """
        output_dir = output_dir or OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)

        safe_name = invoice.client_name.replace(" ", "_").replace("/", "-")[:30]
        period = invoice.period_label.replace(" ", "_")
        filename = f"{invoice.invoice_number}_{safe_name}_{period}.pdf"
        filepath = os.path.join(output_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            topMargin=0.5 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.65 * inch,
            rightMargin=0.65 * inch,
        )

        styles = self._build_styles()
        story = []

        # ── Header Block ──
        story.append(self._build_header(invoice, styles))
        story.append(Spacer(1, 20))

        # ── Bill To / Invoice Details ──
        story.append(self._build_addresses(invoice, styles))
        story.append(Spacer(1, 24))

        # ── Period Banner ──
        story.append(self._build_period_banner(invoice, styles))
        story.append(Spacer(1, 16))

        # ── Line Items Table ──
        story.append(self._build_line_items(invoice, styles))
        story.append(Spacer(1, 16))

        # ── Totals ──
        story.append(self._build_totals(invoice, styles))
        story.append(Spacer(1, 24))

        # ── Notes ──
        if invoice.notes:
            story.append(Paragraph("Notes", styles["section_header"]))
            story.append(Spacer(1, 4))
            story.append(Paragraph(invoice.notes, styles["body_small"]))
            story.append(Spacer(1, 16))

        # ── Footer ──
        story.append(Spacer(1, 12))
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=self.theme.line_color, spaceAfter=10
        ))
        story.append(Paragraph(invoice.footer_text, styles["footer"]))

        # Build
        doc.build(story)

        # Update invoice with PDF path
        invoice.pdf_path = filepath
        print(f"  [PDF] Generated: {filepath}")
        return filepath

    # ─── Style Definitions ──────────────────────────────────────

    def _build_styles(self):
        base = getSampleStyleSheet()
        styles = {}

        styles["company_name"] = ParagraphStyle(
            "CompanyName", parent=base["Normal"],
            fontSize=18, leading=22, fontName="Helvetica-Bold",
            textColor=self.theme.primary,
        )
        styles["invoice_title"] = ParagraphStyle(
            "InvoiceTitle", parent=base["Normal"],
            fontSize=24, leading=28, fontName="Helvetica-Bold",
            textColor=self.theme.text_light, alignment=TA_RIGHT,
        )
        styles["invoice_number"] = ParagraphStyle(
            "InvoiceNum", parent=base["Normal"],
            fontSize=10, leading=14, fontName="Helvetica",
            textColor=self.theme.text_medium, alignment=TA_RIGHT,
        )
        styles["label"] = ParagraphStyle(
            "Label", parent=base["Normal"],
            fontSize=8, leading=10, fontName="Helvetica-Bold",
            textColor=self.theme.text_light, spaceAfter=2,
        )
        styles["value"] = ParagraphStyle(
            "Value", parent=base["Normal"],
            fontSize=10, leading=14, fontName="Helvetica",
            textColor=self.theme.text_dark,
        )
        styles["value_bold"] = ParagraphStyle(
            "ValueBold", parent=base["Normal"],
            fontSize=10, leading=14, fontName="Helvetica-Bold",
            textColor=self.theme.text_dark,
        )
        styles["section_header"] = ParagraphStyle(
            "SectionHeader", parent=base["Normal"],
            fontSize=9, leading=12, fontName="Helvetica-Bold",
            textColor=self.theme.primary, spaceAfter=4,
        )
        styles["body_small"] = ParagraphStyle(
            "BodySmall", parent=base["Normal"],
            fontSize=9, leading=13, fontName="Helvetica",
            textColor=self.theme.text_medium,
        )
        styles["period_banner"] = ParagraphStyle(
            "PeriodBanner", parent=base["Normal"],
            fontSize=10, leading=14, fontName="Helvetica-Bold",
            textColor=self.theme.accent,
        )
        styles["footer"] = ParagraphStyle(
            "Footer", parent=base["Normal"],
            fontSize=9, leading=13, fontName="Helvetica",
            textColor=self.theme.text_light, alignment=TA_CENTER,
        )
        styles["table_header"] = ParagraphStyle(
            "TableHeader", parent=base["Normal"],
            fontSize=8, leading=10, fontName="Helvetica-Bold",
            textColor=self.theme.text_medium,
        )
        styles["table_header_right"] = ParagraphStyle(
            "TableHeaderRight", parent=styles["table_header"],
            alignment=TA_RIGHT, textColor=self.theme.text_medium,
        )
        styles["cell"] = ParagraphStyle(
            "Cell", parent=base["Normal"],
            fontSize=9, leading=13, fontName="Helvetica",
            textColor=self.theme.text_dark,
        )
        styles["cell_right"] = ParagraphStyle(
            "CellRight", parent=styles["cell"],
            alignment=TA_RIGHT,
        )
        styles["cell_desc"] = ParagraphStyle(
            "CellDesc", parent=styles["cell"],
            fontSize=9, textColor=self.theme.text_medium,
        )
        styles["total_label"] = ParagraphStyle(
            "TotalLabel", parent=base["Normal"],
            fontSize=10, leading=14, fontName="Helvetica",
            textColor=self.theme.text_medium, alignment=TA_RIGHT,
        )
        styles["total_value"] = ParagraphStyle(
            "TotalValue", parent=base["Normal"],
            fontSize=10, leading=14, fontName="Helvetica-Bold",
            textColor=self.theme.text_dark, alignment=TA_RIGHT,
        )
        styles["grand_total_label"] = ParagraphStyle(
            "GrandTotalLabel", parent=base["Normal"],
            fontSize=13, leading=18, fontName="Helvetica-Bold",
            textColor=self.theme.primary, alignment=TA_RIGHT,
        )
        styles["grand_total_value"] = ParagraphStyle(
            "GrandTotalValue", parent=base["Normal"],
            fontSize=13, leading=18, fontName="Helvetica-Bold",
            textColor=self.theme.primary, alignment=TA_RIGHT,
        )

        return styles

    # ─── Component Builders ─────────────────────────────────────

    def _build_header(self, invoice: Invoice, styles: dict):
        """Company name + INVOICE title side by side."""
        left = []
        left.append(Paragraph(invoice.company_name or "Your Company", styles["company_name"]))
        if invoice.company_address:
            for line in invoice.company_address.split("\n"):
                left.append(Paragraph(line, styles["body_small"]))
        if invoice.company_email:
            left.append(Paragraph(invoice.company_email, styles["body_small"]))
        if invoice.company_phone:
            left.append(Paragraph(invoice.company_phone, styles["body_small"]))

        right = []
        right.append(Paragraph("INVOICE", styles["invoice_title"]))
        right.append(Paragraph(f"#{invoice.invoice_number}", styles["invoice_number"]))

        data = [[left, right]]
        t = Table(data, colWidths=[3.5 * inch, 3.5 * inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    def _build_addresses(self, invoice: Invoice, styles: dict):
        """Bill To on the left, invoice dates on the right."""
        # Left: Bill To
        left = []
        left.append(Paragraph("BILL TO", styles["label"]))
        left.append(Paragraph(invoice.client_name, styles["value_bold"]))
        if invoice.client_address:
            for line in invoice.client_address.split("\n"):
                left.append(Paragraph(line, styles["value"]))
        if invoice.client_email:
            left.append(Paragraph(invoice.client_email, styles["body_small"]))

        # Right: Dates
        right_data = [
            ["Issue Date:", invoice.issue_date],
            ["Due Date:", invoice.due_date],
            ["Terms:", f"Net {invoice.payment_terms}"],
        ]

        status_text = invoice.status.value.upper()
        if invoice.status == InvoiceStatus.PAID:
            status_text = f"PAID ({invoice.paid_at or ''})"

        right_data.append(["Status:", status_text])

        right_rows = []
        for label, val in right_data:
            right_rows.append([
                Paragraph(label, styles["label"]),
                Paragraph(str(val), styles["value"]),
            ])

        right_table = Table(right_rows, colWidths=[0.9 * inch, 2.0 * inch])
        right_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        data = [[left, right_table]]
        t = Table(data, colWidths=[4.0 * inch, 3.0 * inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    def _build_period_banner(self, invoice: Invoice, styles: dict):
        """Colored banner showing the billing period."""
        text = f"Billing Period: {invoice.period_label}"
        if invoice.period_start and invoice.period_end:
            text += f"  ({invoice.period_start} — {invoice.period_end})"

        data = [[Paragraph(text, styles["period_banner"])]]
        t = Table(data, colWidths=[7.0 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self.theme.highlight),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        return t

    def _build_line_items(self, invoice: Invoice, styles: dict):
        """The main fee table."""
        # Header row
        header = [
            Paragraph("Description", styles["table_header"]),
            Paragraph("Basis", styles["table_header_right"]),
            Paragraph("Rate", styles["table_header_right"]),
            Paragraph("Qty", styles["table_header_right"]),
            Paragraph("Amount", styles["table_header_right"]),
        ]

        rows = [header]

        for item in invoice.line_items:
            # Format basis
            if item.basis > 0:
                basis_str = f"${item.basis:,.2f}"
            else:
                basis_str = "—"

            # Format rate
            if item.unit_label == "% of AUM" or item.unit_label == "percent":
                rate_str = f"{item.rate}%"
            elif item.unit_label == "per trade":
                rate_str = f"${item.rate:.2f}/trade"
            elif item.rate > 0:
                rate_str = f"${item.rate:,.2f}"
            else:
                rate_str = "—"

            # Format quantity
            qty_str = f"{item.quantity:g}" if item.quantity != 1 else "—"

            row = [
                [
                    Paragraph(item.description, styles["cell"]),
                    Paragraph(item.notes, styles["cell_desc"]) if item.notes else Spacer(1, 0),
                ],
                Paragraph(basis_str, styles["cell_right"]),
                Paragraph(rate_str, styles["cell_right"]),
                Paragraph(qty_str, styles["cell_right"]),
                Paragraph(f"${item.amount:,.2f}", styles["cell_right"]),
            ]
            rows.append(row)

        col_widths = [3.0 * inch, 1.1 * inch, 0.9 * inch, 0.5 * inch, 1.1 * inch]
        t = Table(rows, colWidths=col_widths, repeatRows=1)

        # Style
        style_cmds = [
            # Header — clean light background
            ("BACKGROUND", (0, 0), (-1, 0), self.theme.bg_light),
            ("TEXTCOLOR", (0, 0), (-1, 0), self.theme.text_medium),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            # Body
            ("VALIGN", (0, 1), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 1), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            # Subtle grid lines
            ("LINEBELOW", (0, 0), (-1, 0), 1, self.theme.line_color),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, self.theme.line_color),
        ]

        # Alternating row backgrounds
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style_cmds.append(
                    ("BACKGROUND", (0, i), (-1, i), self.theme.bg_light)
                )

        t.setStyle(TableStyle(style_cmds))
        return t

    def _build_totals(self, invoice: Invoice, styles: dict):
        """Subtotal, tax, and total aligned to the right."""
        rows = []

        rows.append([
            "",
            Paragraph("Subtotal", styles["total_label"]),
            Paragraph(f"${invoice.subtotal:,.2f}", styles["total_value"]),
        ])

        if invoice.tax_rate > 0:
            rows.append([
                "",
                Paragraph(f"Tax ({invoice.tax_rate}%)", styles["total_label"]),
                Paragraph(f"${invoice.tax_amount:,.2f}", styles["total_value"]),
            ])

        rows.append([
            "",
            Paragraph("TOTAL DUE", styles["grand_total_label"]),
            Paragraph(f"${invoice.total:,.2f}", styles["grand_total_value"]),
        ])

        t = Table(rows, colWidths=[3.5 * inch, 2.0 * inch, 1.5 * inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            # Line above grand total
            ("LINEABOVE", (1, -1), (-1, -1), 1.5, self.theme.primary),
            ("TOPPADDING", (0, -1), (-1, -1), 8),
        ]))
        return t
