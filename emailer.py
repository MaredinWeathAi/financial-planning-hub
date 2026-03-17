"""
Email Sender for Invoice Delivery.

Sends PDF invoices to clients via SMTP email with
customizable templates and automatic CC/BCC support.

Supports:
- Gmail (App Passwords)
- Outlook/Office 365
- AWS SES
- Any SMTP server
- HTML email templates
- PDF attachment
- CC/BCC to your accountant, CPA, etc.
"""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional
from pathlib import Path

from config import DATA_DIR


# ═══════════════════════════════════════════════════════════════════
# Email Configuration
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EmailConfig:
    """
    SMTP configuration.

    Gmail Setup:
        1. Enable 2FA on your Google account
        2. Go to https://myaccount.google.com/apppasswords
        3. Create an App Password for "Mail"
        4. Use that 16-char password as smtp_password

    Outlook/O365 Setup:
        smtp_host: "smtp.office365.com"
        smtp_port: 587
        use_tls: True
    """
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")    # App Password for Gmail
    use_tls: bool = True
    use_ssl: bool = False

    from_email: str = os.getenv("FROM_EMAIL", "")
    from_name: str = os.getenv("FROM_NAME", "")
    reply_to: str = ""

    # Global CC/BCC (e.g., always CC your CPA)
    global_cc: List[str] = field(default_factory=list)
    global_bcc: List[str] = field(default_factory=list)

    # Branding
    company_name: str = ""
    accent_color: str = "#16a34a"


# ═══════════════════════════════════════════════════════════════════
# Email Templates
# ═══════════════════════════════════════════════════════════════════

def default_invoice_email_html(
    client_name: str,
    invoice_number: str,
    amount: str,
    due_date: str,
    period: str,
    company_name: str = "",
    accent_color: str = "#16a34a",
    custom_message: str = "",
    from_name: str = "",
) -> str:
    """Generate a clean HTML email body for invoice delivery."""

    greeting = client_name.split()[0] if client_name else "there"
    custom_block = f'<p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6">{custom_message}</p>' if custom_message else ""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1)">

<!-- Header -->
<tr><td style="background:{accent_color};padding:28px 32px">
    <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px">
        {company_name or 'Invoice'}
    </h1>
</td></tr>

<!-- Body -->
<tr><td style="padding:32px">
    <p style="margin:0 0 20px;color:#374151;font-size:15px;line-height:1.6">
        Hi {greeting},
    </p>
    <p style="margin:0 0 20px;color:#374151;font-size:15px;line-height:1.6">
        Please find attached your invoice for services rendered during <b>{period}</b>.
    </p>

    {custom_block}

    <!-- Invoice Summary Card -->
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;margin:24px 0">
    <tr><td style="padding:20px 24px">
        <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td style="color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;padding-bottom:4px">Invoice</td>
            <td align="right" style="color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;padding-bottom:4px">Amount Due</td>
        </tr>
        <tr>
            <td style="color:#111827;font-size:16px;font-weight:700">{invoice_number}</td>
            <td align="right" style="color:{accent_color};font-size:22px;font-weight:700">{amount}</td>
        </tr>
        <tr>
            <td colspan="2" style="padding-top:12px;border-top:1px solid #e5e7eb">
                <span style="color:#6b7280;font-size:13px">Due by <b style="color:#111827">{due_date}</b></span>
            </td>
        </tr>
        </table>
    </td></tr>
    </table>

    <p style="margin:0 0 8px;color:#374151;font-size:15px;line-height:1.6">
        The full invoice is attached as a PDF. Please don't hesitate to reach out if you have any questions.
    </p>
    <p style="margin:24px 0 0;color:#374151;font-size:15px;line-height:1.6">
        Best regards,<br>
        <b>{from_name or company_name}</b>
    </p>
</td></tr>

<!-- Footer -->
<tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 32px">
    <p style="margin:0;color:#9ca3af;font-size:12px;text-align:center">
        This invoice was generated automatically.
        Please retain for your records.
    </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def default_invoice_email_text(
    client_name: str,
    invoice_number: str,
    amount: str,
    due_date: str,
    period: str,
    **kwargs,
) -> str:
    """Plain-text fallback for email clients that don't render HTML."""
    greeting = client_name.split()[0] if client_name else "there"
    return f"""Hi {greeting},

Please find attached your invoice for services rendered during {period}.

  Invoice:    {invoice_number}
  Amount Due: {amount}
  Due Date:   {due_date}

The full invoice is attached as a PDF. Please don't hesitate to reach out if you have any questions.

Best regards"""


# ═══════════════════════════════════════════════════════════════════
# Email Sender
# ═══════════════════════════════════════════════════════════════════

class InvoiceEmailer:
    """
    Sends invoice emails with PDF attachments.
    """

    def __init__(self, config: EmailConfig = None):
        self.config = config or EmailConfig()
        self._validate_config()

    def _validate_config(self):
        missing = []
        if not self.config.smtp_user:
            missing.append("SMTP_USER")
        if not self.config.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not self.config.from_email:
            self.config.from_email = self.config.smtp_user
        if missing:
            print(f"⚠ Email not configured. Set env vars: {', '.join(missing)}")
            print("  Or update EmailConfig in emailer.py")

    def send_invoice(
        self,
        invoice,          # invoices.Invoice
        to_email: str = None,
        cc: List[str] = None,
        bcc: List[str] = None,
        subject: str = None,
        custom_message: str = "",
        dry_run: bool = False,
    ) -> bool:
        """
        Send an invoice email with PDF attachment.

        Returns True on success.
        """
        to_email = to_email or invoice.client_email
        if not to_email:
            print(f"  ✗ No email for {invoice.client_name}")
            return False

        # Build recipients
        all_cc = list(set((cc or []) + self.config.global_cc))
        all_bcc = list(set((bcc or []) + self.config.global_bcc))

        # Format values for the template
        amount_str = f"${invoice.balance_due:,.2f}"
        try:
            due_str = date.fromisoformat(invoice.due_date).strftime("%B %d, %Y")
        except (ValueError, TypeError):
            due_str = invoice.due_date

        try:
            ps = date.fromisoformat(invoice.period_start).strftime("%B %Y")
        except (ValueError, TypeError):
            ps = invoice.period_start
        period_str = ps

        # Subject line
        if not subject:
            subject = f"Invoice {invoice.invoice_number} — {period_str} — {amount_str}"

        # Build email
        msg = MIMEMultipart("alternative")
        msg["From"] = (
            f"{self.config.from_name} <{self.config.from_email}>"
            if self.config.from_name else self.config.from_email
        )
        msg["To"] = to_email
        msg["Subject"] = subject

        if all_cc:
            msg["Cc"] = ", ".join(all_cc)
        if self.config.reply_to:
            msg["Reply-To"] = self.config.reply_to

        # Email body
        template_kwargs = dict(
            client_name=invoice.client_name,
            invoice_number=invoice.invoice_number,
            amount=amount_str,
            due_date=due_str,
            period=period_str,
            company_name=self.config.company_name,
            accent_color=self.config.accent_color,
            custom_message=custom_message,
            from_name=self.config.from_name,
        )

        text_body = default_invoice_email_text(**template_kwargs)
        html_body = default_invoice_email_html(**template_kwargs)

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Attach PDF
        if invoice.pdf_path and os.path.exists(invoice.pdf_path):
            with open(invoice.pdf_path, "rb") as f:
                pdf_attachment = MIMEBase("application", "octet-stream")
                pdf_attachment.set_payload(f.read())
            encoders.encode_base64(pdf_attachment)
            filename = os.path.basename(invoice.pdf_path)
            pdf_attachment.add_header(
                "Content-Disposition",
                f"attachment; filename={filename}",
            )
            msg.attach(pdf_attachment)
        else:
            print(f"  ⚠ No PDF found at: {invoice.pdf_path}")

        # Send
        all_recipients = [to_email] + all_cc + all_bcc

        if dry_run:
            print(f"  [DRY RUN] Would send to: {to_email}")
            if all_cc:
                print(f"            CC: {', '.join(all_cc)}")
            print(f"            Subject: {subject}")
            print(f"            Attachment: {invoice.pdf_path}")
            return True

        try:
            if self.config.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    context=context,
                )
            else:
                server = smtplib.SMTP(
                    self.config.smtp_host,
                    self.config.smtp_port,
                )
                if self.config.use_tls:
                    server.starttls(context=ssl.create_default_context())

            server.login(self.config.smtp_user, self.config.smtp_password)
            server.sendmail(self.config.from_email, all_recipients, msg.as_string())
            server.quit()

            print(f"  ✓ Sent to {to_email} — {invoice.invoice_number}")
            return True

        except smtplib.SMTPAuthenticationError:
            print(f"  ✗ SMTP auth failed. Check credentials.")
            print(f"    For Gmail, use an App Password: https://myaccount.google.com/apppasswords")
            return False
        except Exception as e:
            print(f"  ✗ Email failed: {e}")
            return False

    def send_batch(
        self,
        invoices: list,
        client_map: dict = None,
        custom_message: str = "",
        dry_run: bool = False,
    ) -> dict:
        """
        Send invoices to all clients in a batch.

        client_map: {client_id: Client} for looking up CC emails
        Returns {"sent": N, "failed": N, "skipped": N}
        """
        results = {"sent": 0, "failed": 0, "skipped": 0}

        for invoice in invoices:
            if invoice.status == "sent":
                results["skipped"] += 1
                continue

            # Get client-specific CC list
            cc = []
            if client_map and invoice.client_id in client_map:
                cc = client_map[invoice.client_id].cc_emails or []

            success = self.send_invoice(
                invoice=invoice,
                cc=cc,
                custom_message=custom_message,
                dry_run=dry_run,
            )

            if success:
                invoice.status = "sent"
                invoice.sent_at = date.today().isoformat()
                results["sent"] += 1
            else:
                results["failed"] += 1

        return results


# ═══════════════════════════════════════════════════════════════════
# Quick Test
# ═══════════════════════════════════════════════════════════════════

def test_email_config():
    """Verify SMTP settings by sending a test email to yourself."""
    config = EmailConfig()
    if not config.smtp_user:
        print("Email not configured. Set SMTP_USER and SMTP_PASSWORD env vars.")
        return

    emailer = InvoiceEmailer(config)

    msg = MIMEMultipart()
    msg["From"] = config.from_email
    msg["To"] = config.from_email
    msg["Subject"] = "Reconciler — Email Config Test"
    msg.attach(MIMEText("If you can read this, email is working!", "plain"))

    try:
        server = smtplib.SMTP(config.smtp_host, config.smtp_port)
        server.starttls()
        server.login(config.smtp_user, config.smtp_password)
        server.sendmail(config.from_email, [config.from_email], msg.as_string())
        server.quit()
        print("✓ Test email sent successfully!")
    except Exception as e:
        print(f"✗ Test failed: {e}")
