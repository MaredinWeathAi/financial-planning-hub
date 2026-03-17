"""
Invoice Email Sender.

Sends invoices as PDF attachments via SMTP.
Supports Gmail, Outlook, and custom SMTP servers.

Setup:
    Set environment variables:
        SMTP_HOST=smtp.gmail.com
        SMTP_PORT=587
        SMTP_USER=your@gmail.com
        SMTP_PASSWORD=your_app_password     # Use App Password, not your real password
        SMTP_FROM_NAME=Your Company Name

    For Gmail, enable 2FA and create an App Password:
    https://myaccount.google.com/apppasswords

    For Outlook/Office 365:
        SMTP_HOST=smtp.office365.com
        SMTP_PORT=587
"""

import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Optional

from invoice_models import Invoice, InvoiceStatus


# ─── SMTP Configuration ─────────────────────────────────────────

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


class InvoiceEmailSender:
    """
    Sends invoice PDFs via email.

    Usage:
        sender = InvoiceEmailSender()
        sender.send_invoice(invoice)
        sender.send_batch(invoices)  # Send to multiple clients
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        from_name: str = None,
    ):
        self.host = host or SMTP_HOST
        self.port = port or SMTP_PORT
        self.user = user or SMTP_USER
        self.password = password or SMTP_PASSWORD
        self.from_name = from_name or SMTP_FROM_NAME or self.user

    def send_invoice(
        self,
        invoice: Invoice,
        cc: List[str] = None,
        bcc: List[str] = None,
        subject_template: str = None,
        body_template: str = None,
        dry_run: bool = False,
    ) -> bool:
        """
        Send a single invoice email with PDF attached.

        Templates support these placeholders:
            {client_name}, {invoice_number}, {period},
            {total}, {due_date}, {company_name}
        """
        if not invoice.pdf_path or not os.path.exists(invoice.pdf_path):
            print(f"  [Email] ERROR: PDF not found: {invoice.pdf_path}")
            return False

        if not invoice.client_email:
            print(f"  [Email] ERROR: No email for client {invoice.client_name}")
            return False

        # Template variables
        tpl_vars = {
            "client_name": invoice.client_name,
            "invoice_number": invoice.invoice_number,
            "period": invoice.period_label,
            "total": f"${invoice.total:,.2f}",
            "due_date": invoice.due_date,
            "company_name": invoice.company_name or self.from_name,
            "issue_date": invoice.issue_date,
            "subtotal": f"${invoice.subtotal:,.2f}",
            "payment_terms": str(invoice.payment_terms),
        }

        # Subject
        if not subject_template:
            subject_template = (
                "Invoice {invoice_number} — {period} | {company_name}"
            )
        subject = subject_template.format(**tpl_vars)

        # Body
        if not body_template:
            body_template = DEFAULT_EMAIL_BODY
        body_html = body_template.format(**tpl_vars)

        # Build email
        msg = MIMEMultipart("mixed")
        msg["From"] = f"{self.from_name} <{self.user}>"
        msg["To"] = invoice.client_email
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)

        # HTML body
        html_part = MIMEText(body_html, "html")
        msg.attach(html_part)

        # PDF attachment
        pdf_filename = os.path.basename(invoice.pdf_path)
        with open(invoice.pdf_path, "rb") as f:
            pdf_part = MIMEBase("application", "pdf")
            pdf_part.set_payload(f.read())
            encoders.encode_base64(pdf_part)
            pdf_part.add_header(
                "Content-Disposition",
                f"attachment; filename={pdf_filename}"
            )
            msg.attach(pdf_part)

        # Collect all recipients
        all_recipients = [invoice.client_email]
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)

        if dry_run:
            print(f"  [Email] DRY RUN — Would send to: {', '.join(all_recipients)}")
            print(f"           Subject: {subject}")
            print(f"           Attachment: {pdf_filename}")
            return True

        # Send
        try:
            if not self.user or not self.password:
                print("  [Email] ERROR: SMTP credentials not configured.")
                print("  Set SMTP_USER and SMTP_PASSWORD environment variables.")
                return False

            with smtplib.SMTP(self.host, self.port) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)

            invoice.status = InvoiceStatus.SENT
            invoice.sent_at = datetime.now().isoformat()

            print(f"  [Email] Sent to {invoice.client_email}: {subject}")
            return True

        except smtplib.SMTPAuthenticationError:
            print("  [Email] ERROR: Authentication failed.")
            print("  For Gmail, use an App Password (not your real password).")
            print("  https://myaccount.google.com/apppasswords")
            return False
        except Exception as e:
            print(f"  [Email] ERROR: {e}")
            return False

    def send_batch(
        self,
        invoices: List[Invoice],
        cc: List[str] = None,
        bcc: List[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Send invoices to multiple clients.
        Returns summary of results.
        """
        results = {"sent": 0, "failed": 0, "skipped": 0}

        for invoice in invoices:
            if invoice.status == InvoiceStatus.SENT:
                print(f"  [Email] Skipping {invoice.invoice_number} — already sent")
                results["skipped"] += 1
                continue

            if invoice.status == InvoiceStatus.VOID:
                print(f"  [Email] Skipping {invoice.invoice_number} — voided")
                results["skipped"] += 1
                continue

            # Merge client CC with batch CC
            all_cc = list(cc or [])
            # (client-level CC could be added here from invoice/client data)

            success = self.send_invoice(
                invoice, cc=all_cc, bcc=bcc, dry_run=dry_run
            )

            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1

        return results

    def test_connection(self) -> bool:
        """Test SMTP connection without sending."""
        try:
            if not self.user or not self.password:
                print("[Email] No SMTP credentials configured.")
                return False

            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                server.login(self.user, self.password)
                print(f"[Email] Connection OK — {self.host}:{self.port} as {self.user}")
                return True
        except Exception as e:
            print(f"[Email] Connection failed: {e}")
            return False


# ─── Default Email Template ─────────────────────────────────────

DEFAULT_EMAIL_BODY = """<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; background: #f5f5f5; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; }}
  .header {{ background: #1a1a2e; padding: 32px 40px; }}
  .header h1 {{ color: #ffffff; margin: 0; font-size: 20px; font-weight: 600; }}
  .header p {{ color: #a0a0b8; margin: 4px 0 0 0; font-size: 13px; }}
  .body {{ padding: 32px 40px; }}
  .greeting {{ font-size: 15px; margin-bottom: 20px; }}
  .summary {{ background: #f8f9fa; border-radius: 8px; padding: 20px 24px; margin: 20px 0; border-left: 4px solid #1a1a2e; }}
  .summary-row {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }}
  .summary-label {{ color: #666; }}
  .summary-value {{ font-weight: 600; color: #1a1a2e; }}
  .total-row {{ border-top: 1px solid #ddd; margin-top: 8px; padding-top: 8px; }}
  .total-row .summary-value {{ font-size: 18px; }}
  .note {{ font-size: 13px; color: #666; margin-top: 20px; }}
  .footer {{ padding: 20px 40px; background: #f8f9fa; border-top: 1px solid #eee; text-align: center; font-size: 12px; color: #999; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{company_name}</h1>
    <p>Invoice #{invoice_number}</p>
  </div>
  <div class="body">
    <p class="greeting">Dear {client_name},</p>
    <p>Please find attached your invoice for <strong>{period}</strong>.</p>

    <div class="summary">
      <div class="summary-row">
        <span class="summary-label">Invoice Number</span>
        <span class="summary-value">{invoice_number}</span>
      </div>
      <div class="summary-row">
        <span class="summary-label">Billing Period</span>
        <span class="summary-value">{period}</span>
      </div>
      <div class="summary-row">
        <span class="summary-label">Issue Date</span>
        <span class="summary-value">{issue_date}</span>
      </div>
      <div class="summary-row">
        <span class="summary-label">Due Date</span>
        <span class="summary-value">{due_date}</span>
      </div>
      <div class="summary-row total-row">
        <span class="summary-label">Amount Due</span>
        <span class="summary-value">{total}</span>
      </div>
    </div>

    <p class="note">Payment is due within {payment_terms} days. If you have any questions about this invoice, please don't hesitate to reach out.</p>
  </div>
  <div class="footer">
    {company_name} &bull; This invoice was generated automatically.
  </div>
</div>
</body>
</html>"""
