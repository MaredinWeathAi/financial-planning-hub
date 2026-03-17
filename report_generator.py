"""
Premium Financial Report Generator — Maredin Wealth Advisors

Generates beautiful, Black Diamond-quality client financial reports using ReportLab.
Inspired by modern wealth management platforms like Black Diamond, Orion, and
eMoney Advisor — with clean typography, visual charts, and clear data hierarchy.

Usage:
    from report_generator import generate_client_report
    generate_client_report(client_data, output_path="report.pdf")
"""

import os
import io
import math
import textwrap
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak, Image, Frame, PageTemplate,
    BaseDocTemplate, NextPageTemplate
)
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, Circle, String, Line, Wedge, Group
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics import renderPDF


# ═══════════════════════════════════════════════════════════════════
# Design Tokens
# ═══════════════════════════════════════════════════════════════════

class Theme:
    """Refined, modern color palette — light and clean."""
    # Primary brand
    navy = colors.HexColor("#1a1a2e")
    navy_light = colors.HexColor("#2d2d4a")
    navy_muted = colors.HexColor("#4a4a6a")

    # Accent
    blue = colors.HexColor("#2563eb")
    blue_light = colors.HexColor("#dbeafe")
    blue_bg = colors.HexColor("#f0f4ff")

    # Neutral
    white = colors.white
    off_white = colors.HexColor("#fafbfc")
    gray_50 = colors.HexColor("#f8fafc")
    gray_100 = colors.HexColor("#f1f5f9")
    gray_200 = colors.HexColor("#e2e8f0")
    gray_300 = colors.HexColor("#cbd5e1")
    gray_400 = colors.HexColor("#94a3b8")
    gray_500 = colors.HexColor("#64748b")
    gray_600 = colors.HexColor("#475569")
    gray_700 = colors.HexColor("#334155")
    gray_800 = colors.HexColor("#1e293b")
    gray_900 = colors.HexColor("#0f172a")

    # Semantic
    emerald = colors.HexColor("#10b981")
    emerald_light = colors.HexColor("#d1fae5")
    amber = colors.HexColor("#f59e0b")
    amber_light = colors.HexColor("#fef3c7")
    red = colors.HexColor("#ef4444")
    red_light = colors.HexColor("#fee2e2")
    purple = colors.HexColor("#8b5cf6")
    purple_light = colors.HexColor("#ede9fe")
    teal = colors.HexColor("#14b8a6")
    rose = colors.HexColor("#f43f5e")

    # Brand gold (sparingly)
    gold = colors.HexColor("#b8964e")
    gold_light = colors.HexColor("#f5f0e6")

    # Chart palette
    chart_colors = [
        colors.HexColor("#2563eb"),  # Blue
        colors.HexColor("#10b981"),  # Emerald
        colors.HexColor("#f59e0b"),  # Amber
        colors.HexColor("#8b5cf6"),  # Purple
        colors.HexColor("#ec4899"),  # Pink
        colors.HexColor("#14b8a6"),  # Teal
        colors.HexColor("#f97316"),  # Orange
        colors.HexColor("#6366f1"),  # Indigo
        colors.HexColor("#84cc16"),  # Lime
        colors.HexColor("#06b6d4"),  # Cyan
    ]


T = Theme  # Shorthand


# ═══════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PersonInfo:
    name: str = ""
    dob: str = ""
    age: int = 0
    employment_status: str = ""
    annual_income: float = 0.0
    retirement_age: int = 67

@dataclass
class AccountInfo:
    name: str = ""
    owner: str = ""
    account_type: str = ""  # e.g., "IRA", "401(k)", "Brokerage", "Roth IRA"
    balance: float = 0.0
    institution: str = ""

@dataclass
class AllocationItem:
    asset_class: str = ""
    current_pct: float = 0.0
    target_pct: float = 0.0
    current_value: float = 0.0

@dataclass
class GoalInfo:
    name: str = ""
    category: str = "Needs"  # Needs, Wants, Wishes
    target_amount: float = 0.0
    funded_pct: float = 0.0
    target_year: int = 0
    annual_cost: float = 0.0
    notes: str = ""

@dataclass
class PerformanceData:
    period: str = ""  # "1M", "3M", "YTD", "1Y", "3Y", "5Y", "10Y", "Inception"
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0

@dataclass
class ClientReportData:
    """All data needed to generate a comprehensive client report."""
    # Header
    report_title: str = "Financial Goal Plan"
    report_date: str = ""
    advisor_name: str = "Marcelo Zinn"
    advisor_title: str = "Wealth Advisor"
    firm_name: str = "Maredin Wealth Advisors"
    firm_tagline: str = "Independent  |  Fiduciary  |  Focused"

    # Personal
    client_names: str = ""  # e.g., "Eduardo and Adriana Lapeira"
    person1: PersonInfo = field(default_factory=PersonInfo)
    person2: Optional[PersonInfo] = None
    dependents: List[Dict] = field(default_factory=list)
    filing_status: str = "Married Filing Jointly"
    state: str = "Florida"

    # Net Worth
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    net_worth: float = 0.0
    accounts: List[AccountInfo] = field(default_factory=list)

    # Allocation
    allocation: List[AllocationItem] = field(default_factory=list)
    risk_score: int = 0  # 1-10 scale
    risk_label: str = ""  # e.g., "Moderate Growth"

    # Goals
    goals: List[GoalInfo] = field(default_factory=list)
    overall_goal_funded: float = 0.0  # 0-100
    monte_carlo_success: float = 0.0  # 0-100

    # Performance
    performance: List[PerformanceData] = field(default_factory=list)
    monthly_returns: List[float] = field(default_factory=list)  # 12 months
    monthly_labels: List[str] = field(default_factory=list)

    # Income & Expenses
    total_annual_income: float = 0.0
    total_annual_expenses: float = 0.0
    social_security_p1: float = 0.0
    social_security_p2: float = 0.0

    # Insurance
    life_insurance_coverage: float = 0.0
    disability_coverage: bool = False
    ltc_coverage: bool = False

    # Estate
    estate_value: float = 0.0
    has_will: bool = False
    has_trust: bool = False
    has_poa: bool = False
    has_healthcare_directive: bool = False

    # Notes / Recommendations
    key_recommendations: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# PDF Builder
# ═══════════════════════════════════════════════════════════════════

class PremiumReportBuilder:
    """Builds a high-end, multi-page financial report PDF."""

    PAGE_W, PAGE_H = landscape(letter)  # 792 x 612 (landscape 8.5x11)
    MARGIN = 0.7 * inch
    CONTENT_W = PAGE_W - 2 * MARGIN

    def __init__(self, data: ClientReportData, output_path: str):
        self.data = data
        self.output_path = output_path
        self.styles = self._build_styles()
        self.story = []
        self._page_number = 0

    # ─── Style Definitions ──────────────────────────────────────

    def _build_styles(self):
        base = getSampleStyleSheet()
        s = {}

        s["h1"] = ParagraphStyle("H1", parent=base["Normal"],
            fontSize=22, leading=28, fontName="Helvetica-Bold",
            textColor=T.navy, spaceBefore=0, spaceAfter=8)

        s["h2"] = ParagraphStyle("H2", parent=base["Normal"],
            fontSize=16, leading=20, fontName="Helvetica-Bold",
            textColor=T.navy, spaceBefore=20, spaceAfter=8)

        s["h3"] = ParagraphStyle("H3", parent=base["Normal"],
            fontSize=12, leading=16, fontName="Helvetica-Bold",
            textColor=T.gray_700, spaceBefore=14, spaceAfter=4)

        s["body"] = ParagraphStyle("Body", parent=base["Normal"],
            fontSize=10, leading=15, fontName="Helvetica",
            textColor=T.gray_600, spaceAfter=6)

        s["body_sm"] = ParagraphStyle("BodySm", parent=base["Normal"],
            fontSize=9, leading=13, fontName="Helvetica",
            textColor=T.gray_500)

        s["metric_value"] = ParagraphStyle("MetricValue", parent=base["Normal"],
            fontSize=24, leading=28, fontName="Helvetica-Bold",
            textColor=T.navy)

        s["metric_label"] = ParagraphStyle("MetricLabel", parent=base["Normal"],
            fontSize=9, leading=12, fontName="Helvetica",
            textColor=T.gray_400, spaceAfter=2)

        s["metric_change"] = ParagraphStyle("MetricChange", parent=base["Normal"],
            fontSize=9, leading=12, fontName="Helvetica-Bold",
            textColor=T.emerald)

        s["section_label"] = ParagraphStyle("SectionLabel", parent=base["Normal"],
            fontSize=8, leading=10, fontName="Helvetica-Bold",
            textColor=T.gray_400, spaceBefore=0, spaceAfter=2)

        s["table_header"] = ParagraphStyle("TH", parent=base["Normal"],
            fontSize=8, leading=10, fontName="Helvetica-Bold",
            textColor=T.gray_500)

        s["table_header_r"] = ParagraphStyle("THR", parent=s["table_header"],
            alignment=TA_RIGHT)

        s["td"] = ParagraphStyle("TD", parent=base["Normal"],
            fontSize=9, leading=13, fontName="Helvetica",
            textColor=T.gray_700)

        s["td_r"] = ParagraphStyle("TDR", parent=s["td"], alignment=TA_RIGHT)

        s["td_bold"] = ParagraphStyle("TDBold", parent=s["td"],
            fontName="Helvetica-Bold", textColor=T.navy)

        s["td_bold_r"] = ParagraphStyle("TDBoldR", parent=s["td_bold"],
            alignment=TA_RIGHT)

        s["footer"] = ParagraphStyle("Footer", parent=base["Normal"],
            fontSize=7, leading=9, fontName="Helvetica",
            textColor=T.gray_400, alignment=TA_CENTER)

        s["cover_title"] = ParagraphStyle("CoverTitle", parent=base["Normal"],
            fontSize=32, leading=38, fontName="Helvetica-Bold",
            textColor=T.navy)

        s["cover_subtitle"] = ParagraphStyle("CoverSub", parent=base["Normal"],
            fontSize=16, leading=22, fontName="Helvetica",
            textColor=T.gray_500)

        s["cover_detail"] = ParagraphStyle("CoverDetail", parent=base["Normal"],
            fontSize=11, leading=16, fontName="Helvetica",
            textColor=T.gray_600)

        s["toc_item"] = ParagraphStyle("TocItem", parent=base["Normal"],
            fontSize=11, leading=22, fontName="Helvetica",
            textColor=T.gray_700)

        s["toc_section"] = ParagraphStyle("TocSection", parent=base["Normal"],
            fontSize=11, leading=22, fontName="Helvetica-Bold",
            textColor=T.blue)

        s["callout"] = ParagraphStyle("Callout", parent=base["Normal"],
            fontSize=10, leading=15, fontName="Helvetica",
            textColor=T.blue, leftIndent=12)

        s["disclaimer"] = ParagraphStyle("Disclaimer", parent=base["Normal"],
            fontSize=7.5, leading=10.5, fontName="Helvetica",
            textColor=T.gray_400, alignment=TA_JUSTIFY)

        return s

    # ─── Utility Drawing Helpers ────────────────────────────────

    def _draw_rounded_rect(self, d, x, y, w, h, r=6, fill=T.white, stroke=T.gray_200):
        """Draw a rounded rectangle on a Drawing."""
        rect = Rect(x, y, w, h, rx=r, ry=r,
                     fillColor=fill, strokeColor=stroke, strokeWidth=0.5)
        d.add(rect)

    def _fmt_currency(self, val, decimals=0):
        if val >= 1_000_000:
            return f"${val / 1_000_000:,.{decimals}f}M"
        elif val >= 1_000:
            return f"${val / 1_000:,.{decimals}f}K"
        else:
            return f"${val:,.{decimals}f}"

    def _fmt_pct(self, val, decimals=1):
        return f"{val:.{decimals}f}%"

    # ─── Page Components ────────────────────────────────────────

    def _add_section_header(self, title, subtitle=None):
        """Section header with accent line."""
        self.story.append(Spacer(1, 4))

        d = Drawing(self.CONTENT_W, 3)
        d.add(Rect(0, 0, self.CONTENT_W, 3, fillColor=T.blue, strokeColor=None))
        self.story.append(d)
        self.story.append(Spacer(1, 12))

        self.story.append(Paragraph(title, self.styles["h1"]))
        if subtitle:
            self.story.append(Paragraph(subtitle, self.styles["body"]))
        self.story.append(Spacer(1, 8))

    def _add_divider(self, color=None):
        self.story.append(Spacer(1, 8))
        self.story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=color or T.gray_200, spaceAfter=8
        ))

    def _metric_card_row(self, metrics):
        """
        Create a row of metric cards.
        metrics: list of (label, value, change_text, change_positive)
        """
        n = len(metrics)
        card_w = (self.CONTENT_W - (n - 1) * 10) / n

        cells = []
        for label, value, change, positive in metrics:
            change_color = T.emerald if positive else T.red
            change_style = ParagraphStyle("ch", parent=self.styles["metric_change"],
                                          textColor=change_color)
            cell_content = [
                Paragraph(label.upper(), self.styles["section_label"]),
                Spacer(1, 4),
                Paragraph(str(value), self.styles["metric_value"]),
                Spacer(1, 2),
                Paragraph(str(change), change_style),
            ]
            cells.append(cell_content)

        col_widths = [card_w] * n
        t = Table([cells], colWidths=col_widths)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("TOPPADDING", (0, 0), (-1, -1), 16),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ("BACKGROUND", (0, 0), (-1, -1), T.white),
            ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
        ]))
        self.story.append(t)
        self.story.append(Spacer(1, 16))

    # ─── Cover Page ─────────────────────────────────────────────

    def _build_cover(self):
        """Premium cover page with clean geometric design."""
        self.story.append(Spacer(1, 0.8 * inch))

        # Firm name
        firm_style = ParagraphStyle("FirmName", parent=self.styles["cover_detail"],
            fontSize=14, fontName="Helvetica-Bold", textColor=T.navy,
            spaceAfter=2)
        self.story.append(Paragraph(self.data.firm_name.upper(), firm_style))

        tagline_style = ParagraphStyle("Tagline", parent=self.styles["body_sm"],
            fontSize=9, textColor=T.gray_400, letterSpacing=2)
        self.story.append(Paragraph(self.data.firm_tagline, tagline_style))

        self.story.append(Spacer(1, 0.3 * inch))

        # Accent line
        d = Drawing(self.CONTENT_W, 4)
        d.add(Rect(0, 0, 100, 4, fillColor=T.blue, strokeColor=None))
        self.story.append(d)

        self.story.append(Spacer(1, 0.25 * inch))

        # Title — larger for landscape
        cover_title_lg = ParagraphStyle("CoverTitleLg", parent=self.styles["cover_title"],
            fontSize=36, leading=42)
        self.story.append(Paragraph(self.data.report_title, cover_title_lg))
        self.story.append(Spacer(1, 8))
        self.story.append(Paragraph(self.data.client_names, self.styles["cover_subtitle"]))

        self.story.append(Spacer(1, 0.8 * inch))

        # Prepared by block
        detail = self.styles["cover_detail"]
        label = ParagraphStyle("CoverLabel", parent=detail,
            fontSize=9, textColor=T.gray_400, fontName="Helvetica-Bold",
            spaceAfter=4)

        self.story.append(Paragraph("PREPARED BY", label))
        self.story.append(Paragraph(self.data.advisor_name, detail))
        self.story.append(Paragraph(self.data.advisor_title, detail))
        self.story.append(Spacer(1, 16))
        self.story.append(Paragraph("DATE", label))
        report_date = self.data.report_date or datetime.now().strftime("%B %d, %Y")
        self.story.append(Paragraph(report_date, detail))

        self.story.append(Spacer(1, 0.6 * inch))

        # Bottom accent bar
        d2 = Drawing(self.CONTENT_W, 6)
        d2.add(Rect(0, 0, self.CONTENT_W, 6, fillColor=T.navy, strokeColor=None))
        self.story.append(d2)

        self.story.append(PageBreak())

    # ─── Table of Contents ──────────────────────────────────────

    def _build_toc(self):
        self._add_section_header("Contents")

        sections = [
            ("01", "Executive Summary", "Your financial snapshot at a glance"),
            ("02", "Personal Information", "Household details and dependents"),
            ("03", "Net Worth Overview", "Assets, liabilities, and net worth breakdown"),
            ("04", "Portfolio Allocation", "Current allocation and risk profile"),
            ("05", "Investment Performance", "Portfolio returns vs. benchmark"),
            ("06", "Financial Goals", "Goal progress and funding status"),
            ("07", "Retirement Projection", "Monte Carlo analysis and income timeline"),
            ("08", "Risk Management", "Insurance and estate planning checklist"),
            ("09", "Recommendations", "Key action items and next steps"),
            ("10", "Important Disclosures", "Assumptions, limitations, and methodology"),
        ]

        toc_title_style = ParagraphStyle("TocTitle", parent=self.styles["toc_section"],
            leading=18, spaceBefore=0, spaceAfter=0)
        toc_desc_style = ParagraphStyle("TocDesc", parent=self.styles["body_sm"],
            leading=11, spaceBefore=0, spaceAfter=0)

        for num, title, desc in sections:
            row_data = [[
                Paragraph(f'<font color="#{T.blue.hexval()[2:]}">{num}</font>',
                    ParagraphStyle("TocNum", fontSize=11, fontName="Helvetica-Bold",
                                   textColor=T.blue, leading=16)),
                [
                    Paragraph(title, toc_title_style),
                    Paragraph(desc, toc_desc_style),
                ],
            ]]
            t = Table(row_data, colWidths=[40, self.CONTENT_W - 40])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, T.gray_100),
            ]))
            self.story.append(t)

        self.story.append(PageBreak())

    # ─── Executive Summary ──────────────────────────────────────

    def _build_executive_summary(self):
        self._add_section_header(
            "Executive Summary",
            f"Financial overview for {self.data.client_names} as of {self.data.report_date or datetime.now().strftime('%B %d, %Y')}"
        )

        # KPI cards — use abbreviated format for values ≥ $100K to prevent wrapping
        nw = self.data.net_worth
        nw_str = self._fmt_currency(nw, 2) if nw >= 100_000 else f"${nw:,.0f}"
        assets_str = self._fmt_currency(self.data.total_assets, 2) if self.data.total_assets >= 100_000 else f"${self.data.total_assets:,.0f}"

        self._metric_card_row([
            ("Net Worth", nw_str, "Total assets minus liabilities", True),
            ("Total Assets", assets_str, f"{len(self.data.accounts)} accounts", True),
            ("Goal Funded", self._fmt_pct(self.data.overall_goal_funded, 0),
             f"{self.data.monte_carlo_success:.0f}% Monte Carlo success", self.data.overall_goal_funded >= 80),
            ("Risk Score", f"{self.data.risk_score}/10",
             self.data.risk_label, True),
        ])

        # ── Two side-by-side mini charts: Allocation donut + Income vs Expenses ──
        mini_chart_cells = []

        # Mini allocation donut
        if self.data.allocation:
            donut = Drawing(280, 140)
            pie = Pie()
            pie.x = 40
            pie.y = 10
            pie.width = 110
            pie.height = 110
            pie.data = [a.current_pct for a in self.data.allocation if a.current_pct > 0]
            pie.labels = None
            # Note: donut style not available in this ReportLab version
            pie.sideLabels = False
            pie.simpleLabels = False
            visible_alloc = [a for a in self.data.allocation if a.current_pct > 0]
            for i in range(len(pie.data)):
                pie.slices[i].fillColor = T.chart_colors[i % len(T.chart_colors)]
                pie.slices[i].strokeColor = T.white
                pie.slices[i].strokeWidth = 1.5
            donut.add(pie)
            # Top 4 legend items
            lx = 165
            for i, a in enumerate(visible_alloc[:5]):
                ly = 120 - i * 18
                c = T.chart_colors[i % len(T.chart_colors)]
                donut.add(Rect(lx, ly, 8, 8, fillColor=c, strokeColor=None, rx=2, ry=2))
                donut.add(String(lx + 12, ly + 1, f"{a.asset_class} ({a.current_pct:.0f}%)",
                    fontName="Helvetica", fontSize=7.5, fillColor=T.gray_600))
            mini_chart_cells.append([
                Paragraph("ASSET ALLOCATION", self.styles["section_label"]),
                Spacer(1, 4),
                donut,
            ])

        # Income vs Expenses bar comparison
        if self.data.total_annual_income > 0:
            ie_d = Drawing(280, 140)
            # Income bar
            max_val = max(self.data.total_annual_income, self.data.total_annual_expenses)
            bar_max_w = 200
            inc_w = (self.data.total_annual_income / max_val) * bar_max_w if max_val > 0 else 0
            exp_w = (self.data.total_annual_expenses / max_val) * bar_max_w if max_val > 0 else 0
            savings = self.data.total_annual_income - self.data.total_annual_expenses
            sav_w = (savings / max_val) * bar_max_w if max_val > 0 and savings > 0 else 0

            y_base = 90
            ie_d.add(String(10, y_base + 14, "Income", fontName="Helvetica", fontSize=8, fillColor=T.gray_500))
            ie_d.add(Rect(60, y_base + 8, inc_w, 16, fillColor=T.emerald, strokeColor=None, rx=4, ry=4))
            ie_d.add(String(65 + inc_w, y_base + 12, self._fmt_currency(self.data.total_annual_income),
                fontName="Helvetica-Bold", fontSize=8, fillColor=T.gray_700))

            y_base -= 30
            ie_d.add(String(10, y_base + 14, "Expenses", fontName="Helvetica", fontSize=8, fillColor=T.gray_500))
            ie_d.add(Rect(60, y_base + 8, exp_w, 16, fillColor=T.amber, strokeColor=None, rx=4, ry=4))
            ie_d.add(String(65 + exp_w, y_base + 12, self._fmt_currency(self.data.total_annual_expenses),
                fontName="Helvetica-Bold", fontSize=8, fillColor=T.gray_700))

            if savings > 0:
                y_base -= 30
                ie_d.add(String(10, y_base + 14, "Savings", fontName="Helvetica", fontSize=8, fillColor=T.gray_500))
                ie_d.add(Rect(60, y_base + 8, sav_w, 16, fillColor=T.blue, strokeColor=None, rx=4, ry=4))
                ie_d.add(String(65 + sav_w, y_base + 12, self._fmt_currency(savings),
                    fontName="Helvetica-Bold", fontSize=8, fillColor=T.gray_700))

                # Savings rate
                rate = (savings / self.data.total_annual_income * 100)
                ie_d.add(String(10, 10, f"Savings Rate: {rate:.0f}%",
                    fontName="Helvetica-Bold", fontSize=9, fillColor=T.blue))

            mini_chart_cells.append([
                Paragraph("INCOME VS. EXPENSES", self.styles["section_label"]),
                Spacer(1, 4),
                ie_d,
            ])

        if mini_chart_cells:
            col_w = (self.CONTENT_W - 16) / max(len(mini_chart_cells), 1)
            mc_table = Table([mini_chart_cells], colWidths=[col_w] * len(mini_chart_cells))
            mc_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("BACKGROUND", (0, 0), (-1, -1), T.white),
                ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
                ("LINEBEFORE", (1, 0), (1, -1), 0.5, T.gray_200),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ]))
            self.story.append(mc_table)
            self.story.append(Spacer(1, 16))

        # Two-column: Goals overview + Allocation summary
        if self.data.goals:
            goal_rows = []
            for g in self.data.goals[:6]:
                pct = g.funded_pct
                bar_color = T.emerald if pct >= 90 else (T.amber if pct >= 60 else T.red)
                status = "On Track" if pct >= 90 else ("Monitor" if pct >= 60 else "Action Needed")
                goal_rows.append([
                    Paragraph(g.name, self.styles["td_bold"]),
                    Paragraph(g.category, self.styles["td"]),
                    Paragraph(self._fmt_pct(pct, 0), self.styles["td_r"]),
                    Paragraph(status, ParagraphStyle("st", parent=self.styles["td"],
                        textColor=bar_color, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
                ])

            header = [
                Paragraph("Goal", self.styles["table_header"]),
                Paragraph("Priority", self.styles["table_header"]),
                Paragraph("Funded", self.styles["table_header_r"]),
                Paragraph("Status", self.styles["table_header_r"]),
            ]
            goal_rows.insert(0, header)

            t = Table(goal_rows, colWidths=[
                self.CONTENT_W * 0.35,
                self.CONTENT_W * 0.20,
                self.CONTENT_W * 0.20,
                self.CONTENT_W * 0.25,
            ])
            style_cmds = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
                ("LINEBELOW", (0, 0), (-1, 0), 1, T.gray_200),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, T.gray_100),
                ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
            t.setStyle(TableStyle(style_cmds))

            self.story.append(Paragraph("Goal Progress Summary", self.styles["h3"]))
            self.story.append(Spacer(1, 6))
            self.story.append(t)

        self.story.append(PageBreak())

    # ─── Personal Information ───────────────────────────────────

    def _build_personal_info(self):
        self._add_section_header("Personal Information",
            "Household details as provided")

        # Person info cards side by side
        persons = [self.data.person1]
        if self.data.person2 and self.data.person2.name:
            persons.append(self.data.person2)

        person_cells = []
        for p in persons:
            cell = [
                Paragraph(p.name, self.styles["td_bold"]),
                Spacer(1, 4),
                Paragraph(f"Date of Birth: {p.dob}", self.styles["body_sm"]),
                Paragraph(f"Age: {p.age}", self.styles["body_sm"]),
                Paragraph(f"Employment: {p.employment_status}", self.styles["body_sm"]),
                Paragraph(f"Annual Income: ${p.annual_income:,.0f}", self.styles["body_sm"]),
                Paragraph(f"Planned Retirement Age: {p.retirement_age}", self.styles["body_sm"]),
            ]
            person_cells.append(cell)

        if len(person_cells) == 1:
            person_cells.append([])  # Empty second column

        col_w = (self.CONTENT_W - 16) / 2
        t = Table([person_cells], colWidths=[col_w, col_w])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("TOPPADDING", (0, 0), (-1, -1), 16),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ("BACKGROUND", (0, 0), (-1, -1), T.white),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
            ("LINEBEFORE", (1, 0), (1, -1), 0.5, T.gray_200),
            ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ]))
        self.story.append(t)
        self.story.append(Spacer(1, 16))

        # Key facts
        facts_data = [
            ("Filing Status", self.data.filing_status),
            ("State of Residence", self.data.state),
            ("Social Security (P1)", f"${self.data.social_security_p1:,.0f}/yr at age {self.data.person1.retirement_age}"),
        ]
        if self.data.person2 and self.data.person2.name:
            facts_data.append(
                ("Social Security (P2)", f"${self.data.social_security_p2:,.0f}/yr at age {self.data.person2.retirement_age}")
            )

        rows = [[
            Paragraph("Item", self.styles["table_header"]),
            Paragraph("Detail", self.styles["table_header"]),
        ]]
        for label, val in facts_data:
            rows.append([
                Paragraph(label, self.styles["td"]),
                Paragraph(val, self.styles["td_bold"]),
            ])

        t2 = Table(rows, colWidths=[self.CONTENT_W * 0.35, self.CONTENT_W * 0.65])
        t2.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, T.gray_100),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        self.story.append(Paragraph("Key Facts", self.styles["h3"]))
        self.story.append(Spacer(1, 6))
        self.story.append(t2)

        # Dependents
        if self.data.dependents:
            self.story.append(Spacer(1, 16))
            self.story.append(Paragraph("Dependents", self.styles["h3"]))
            self.story.append(Spacer(1, 6))

            dep_rows = [[
                Paragraph("Name", self.styles["table_header"]),
                Paragraph("Date of Birth", self.styles["table_header"]),
                Paragraph("Age", self.styles["table_header"]),
                Paragraph("Relationship", self.styles["table_header"]),
            ]]
            for dep in self.data.dependents:
                dep_rows.append([
                    Paragraph(dep.get("name", ""), self.styles["td"]),
                    Paragraph(dep.get("dob", ""), self.styles["td"]),
                    Paragraph(str(dep.get("age", "")), self.styles["td"]),
                    Paragraph(dep.get("relationship", ""), self.styles["td"]),
                ])
            dt = Table(dep_rows, colWidths=[
                self.CONTENT_W * 0.30, self.CONTENT_W * 0.25,
                self.CONTENT_W * 0.15, self.CONTENT_W * 0.30])
            dt.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, T.gray_100),
                ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]))
            self.story.append(dt)

        self.story.append(PageBreak())

    # ─── Net Worth ──────────────────────────────────────────────

    def _build_net_worth(self):
        self._add_section_header("Net Worth Overview",
            f"As of {self.data.report_date or datetime.now().strftime('%B %d, %Y')}")

        # Big numbers — abbreviated format for large values
        a = self.data.total_assets
        l = self.data.total_liabilities
        n = self.data.net_worth
        self._metric_card_row([
            ("Total Assets", self._fmt_currency(a, 2) if a >= 100_000 else f"${a:,.0f}",
             f"{len(self.data.accounts)} accounts", True),
            ("Total Liabilities", self._fmt_currency(l, 2) if l >= 100_000 else f"${l:,.0f}",
             "", l == 0),
            ("Net Worth", self._fmt_currency(n, 2) if n >= 100_000 else f"${n:,.0f}",
             "", n > 0),
        ])

        # Net worth bar visualization
        if self.data.total_assets > 0:
            bar_w = self.CONTENT_W - 40
            d = Drawing(self.CONTENT_W, 60)

            # Background
            self._draw_rounded_rect(d, 20, 10, bar_w, 40, r=6, fill=T.gray_50, stroke=T.gray_200)

            total = max(self.data.total_assets, self.data.total_liabilities + self.data.net_worth)
            asset_w = (self.data.total_assets / total) * (bar_w - 8) if total > 0 else 0
            liab_w = (self.data.total_liabilities / total) * (bar_w - 8) if total > 0 else 0

            # Asset bar
            if asset_w > 0:
                d.add(Rect(24, 14, asset_w, 16, fillColor=T.emerald, strokeColor=None, rx=3, ry=3))
            # Liability bar (stacked above)
            if liab_w > 0:
                d.add(Rect(24, 32, liab_w, 14, fillColor=T.red, strokeColor=None, rx=3, ry=3))

            # Legend
            d.add(Rect(24, 0, 8, 8, fillColor=T.emerald, strokeColor=None))
            d.add(String(36, 1, "Assets", fontName="Helvetica", fontSize=7, fillColor=T.gray_500))
            d.add(Rect(84, 0, 8, 8, fillColor=T.red, strokeColor=None))
            d.add(String(96, 1, "Liabilities", fontName="Helvetica", fontSize=7, fillColor=T.gray_500))
            d.add(Rect(164, 0, 8, 8, fillColor=T.blue, strokeColor=None))
            d.add(String(176, 1, "Net Worth", fontName="Helvetica", fontSize=7, fillColor=T.gray_500))

            self.story.append(d)
            self.story.append(Spacer(1, 16))

        # ── Account balance horizontal bar chart ──
        if self.data.accounts:
            self.story.append(Paragraph("Account Balances", self.styles["h3"]))
            self.story.append(Spacer(1, 6))

            sorted_accts = sorted(self.data.accounts, key=lambda x: x.balance, reverse=True)
            max_balance = max(a.balance for a in sorted_accts) if sorted_accts else 1
            bar_chart_h = len(sorted_accts) * 24 + 20
            acct_d = Drawing(self.CONTENT_W, bar_chart_h)

            chart_left = 140  # Space for account names
            chart_right = self.CONTENT_W - 80  # Space for values on right
            chart_w = chart_right - chart_left

            for i, acct in enumerate(sorted_accts):
                y = bar_chart_h - 18 - i * 24
                # Account name
                acct_d.add(String(5, y + 2, acct.name[:22],
                    fontName="Helvetica", fontSize=8, fillColor=T.gray_600))
                # Bar
                bw = (acct.balance / max_balance) * chart_w if max_balance > 0 else 0
                bar_color = T.chart_colors[i % len(T.chart_colors)]
                acct_d.add(Rect(chart_left, y, bw, 14, fillColor=bar_color, strokeColor=None, rx=3, ry=3))
                # Value
                acct_d.add(String(chart_right + 8, y + 2, f"${acct.balance:,.0f}",
                    fontName="Helvetica-Bold", fontSize=8, fillColor=T.gray_700))

            self.story.append(acct_d)
            self.story.append(Spacer(1, 16))

        # Account detail table
        if self.data.accounts:
            self.story.append(Paragraph("Account Detail", self.styles["h3"]))
            self.story.append(Spacer(1, 6))

            rows = [[
                Paragraph("Account", self.styles["table_header"]),
                Paragraph("Owner", self.styles["table_header"]),
                Paragraph("Type", self.styles["table_header"]),
                Paragraph("Institution", self.styles["table_header"]),
                Paragraph("Balance", self.styles["table_header_r"]),
            ]]

            for acct in self.data.accounts:
                rows.append([
                    Paragraph(acct.name, self.styles["td_bold"]),
                    Paragraph(acct.owner, self.styles["td"]),
                    Paragraph(acct.account_type, self.styles["td"]),
                    Paragraph(acct.institution, self.styles["td"]),
                    Paragraph(f"${acct.balance:,.0f}", self.styles["td_bold_r"]),
                ])

            # Total row
            total_balance = sum(a.balance for a in self.data.accounts)
            rows.append([
                Paragraph("Total", self.styles["td_bold"]),
                Paragraph("", self.styles["td"]),
                Paragraph("", self.styles["td"]),
                Paragraph("", self.styles["td"]),
                Paragraph(f"${total_balance:,.0f}", self.styles["td_bold_r"]),
            ])

            col_widths = [
                self.CONTENT_W * 0.25, self.CONTENT_W * 0.18,
                self.CONTENT_W * 0.18, self.CONTENT_W * 0.20,
                self.CONTENT_W * 0.19
            ]
            t = Table(rows, colWidths=col_widths)
            style_cmds = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
                ("LINEBELOW", (0, 0), (-1, 0), 1, T.gray_200),
                ("LINEBELOW", (0, 1), (-1, -2), 0.5, T.gray_100),
                ("LINEABOVE", (0, -1), (-1, -1), 1, T.navy),
                ("BACKGROUND", (0, -1), (-1, -1), T.gray_50),
                ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
            # Alternating rows
            for i in range(1, len(rows) - 1):
                if i % 2 == 0:
                    style_cmds.append(("BACKGROUND", (0, i), (-1, i), T.gray_50))
            t.setStyle(TableStyle(style_cmds))
            self.story.append(t)

        self.story.append(PageBreak())

    # ─── Portfolio Allocation ───────────────────────────────────

    def _build_allocation(self):
        self._add_section_header("Portfolio Allocation",
            f"Risk Profile: {self.data.risk_label} (Score {self.data.risk_score}/10)")

        # Pie chart
        if self.data.allocation:
            d = Drawing(self.CONTENT_W, 220)

            pie = Pie()
            pie.x = 80
            pie.y = 20
            pie.width = 180
            pie.height = 180
            pie.data = [a.current_pct for a in self.data.allocation if a.current_pct > 0]
            pie.labels = None
            pie.sideLabels = False
            pie.simpleLabels = False

            # Color slices
            for i in range(len(pie.data)):
                color = T.chart_colors[i % len(T.chart_colors)]
                pie.slices[i].fillColor = color
                pie.slices[i].strokeColor = T.white
                pie.slices[i].strokeWidth = 2

            d.add(pie)

            # Legend on the right — positioned for landscape width
            legend_x = 340
            legend_y = 195
            visible = [a for a in self.data.allocation if a.current_pct > 0]
            for i, a in enumerate(visible):
                y_pos = legend_y - i * 18
                color = T.chart_colors[i % len(T.chart_colors)]
                d.add(Rect(legend_x, y_pos - 2, 10, 10, fillColor=color, strokeColor=None, rx=2, ry=2))
                d.add(String(legend_x + 16, y_pos, a.asset_class,
                             fontName="Helvetica", fontSize=9, fillColor=T.gray_700))
                d.add(String(legend_x + 160, y_pos, f"{a.current_pct:.1f}%",
                             fontName="Helvetica-Bold", fontSize=9, fillColor=T.navy))

            self.story.append(d)
            self.story.append(Spacer(1, 12))

            # Allocation comparison table: Current vs Target
            self.story.append(Paragraph("Current vs. Target Allocation", self.styles["h3"]))
            self.story.append(Spacer(1, 6))

            rows = [[
                Paragraph("Asset Class", self.styles["table_header"]),
                Paragraph("Current %", self.styles["table_header_r"]),
                Paragraph("Target %", self.styles["table_header_r"]),
                Paragraph("Difference", self.styles["table_header_r"]),
                Paragraph("Current Value", self.styles["table_header_r"]),
            ]]
            for a in self.data.allocation:
                diff = a.current_pct - a.target_pct
                diff_color = T.emerald if abs(diff) < 2 else (T.amber if abs(diff) < 5 else T.red)
                diff_style = ParagraphStyle("diff", parent=self.styles["td_r"],
                    textColor=diff_color, fontName="Helvetica-Bold")
                rows.append([
                    Paragraph(a.asset_class, self.styles["td"]),
                    Paragraph(f"{a.current_pct:.1f}%", self.styles["td_r"]),
                    Paragraph(f"{a.target_pct:.1f}%", self.styles["td_r"]),
                    Paragraph(f"{diff:+.1f}%", diff_style),
                    Paragraph(f"${a.current_value:,.0f}", self.styles["td_bold_r"]),
                ])

            t = Table(rows, colWidths=[
                self.CONTENT_W * 0.30, self.CONTENT_W * 0.15,
                self.CONTENT_W * 0.15, self.CONTENT_W * 0.15,
                self.CONTENT_W * 0.25
            ])
            style_cmds = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
                ("LINEBELOW", (0, 0), (-1, 0), 1, T.gray_200),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, T.gray_100),
                ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
            for i in range(1, len(rows)):
                if i % 2 == 0:
                    style_cmds.append(("BACKGROUND", (0, i), (-1, i), T.gray_50))
            t.setStyle(TableStyle(style_cmds))
            self.story.append(t)

        # Risk score visual
        self.story.append(Spacer(1, 20))
        self.story.append(Paragraph("Risk Profile", self.styles["h3"]))
        self.story.append(Spacer(1, 6))

        d2 = Drawing(self.CONTENT_W, 50)

        # Risk scale bar
        bar_x = 20
        bar_y = 25
        bar_w = self.CONTENT_W - 40
        segment_w = bar_w / 10

        for i in range(10):
            # Gradient from green to red
            if i < 3:
                fill = T.emerald
            elif i < 5:
                fill = T.amber
            elif i < 7:
                fill = colors.HexColor("#f97316")
            else:
                fill = T.red
            r = 4 if i in (0, 9) else 0
            d2.add(Rect(bar_x + i * segment_w, bar_y, segment_w - 2, 18,
                       fillColor=fill, strokeColor=None, rx=r, ry=r))
            d2.add(String(bar_x + i * segment_w + segment_w/2 - 3, bar_y + 4,
                         str(i + 1), fontName="Helvetica-Bold", fontSize=8, fillColor=T.white))

        # Marker for current score
        score = max(1, min(10, self.data.risk_score))
        marker_x = bar_x + (score - 0.5) * segment_w
        d2.add(Rect(marker_x - 8, bar_y - 8, 16, 8,
                    fillColor=T.navy, strokeColor=None, rx=2, ry=2))
        # Triangle pointing up
        d2.add(String(marker_x - 3, bar_y - 6, "^", fontName="Helvetica-Bold",
                      fontSize=6, fillColor=T.navy))

        # Labels
        d2.add(String(bar_x, bar_y + 26, "Conservative", fontName="Helvetica", fontSize=7, fillColor=T.gray_400))
        d2.add(String(bar_x + bar_w - 50, bar_y + 26, "Aggressive", fontName="Helvetica", fontSize=7, fillColor=T.gray_400))

        d2.add(String(bar_x, bar_y - 18, f"Your score: {score} — {self.data.risk_label}",
                      fontName="Helvetica-Bold", fontSize=9, fillColor=T.navy))

        self.story.append(d2)

        self.story.append(PageBreak())

    # ─── Performance ──────────────────────────────────────────────

    def _build_performance(self):
        self._add_section_header("Investment Performance",
            f"Portfolio returns vs. benchmark as of {self.data.report_date or datetime.now().strftime('%B %d, %Y')}")

        if not self.data.performance:
            self.story.append(Paragraph("Performance data not yet available.", self.styles["body"]))
            self.story.append(PageBreak())
            return

        # ── Performance bar chart: Portfolio vs Benchmark ──
        chart_h = 200
        d = Drawing(self.CONTENT_W, chart_h + 30)

        bc = VerticalBarChart()
        bc.x = 60
        bc.y = 40
        bc.width = self.CONTENT_W - 120
        bc.height = chart_h - 60

        portfolio_data = [p.portfolio_return for p in self.data.performance]
        benchmark_data = [p.benchmark_return for p in self.data.performance]
        bc.data = [portfolio_data, benchmark_data]

        bc.categoryAxis.categoryNames = [p.period for p in self.data.performance]
        bc.categoryAxis.labels.fontSize = 8
        bc.categoryAxis.labels.fontName = "Helvetica"
        bc.categoryAxis.labels.fillColor = T.gray_500
        bc.categoryAxis.strokeColor = T.gray_200
        bc.categoryAxis.tickDown = 0

        bc.valueAxis.valueMin = 0
        bc.valueAxis.labels.fontSize = 8
        bc.valueAxis.labels.fontName = "Helvetica"
        bc.valueAxis.labels.fillColor = T.gray_500
        bc.valueAxis.strokeColor = T.gray_200
        bc.valueAxis.gridStrokeColor = T.gray_100
        bc.valueAxis.gridStrokeWidth = 0.5
        bc.valueAxis.visibleGrid = True

        bc.bars[0].fillColor = T.blue
        bc.bars[0].strokeColor = None
        bc.bars[0].strokeWidth = 0
        bc.bars[1].fillColor = T.gray_300
        bc.bars[1].strokeColor = None
        bc.bars[1].strokeWidth = 0

        bc.barWidth = 16
        bc.groupSpacing = 20
        bc.barSpacing = 3

        d.add(bc)

        # Legend
        lx = bc.x
        ly = chart_h + 10
        d.add(Rect(lx, ly, 10, 10, fillColor=T.blue, strokeColor=None, rx=2, ry=2))
        d.add(String(lx + 14, ly + 1, "Portfolio", fontName="Helvetica", fontSize=8, fillColor=T.gray_600))
        d.add(Rect(lx + 80, ly, 10, 10, fillColor=T.gray_300, strokeColor=None, rx=2, ry=2))
        d.add(String(lx + 94, ly + 1, "Benchmark", fontName="Helvetica", fontSize=8, fillColor=T.gray_600))

        self.story.append(d)
        self.story.append(Spacer(1, 20))

        # ── Performance data table ──
        self.story.append(Paragraph("Return Comparison", self.styles["h3"]))
        self.story.append(Spacer(1, 6))

        rows = [[
            Paragraph("Period", self.styles["table_header"]),
            Paragraph("Portfolio", self.styles["table_header_r"]),
            Paragraph("Benchmark", self.styles["table_header_r"]),
            Paragraph("Difference", self.styles["table_header_r"]),
        ]]
        for p in self.data.performance:
            diff = p.portfolio_return - p.benchmark_return
            diff_color = T.emerald if diff >= 0 else T.red
            diff_style = ParagraphStyle("pdiff", parent=self.styles["td_r"],
                textColor=diff_color, fontName="Helvetica-Bold")
            rows.append([
                Paragraph(p.period, self.styles["td_bold"]),
                Paragraph(f"{p.portfolio_return:.1f}%", self.styles["td_r"]),
                Paragraph(f"{p.benchmark_return:.1f}%", self.styles["td_r"]),
                Paragraph(f"{diff:+.1f}%", diff_style),
            ])

        t = Table(rows, colWidths=[
            self.CONTENT_W * 0.30, self.CONTENT_W * 0.22,
            self.CONTENT_W * 0.22, self.CONTENT_W * 0.26,
        ])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
            ("LINEBELOW", (0, 0), (-1, 0), 1, T.gray_200),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, T.gray_100),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        self.story.append(t)

        self.story.append(PageBreak())

    # ─── Goals ──────────────────────────────────────────────────

    def _build_goals(self):
        self._add_section_header("Financial Goals",
            "Progress toward your needs, wants, and wishes")

        if not self.data.goals:
            self.story.append(Paragraph("No goals have been configured yet.", self.styles["body"]))
            self.story.append(PageBreak())
            return

        # Overall funding indicator
        d = Drawing(self.CONTENT_W, 70)
        self._draw_rounded_rect(d, 0, 0, self.CONTENT_W, 65, r=8, fill=T.white, stroke=T.gray_200)

        funded = self.data.overall_goal_funded
        mc = self.data.monte_carlo_success

        d.add(String(16, 45, "OVERALL GOAL FUNDING", fontName="Helvetica-Bold",
                    fontSize=8, fillColor=T.gray_400))
        d.add(String(16, 18, f"{funded:.0f}%", fontName="Helvetica-Bold",
                    fontSize=24, fillColor=T.navy))
        d.add(String(70, 18, "funded", fontName="Helvetica", fontSize=10, fillColor=T.gray_500))

        # Progress bar
        bar_x = 160
        bar_w = self.CONTENT_W - 180
        bar_y = 20
        d.add(Rect(bar_x, bar_y, bar_w, 12, fillColor=T.gray_100, strokeColor=None, rx=6, ry=6))
        fill_w = (funded / 100) * bar_w
        bar_color = T.emerald if funded >= 90 else (T.amber if funded >= 60 else T.red)
        d.add(Rect(bar_x, bar_y, fill_w, 12, fillColor=bar_color, strokeColor=None, rx=6, ry=6))

        d.add(String(bar_x, bar_y + 20, f"Monte Carlo Success Rate: {mc:.0f}%",
                    fontName="Helvetica", fontSize=9, fillColor=T.gray_500))

        self.story.append(d)
        self.story.append(Spacer(1, 16))

        # ── Goal funding comparison bar chart ──
        chart_h = min(len(self.data.goals) * 30 + 30, 180)
        goal_chart = Drawing(self.CONTENT_W, chart_h)
        goal_chart_left = 180
        goal_chart_w = self.CONTENT_W - goal_chart_left - 60

        for i, g in enumerate(self.data.goals):
            y = chart_h - 22 - i * 28
            # Goal name
            display_name = g.name if len(g.name) <= 25 else g.name[:23] + "..."
            goal_chart.add(String(5, y + 2, display_name,
                fontName="Helvetica", fontSize=8, fillColor=T.gray_600))
            # Background bar (100%)
            goal_chart.add(Rect(goal_chart_left, y, goal_chart_w, 14,
                fillColor=T.gray_100, strokeColor=None, rx=4, ry=4))
            # Funded bar
            fill_pct = min(g.funded_pct / 100, 1.0)
            pbar_color = T.emerald if g.funded_pct >= 90 else (T.amber if g.funded_pct >= 60 else T.red)
            goal_chart.add(Rect(goal_chart_left, y, fill_pct * goal_chart_w, 14,
                fillColor=pbar_color, strokeColor=None, rx=4, ry=4))
            # Percentage label
            goal_chart.add(String(goal_chart_left + goal_chart_w + 8, y + 2,
                f"{g.funded_pct:.0f}%",
                fontName="Helvetica-Bold", fontSize=8, fillColor=T.navy))

        self.story.append(goal_chart)
        self.story.append(Spacer(1, 16))

        # Goal cards
        for category in ["Needs", "Wants", "Wishes"]:
            cat_goals = [g for g in self.data.goals if g.category == category]
            if not cat_goals:
                continue

            cat_color = T.blue if category == "Needs" else (T.purple if category == "Wants" else T.amber)
            self.story.append(Paragraph(category.upper(), ParagraphStyle("CatLabel",
                parent=self.styles["section_label"], textColor=cat_color)))
            self.story.append(Spacer(1, 4))

            for g in cat_goals:
                # Goal row with progress bar
                gd = Drawing(self.CONTENT_W, 45)
                self._draw_rounded_rect(gd, 0, 0, self.CONTENT_W, 42, r=6, fill=T.white, stroke=T.gray_200)

                # Left accent
                gd.add(Rect(0, 0, 4, 42, fillColor=cat_color, strokeColor=None))

                gd.add(String(16, 26, g.name, fontName="Helvetica-Bold", fontSize=10, fillColor=T.navy))
                year_str = f"Target: {g.target_year}" if g.target_year else ""
                cost_str = f"${g.annual_cost:,.0f}/yr" if g.annual_cost else ""
                detail = f"{year_str}   {cost_str}".strip()
                gd.add(String(16, 10, detail, fontName="Helvetica", fontSize=8, fillColor=T.gray_400))

                # Progress bar
                bar_x = self.CONTENT_W * 0.55
                bar_w = self.CONTENT_W * 0.30
                gd.add(Rect(bar_x, 16, bar_w, 10, fillColor=T.gray_100, strokeColor=None, rx=5, ry=5))
                fill = min(g.funded_pct / 100, 1.0) * bar_w
                pbar_color = T.emerald if g.funded_pct >= 90 else (T.amber if g.funded_pct >= 60 else T.red)
                gd.add(Rect(bar_x, 16, fill, 10, fillColor=pbar_color, strokeColor=None, rx=5, ry=5))

                # Percentage
                gd.add(String(self.CONTENT_W - 40, 16, f"{g.funded_pct:.0f}%",
                             fontName="Helvetica-Bold", fontSize=10, fillColor=T.navy))

                self.story.append(gd)
                self.story.append(Spacer(1, 4))

            self.story.append(Spacer(1, 10))

        self.story.append(PageBreak())

    # ─── Retirement / Monte Carlo ───────────────────────────────

    def _build_retirement(self):
        self._add_section_header("Retirement Projection",
            "Monte Carlo simulation and income timeline")

        # Monte Carlo result
        mc = self.data.monte_carlo_success
        mc_color = T.emerald if mc >= 80 else (T.amber if mc >= 60 else T.red)

        d = Drawing(self.CONTENT_W, 100)
        self._draw_rounded_rect(d, 0, 0, self.CONTENT_W, 95, r=8, fill=T.white, stroke=T.gray_200)

        d.add(String(20, 70, "PROBABILITY OF SUCCESS", fontName="Helvetica-Bold",
                    fontSize=9, fillColor=T.gray_400))

        d.add(String(20, 30, f"{mc:.0f}%", fontName="Helvetica-Bold",
                    fontSize=36, fillColor=mc_color))

        # Descriptive text
        if mc >= 80:
            desc = "Your plan has a strong probability of success. Stay the course."
        elif mc >= 60:
            desc = "Your plan is on track but could benefit from adjustments."
        else:
            desc = "Your plan needs attention. Let's discuss strategies to improve your outlook."

        d.add(String(120, 40, desc, fontName="Helvetica", fontSize=10, fillColor=T.gray_600))

        # Visual gauge bar
        gauge_x = 120
        gauge_w = self.CONTENT_W - 160
        d.add(Rect(gauge_x, 15, gauge_w, 10, fillColor=T.gray_100, strokeColor=None, rx=5, ry=5))
        fill_w = (mc / 100) * gauge_w
        d.add(Rect(gauge_x, 15, fill_w, 10, fillColor=mc_color, strokeColor=None, rx=5, ry=5))

        self.story.append(d)
        self.story.append(Spacer(1, 20))

        # Income sources in retirement
        self.story.append(Paragraph("Projected Retirement Income Sources", self.styles["h3"]))
        self.story.append(Spacer(1, 6))

        income_rows = [[
            Paragraph("Source", self.styles["table_header"]),
            Paragraph("Annual Amount", self.styles["table_header_r"]),
            Paragraph("Notes", self.styles["table_header"]),
        ]]

        p1 = self.data.person1
        if p1.name and self.data.social_security_p1 > 0:
            income_rows.append([
                Paragraph(f"Social Security — {p1.name}", self.styles["td"]),
                Paragraph(f"${self.data.social_security_p1:,.0f}", self.styles["td_bold_r"]),
                Paragraph(f"Starting at age {p1.retirement_age}", self.styles["td"]),
            ])

        p2 = self.data.person2
        if p2 and p2.name and self.data.social_security_p2 > 0:
            income_rows.append([
                Paragraph(f"Social Security — {p2.name}", self.styles["td"]),
                Paragraph(f"${self.data.social_security_p2:,.0f}", self.styles["td_bold_r"]),
                Paragraph(f"Starting at age {p2.retirement_age}", self.styles["td"]),
            ])

        # Portfolio withdrawals
        if self.data.total_assets > 0:
            safe_withdrawal = self.data.total_assets * 0.04
            income_rows.append([
                Paragraph("Portfolio Withdrawals (4% rule)", self.styles["td"]),
                Paragraph(f"${safe_withdrawal:,.0f}", self.styles["td_bold_r"]),
                Paragraph("Inflation-adjusted annually", self.styles["td"]),
            ])

        t = Table(income_rows, colWidths=[
            self.CONTENT_W * 0.38, self.CONTENT_W * 0.22, self.CONTENT_W * 0.40])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, T.gray_100),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        self.story.append(t)
        self.story.append(Spacer(1, 16))

        # ── Retirement income pie chart + Projected wealth line chart side by side ──
        ret_charts = []

        # Income composition donut
        ss1 = self.data.social_security_p1
        ss2 = self.data.social_security_p2 if self.data.person2 else 0
        withdrawal = self.data.total_assets * 0.04 if self.data.total_assets > 0 else 0
        income_sources = []
        if ss1 > 0:
            income_sources.append(("Social Security (P1)", ss1, T.blue))
        if ss2 > 0:
            income_sources.append(("Social Security (P2)", ss2, T.teal))
        if withdrawal > 0:
            income_sources.append(("Portfolio Withdrawals", withdrawal, T.emerald))

        if income_sources:
            pie_d = Drawing(280, 160)
            pie = Pie()
            pie.x = 30
            pie.y = 20
            pie.width = 100
            pie.height = 100
            pie.data = [s[1] for s in income_sources]
            pie.labels = None
            # Note: donut style not available in this ReportLab version
            pie.sideLabels = False
            pie.simpleLabels = False
            for i, (_, _, c) in enumerate(income_sources):
                pie.slices[i].fillColor = c
                pie.slices[i].strokeColor = T.white
                pie.slices[i].strokeWidth = 1.5
            pie_d.add(pie)

            total_income = sum(s[1] for s in income_sources)
            # Center text
            pie_d.add(String(58, 72, self._fmt_currency(total_income),
                fontName="Helvetica-Bold", fontSize=10, fillColor=T.navy))
            pie_d.add(String(65, 60, "/year",
                fontName="Helvetica", fontSize=7, fillColor=T.gray_400))

            lx = 150
            for i, (name, val, c) in enumerate(income_sources):
                ly = 130 - i * 22
                pie_d.add(Rect(lx, ly, 8, 8, fillColor=c, strokeColor=None, rx=2, ry=2))
                pie_d.add(String(lx + 12, ly + 1, f"{name}",
                    fontName="Helvetica", fontSize=8, fillColor=T.gray_600))
                pie_d.add(String(lx + 12, ly - 10, self._fmt_currency(val),
                    fontName="Helvetica-Bold", fontSize=8, fillColor=T.gray_700))

            ret_charts.append([
                Paragraph("INCOME COMPOSITION", self.styles["section_label"]),
                Spacer(1, 4),
                pie_d,
            ])

        # Projected wealth growth line chart
        if self.data.total_assets > 0:
            proj_d = Drawing(340, 160)
            retirement_age = self.data.person1.retirement_age
            current_age = self.data.person1.age
            years_to_ret = max(retirement_age - current_age, 5)
            years_post_ret = 25  # Plan to age ~92

            # Project growth at 6% pre-retirement, 4% withdrawals post
            asset_val = self.data.total_assets
            annual_savings = max(self.data.total_annual_income - self.data.total_annual_expenses, 0)
            points_pre = []
            points_post = []
            ages = []

            # Pre-retirement phase
            val = asset_val
            for yr in range(years_to_ret + 1):
                age = current_age + yr
                ages.append(age)
                points_pre.append(val / 1_000_000)  # in millions
                val = val * 1.06 + annual_savings * 0.5  # simplified growth

            # Post-retirement phase
            peak = val
            for yr in range(1, years_post_ret + 1):
                age = retirement_age + yr
                ages.append(age)
                val = val * 1.04 - withdrawal * 1.02  # growth minus withdrawals
                val = max(val, 0)
                points_post.append(val / 1_000_000)

            all_points = points_pre + points_post
            total_years = len(all_points)

            # Draw axes
            chart_x = 40
            chart_y = 25
            chart_w = 280
            chart_h = 110
            max_val = max(all_points) * 1.1 if all_points else 1

            # Y-axis grid
            for i in range(5):
                gy = chart_y + (i / 4) * chart_h
                gval = (i / 4) * max_val
                proj_d.add(Line(chart_x, gy, chart_x + chart_w, gy,
                    strokeColor=T.gray_100, strokeWidth=0.5))
                proj_d.add(String(5, gy - 3, f"${gval:.1f}M",
                    fontName="Helvetica", fontSize=6, fillColor=T.gray_400))

            # X-axis labels
            label_interval = max(total_years // 6, 1)
            for i in range(0, total_years, label_interval):
                x = chart_x + (i / max(total_years - 1, 1)) * chart_w
                proj_d.add(String(x - 5, chart_y - 12, str(ages[i]) if i < len(ages) else "",
                    fontName="Helvetica", fontSize=6, fillColor=T.gray_400))

            # Draw pre-retirement area (filled)
            n_pre = len(points_pre)
            for i in range(n_pre - 1):
                x1 = chart_x + (i / max(total_years - 1, 1)) * chart_w
                x2 = chart_x + ((i + 1) / max(total_years - 1, 1)) * chart_w
                y1 = chart_y + (points_pre[i] / max_val) * chart_h
                y2 = chart_y + (points_pre[i + 1] / max_val) * chart_h
                proj_d.add(Line(x1, y1, x2, y2, strokeColor=T.emerald, strokeWidth=2))

            # Draw post-retirement line
            for i in range(len(points_post) - 1):
                idx1 = n_pre + i
                idx2 = n_pre + i + 1
                x1 = chart_x + (idx1 / max(total_years - 1, 1)) * chart_w
                x2 = chart_x + (idx2 / max(total_years - 1, 1)) * chart_w
                y1 = chart_y + (points_post[i] / max_val) * chart_h
                y2 = chart_y + (points_post[i + 1] / max_val) * chart_h
                proj_d.add(Line(x1, y1, x2, y2, strokeColor=T.blue, strokeWidth=2))

            # Retirement marker line
            ret_x = chart_x + ((n_pre - 1) / max(total_years - 1, 1)) * chart_w
            proj_d.add(Line(ret_x, chart_y, ret_x, chart_y + chart_h,
                strokeColor=T.gray_300, strokeWidth=1, strokeDashArray=[3, 3]))
            proj_d.add(String(ret_x - 15, chart_y + chart_h + 4, "Retirement",
                fontName="Helvetica", fontSize=7, fillColor=T.gray_400))

            # Legend
            proj_d.add(Rect(chart_x, chart_h + 35, 8, 8, fillColor=T.emerald, strokeColor=None))
            proj_d.add(String(chart_x + 12, chart_h + 36, "Accumulation",
                fontName="Helvetica", fontSize=7, fillColor=T.gray_500))
            proj_d.add(Rect(chart_x + 90, chart_h + 35, 8, 8, fillColor=T.blue, strokeColor=None))
            proj_d.add(String(chart_x + 102, chart_h + 36, "Distribution",
                fontName="Helvetica", fontSize=7, fillColor=T.gray_500))

            ret_charts.append([
                Paragraph("PROJECTED WEALTH GROWTH", self.styles["section_label"]),
                Spacer(1, 4),
                proj_d,
            ])

        if ret_charts:
            col_w = (self.CONTENT_W - 16) / max(len(ret_charts), 1)
            rt = Table([ret_charts], colWidths=[col_w] * len(ret_charts))
            rt.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("BACKGROUND", (0, 0), (-1, -1), T.white),
                ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
                ("LINEBEFORE", (1, 0), (1, -1), 0.5, T.gray_200),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ]))
            self.story.append(rt)

        self.story.append(PageBreak())

    # ─── Risk Management ────────────────────────────────────────

    def _build_risk_management(self):
        self._add_section_header("Risk Management",
            "Insurance coverage and estate planning review")

        # Insurance checklist
        self.story.append(Paragraph("Insurance Coverage", self.styles["h3"]))
        self.story.append(Spacer(1, 6))

        def _check(val):
            return "Yes" if val else "No"

        def _check_style(val):
            return ParagraphStyle("chk", parent=self.styles["td_bold"],
                textColor=T.emerald if val else T.red)

        ins_rows = [[
            Paragraph("Coverage Type", self.styles["table_header"]),
            Paragraph("Status", self.styles["table_header"]),
            Paragraph("Details", self.styles["table_header"]),
        ]]
        ins_rows.append([
            Paragraph("Life Insurance", self.styles["td"]),
            Paragraph(_check(self.data.life_insurance_coverage > 0),
                      _check_style(self.data.life_insurance_coverage > 0)),
            Paragraph(f"${self.data.life_insurance_coverage:,.0f} coverage" if self.data.life_insurance_coverage > 0 else "Not in place",
                      self.styles["td"]),
        ])
        ins_rows.append([
            Paragraph("Disability Insurance", self.styles["td"]),
            Paragraph(_check(self.data.disability_coverage), _check_style(self.data.disability_coverage)),
            Paragraph("In place" if self.data.disability_coverage else "Consider adding coverage", self.styles["td"]),
        ])
        ins_rows.append([
            Paragraph("Long-Term Care", self.styles["td"]),
            Paragraph(_check(self.data.ltc_coverage), _check_style(self.data.ltc_coverage)),
            Paragraph("In place" if self.data.ltc_coverage else "Review need based on age and assets", self.styles["td"]),
        ])

        t = Table(ins_rows, colWidths=[self.CONTENT_W * 0.25, self.CONTENT_W * 0.15, self.CONTENT_W * 0.60])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, T.gray_100),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        self.story.append(t)

        self.story.append(Spacer(1, 24))

        # Estate planning checklist
        self.story.append(Paragraph("Estate Planning Checklist", self.styles["h3"]))
        self.story.append(Spacer(1, 6))

        estate_items = [
            ("Last Will & Testament", self.data.has_will),
            ("Revocable Living Trust", self.data.has_trust),
            ("Durable Power of Attorney", self.data.has_poa),
            ("Healthcare Directive / Living Will", self.data.has_healthcare_directive),
        ]

        est_rows = [[
            Paragraph("Document", self.styles["table_header"]),
            Paragraph("Status", self.styles["table_header"]),
            Paragraph("Recommendation", self.styles["table_header"]),
        ]]
        for name, has_it in estate_items:
            rec = "Current and up to date" if has_it else "Recommended — schedule with attorney"
            est_rows.append([
                Paragraph(name, self.styles["td"]),
                Paragraph(_check(has_it), _check_style(has_it)),
                Paragraph(rec, self.styles["td"]),
            ])

        t2 = Table(est_rows, colWidths=[self.CONTENT_W * 0.30, self.CONTENT_W * 0.12, self.CONTENT_W * 0.58])
        t2.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), T.gray_50),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, T.gray_100),
            ("BOX", (0, 0), (-1, -1), 0.5, T.gray_200),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        self.story.append(t2)

        self.story.append(PageBreak())

    # ─── Recommendations ────────────────────────────────────────

    def _build_recommendations(self):
        self._add_section_header("Recommendations & Next Steps",
            "Key action items from your financial review")

        if self.data.key_recommendations:
            self.story.append(Paragraph("Key Recommendations", self.styles["h3"]))
            self.story.append(Spacer(1, 6))

            for i, rec in enumerate(self.data.key_recommendations, 1):
                d = Drawing(self.CONTENT_W, 36)
                self._draw_rounded_rect(d, 0, 0, self.CONTENT_W, 32, r=6, fill=T.blue_bg, stroke=T.blue_light)
                d.add(Rect(0, 0, 4, 32, fillColor=T.blue, strokeColor=None))

                # Number circle
                d.add(Circle(22, 16, 10, fillColor=T.blue, strokeColor=None))
                d.add(String(19, 12, str(i), fontName="Helvetica-Bold", fontSize=10, fillColor=T.white))

                d.add(String(40, 12, rec, fontName="Helvetica", fontSize=9.5, fillColor=T.gray_700))
                self.story.append(d)
                self.story.append(Spacer(1, 4))

        if self.data.next_steps:
            self.story.append(Spacer(1, 16))
            self.story.append(Paragraph("Next Steps", self.styles["h3"]))
            self.story.append(Spacer(1, 6))

            for step in self.data.next_steps:
                d = Drawing(self.CONTENT_W, 30)
                self._draw_rounded_rect(d, 0, 0, self.CONTENT_W, 26, r=4, fill=T.white, stroke=T.gray_200)

                # Checkbox
                d.add(Rect(12, 6, 14, 14, fillColor=T.white, strokeColor=T.gray_300, strokeWidth=1, rx=3, ry=3))

                d.add(String(34, 8, step, fontName="Helvetica", fontSize=9.5, fillColor=T.gray_700))
                self.story.append(d)
                self.story.append(Spacer(1, 3))

        self.story.append(PageBreak())

    # ─── Disclosures ────────────────────────────────────────────

    def _build_disclosures(self):
        self._add_section_header("Important Disclosures",
            "Assumptions, limitations, and methodology")

        disclosures = [
            "This report provides a snapshot of your current financial position and can help you focus "
            "on your financial resources and goals, and to create a plan of action. Because the results "
            "are calculated over many years, small changes can create large differences in future results.",

            "The projections contained within are hypothetical in nature, do not reflect actual investment "
            "results, and are not guarantees of future results. All results use simplifying assumptions "
            "that do not completely or accurately reflect your specific circumstances.",

            "This report does not provide legal, tax, or accounting advice. Before making decisions with "
            "legal, tax, or accounting ramifications, you should consult appropriate professionals for "
            "advice that is specific to your situation.",

            "All asset and net worth information included in this report was provided by you or your "
            "designated agents, and is not a substitute for the information contained in the official "
            "account statements provided to you by custodians.",

            "Monte Carlo simulations are used to show how variations in rates of return each year can "
            "affect your results. The percentage of trials that were successful is the Probability of "
            "Success. Monte Carlo simulations indicate the likelihood that an event may occur as well "
            "as the likelihood that it may not occur.",

            "Past performance is not a guarantee of future performance or a guarantee of achieving "
            "overall financial objectives. Past performance is not reflective of any specific product, "
            "and does not include any fees or expenses that may be incurred by investing in specific "
            "products. Actual returns of a specific product may be more or less than the returns used.",
        ]

        for text in disclosures:
            self.story.append(Paragraph(text, self.styles["disclaimer"]))
            self.story.append(Spacer(1, 6))

    # ─── Page Header / Footer ───────────────────────────────────

    def _draw_header_footer(self, canvas_obj, doc):
        """Called on each page to draw header and footer."""
        canvas_obj.saveState()

        # Header — thin accent line
        canvas_obj.setStrokeColor(T.gray_200)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(self.MARGIN, self.PAGE_H - 36,
                       self.PAGE_W - self.MARGIN, self.PAGE_H - 36)

        # Header text
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(T.gray_400)
        canvas_obj.drawString(self.MARGIN, self.PAGE_H - 30, self.data.firm_name)
        canvas_obj.drawRightString(self.PAGE_W - self.MARGIN, self.PAGE_H - 30,
            f"Prepared for: {self.data.client_names}")

        # Footer
        canvas_obj.setStrokeColor(T.gray_200)
        canvas_obj.line(self.MARGIN, 40, self.PAGE_W - self.MARGIN, 40)

        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(T.gray_400)
        canvas_obj.drawString(self.MARGIN, 28,
            f"Prepared by: {self.data.advisor_name}")
        canvas_obj.drawCentredString(self.PAGE_W / 2, 28,
            self.data.firm_name)
        canvas_obj.drawRightString(self.PAGE_W - self.MARGIN, 28,
            f"Page {doc.page}")

        canvas_obj.restoreState()

    def _draw_cover_header_footer(self, canvas_obj, doc):
        """Cover page — no header/footer."""
        pass

    # ─── Build ──────────────────────────────────────────────────

    def build(self):
        """Assemble and generate the complete report."""
        doc = BaseDocTemplate(self.output_path, pagesize=landscape(letter),
            topMargin=0.55 * inch, bottomMargin=0.6 * inch,
            leftMargin=self.MARGIN, rightMargin=self.MARGIN)

        frame = Frame(doc.leftMargin, doc.bottomMargin,
                      doc.width, doc.height, id="normal")

        doc.addPageTemplates([
            PageTemplate(id="cover", frames=frame,
                        onPage=self._draw_cover_header_footer),
            PageTemplate(id="content", frames=frame,
                        onPage=self._draw_header_footer),
        ])

        # Build story
        self.story.append(NextPageTemplate("cover"))
        self._build_cover()
        self.story.append(NextPageTemplate("content"))
        self._build_toc()
        self._build_executive_summary()
        self._build_personal_info()
        self._build_net_worth()
        self._build_allocation()
        self._build_performance()
        self._build_goals()
        self._build_retirement()
        self._build_risk_management()
        self._build_recommendations()
        self._build_disclosures()

        doc.build(self.story)
        print(f"  [PDF] Premium report generated: {self.output_path}")
        return self.output_path


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════

def generate_client_report(data: ClientReportData, output_path: str = None) -> str:
    """
    Generate a premium client financial report PDF.

    Args:
        data: ClientReportData with all client information
        output_path: Where to save the PDF (default: ./reports/<client>.pdf)

    Returns:
        Path to the generated PDF
    """
    if not output_path:
        safe_name = data.client_names.replace(" ", "_").replace("/", "-")[:40]
        os.makedirs("./reports", exist_ok=True)
        output_path = f"./reports/{safe_name}_Financial_Report.pdf"

    builder = PremiumReportBuilder(data, output_path)
    return builder.build()


# ═══════════════════════════════════════════════════════════════════
# Demo / Sample Report Generation
# ═══════════════════════════════════════════════════════════════════

def generate_sample_report(output_path: str = None) -> str:
    """Generate a sample report with Eduardo & Adriana's data."""

    data = ClientReportData(
        report_title="Financial Goal Plan",
        report_date="March 16, 2026",
        advisor_name="Marcelo Zinn",
        advisor_title="Wealth Advisor",
        firm_name="Maredin Wealth Advisors",
        firm_tagline="Independent  |  Fiduciary  |  Focused",

        client_names="Eduardo and Adriana Lapeira",
        person1=PersonInfo(
            name="Eduardo Lapeira",
            dob="06/30/1978",
            age=47,
            employment_status="Employed",
            annual_income=630000,
            retirement_age=67,
        ),
        person2=PersonInfo(
            name="Adriana Lapeira",
            dob="05/05/1976",
            age=49,
            employment_status="Homemaker",
            annual_income=0,
            retirement_age=69,
        ),
        dependents=[
            {"name": "Diana", "dob": "01/01/2005", "age": 21, "relationship": "Child - Dependent of Both"},
        ],
        filing_status="Married Filing Jointly",
        state="Florida",

        total_assets=4_850_000,
        total_liabilities=380_000,
        net_worth=4_470_000,
        accounts=[
            AccountInfo("Eduardo 401(k)", "Eduardo", "401(k)", 1_250_000, "Fidelity"),
            AccountInfo("Eduardo Roth IRA", "Eduardo", "Roth IRA", 285_000, "Schwab"),
            AccountInfo("Adriana IRA", "Adriana", "Traditional IRA", 420_000, "Schwab"),
            AccountInfo("Joint Brokerage", "Joint", "Taxable Brokerage", 1_380_000, "Interactive Brokers"),
            AccountInfo("529 Plan — Diana", "Joint", "529 Education", 185_000, "Vanguard"),
            AccountInfo("Checking / Savings", "Joint", "Cash", 320_000, "Bank of America"),
            AccountInfo("Investment Property", "Joint", "Real Estate", 650_000, "N/A"),
            AccountInfo("Eduardo RSUs", "Eduardo", "Stock Options", 360_000, "E-Trade"),
        ],

        allocation=[
            AllocationItem("US Large Cap Stocks", 32.0, 30.0, 1_552_000),
            AllocationItem("US Mid/Small Cap", 12.0, 12.0, 582_000),
            AllocationItem("International Developed", 14.0, 15.0, 679_000),
            AllocationItem("Emerging Markets", 6.0, 8.0, 291_000),
            AllocationItem("US Bonds", 18.0, 18.0, 873_000),
            AllocationItem("International Bonds", 4.0, 5.0, 194_000),
            AllocationItem("Real Estate / REITs", 8.0, 7.0, 388_200),
            AllocationItem("Cash & Equivalents", 6.0, 5.0, 291_000),
        ],
        risk_score=6,
        risk_label="Moderate Growth",

        goals=[
            GoalInfo("Retirement — Basic Living", "Needs", 220_000, 92.0, 2045, 220_000, "Both retired 2045-2070"),
            GoalInfo("Healthcare in Retirement", "Needs", 85_000, 78.0, 2045, 85_000, "Including Medicare supplement"),
            GoalInfo("Diana's Graduate School", "Wants", 120_000, 95.0, 2028, 40_000, "MBA program funding"),
            GoalInfo("Vacation Home", "Wants", 450_000, 62.0, 2032, 0, "Mountains or beach property"),
            GoalInfo("Philanthropic Giving", "Wishes", 50_000, 100.0, 0, 50_000, "Annual donor-advised fund"),
            GoalInfo("Legacy / Inheritance", "Wishes", 1_000_000, 85.0, 0, 0, "Estate for Diana"),
        ],
        overall_goal_funded=87.0,
        monte_carlo_success=82.0,

        performance=[
            PerformanceData("1 Month", 1.2, 1.0),
            PerformanceData("3 Months", 3.8, 3.5),
            PerformanceData("YTD", 5.2, 4.8),
            PerformanceData("1 Year", 12.4, 11.8),
            PerformanceData("3 Years", 8.2, 7.6),
            PerformanceData("5 Years", 9.1, 8.5),
        ],

        total_annual_income=630_000,
        total_annual_expenses=180_000,
        social_security_p1=51_947,
        social_security_p2=25_973,

        life_insurance_coverage=2_000_000,
        disability_coverage=True,
        ltc_coverage=False,

        estate_value=4_470_000,
        has_will=True,
        has_trust=True,
        has_poa=True,
        has_healthcare_directive=False,

        key_recommendations=[
            "Maximize 401(k) contributions to $23,500 annual limit — consider catch-up contributions starting age 50",
            "Rebalance international allocation — currently 2% under target in Emerging Markets",
            "Establish long-term care insurance before age 55 to lock in favorable rates",
            "Complete healthcare directive / living will — critical gap in estate planning",
            "Review RSU vesting schedule and develop a systematic diversification plan to reduce concentration risk",
            "Consider Roth conversion strategy during lower-income years before RMDs begin",
        ],
        next_steps=[
            "Schedule estate attorney meeting to complete healthcare directive",
            "Request LTC insurance quotes from 3 carriers",
            "Set up automatic rebalancing for joint brokerage account",
            "Review and update beneficiary designations on all retirement accounts",
            "Discuss 529-to-Roth rollover strategy for Diana's leftover education funds",
            "Next comprehensive review: September 2026",
        ],
    )

    return generate_client_report(data, output_path)


if __name__ == "__main__":
    path = generate_sample_report("./Eduardo_Adriana_Financial_Report.pdf")
    print(f"\nReport saved to: {path}")
