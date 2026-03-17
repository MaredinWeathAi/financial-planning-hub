"""
QuickBooks Online Integration.

Handles OAuth2 authentication and CRUD operations for
pushing reconciled transactions into QBO.

Prerequisites:
    pip install python-quickbooks intuit-oauth

Setup:
    1. Create an app at https://developer.intuit.com
    2. Get Client ID and Client Secret
    3. Set redirect URI to http://localhost:5000/callback
    4. Run the OAuth flow once to get initial tokens
    5. Tokens auto-refresh after that
"""

import json
import os
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from models import (
    UnifiedTransaction, TransactionType, ReconciliationStatus
)
from config import (
    QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REDIRECT_URI,
    QBO_ENVIRONMENT, QBO_REALM_ID, DATA_DIR
)

# Token storage path
TOKEN_FILE = os.path.join(DATA_DIR, ".qbo_tokens.json")


class QuickBooksClient:
    """
    Handles all QuickBooks Online API operations.

    Usage:
        client = QuickBooksClient()
        client.authenticate()  # First time: opens browser for OAuth
        client.push_transactions(transactions)
    """

    def __init__(self):
        self.qb_client = None
        self.auth_client = None
        self._tokens = self._load_tokens()

    def authenticate(self):
        """
        Initialize OAuth2 authentication.
        First run requires browser-based authorization.
        Subsequent runs use saved refresh token.
        """
        try:
            from intuitlib.client import AuthClient
            from intuitlib.enums import Scopes
            from quickbooks import QuickBooks
        except ImportError:
            print("Install required packages:")
            print("  pip install python-quickbooks intuit-oauth")
            return False

        self.auth_client = AuthClient(
            client_id=QBO_CLIENT_ID,
            client_secret=QBO_CLIENT_SECRET,
            redirect_uri=QBO_REDIRECT_URI,
            environment=QBO_ENVIRONMENT,
        )

        if self._tokens.get("refresh_token"):
            # Use existing refresh token
            try:
                self.auth_client.refresh(
                    refresh_token=self._tokens["refresh_token"]
                )
                self._save_tokens({
                    "access_token": self.auth_client.access_token,
                    "refresh_token": self.auth_client.refresh_token,
                    "realm_id": self._tokens.get("realm_id", QBO_REALM_ID),
                })
            except Exception as e:
                print(f"Token refresh failed: {e}")
                return self._do_initial_auth()
        else:
            return self._do_initial_auth()

        realm_id = self._tokens.get("realm_id", QBO_REALM_ID)
        self.qb_client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self.auth_client.refresh_token,
            company_id=realm_id,
        )
        return True

    def _do_initial_auth(self) -> bool:
        """Run the initial OAuth2 browser flow."""
        from intuitlib.enums import Scopes

        scopes = [Scopes.ACCOUNTING]
        auth_url = self.auth_client.get_authorization_url(scopes)

        print("\n" + "=" * 60)
        print("QuickBooks OAuth2 Authorization Required")
        print("=" * 60)
        print(f"\n1. Open this URL in your browser:\n\n   {auth_url}\n")
        print("2. Authorize the app")
        print("3. Copy the FULL redirect URL from your browser")

        redirect_url = input("\nPaste the redirect URL here: ").strip()

        # Parse the auth code from the redirect URL
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)

        auth_code = params.get("code", [None])[0]
        realm_id = params.get("realmId", [QBO_REALM_ID])[0]

        if not auth_code:
            print("ERROR: Could not extract auth code from URL")
            return False

        self.auth_client.get_bearer_token(auth_code, realm_id=realm_id)

        self._save_tokens({
            "access_token": self.auth_client.access_token,
            "refresh_token": self.auth_client.refresh_token,
            "realm_id": realm_id,
        })

        from quickbooks import QuickBooks
        self.qb_client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self.auth_client.refresh_token,
            company_id=realm_id,
        )
        print("\n✓ Successfully authenticated with QuickBooks Online!")
        return True

    # ─── Transaction Operations ──────────────────────────────────

    def push_transactions(self, transactions: List[UnifiedTransaction]) -> Dict[str, int]:
        """
        Push a batch of reconciled transactions to QuickBooks Online.
        Returns counts of success/failure.
        """
        if not self.qb_client:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        results = {"success": 0, "failed": 0, "skipped": 0}

        for txn in transactions:
            try:
                if txn.recon_status == ReconciliationStatus.MATCHED:
                    results["skipped"] += 1
                    continue

                qbo_txn = self._create_qbo_transaction(txn)
                if qbo_txn:
                    qbo_txn.save(qb=self.qb_client)
                    txn.qbo_txn_id = str(qbo_txn.Id)
                    txn.recon_status = ReconciliationStatus.UPLOADED
                    results["success"] += 1
                else:
                    results["skipped"] += 1

            except Exception as e:
                print(f"[QBO] Failed to push: {txn} — {e}")
                results["failed"] += 1

        return results

    def _create_qbo_transaction(self, txn: UnifiedTransaction):
        """
        Convert a UnifiedTransaction into the appropriate QBO object.
        Maps transaction types to QBO entity types:
        - Income → Deposit or SalesReceipt
        - Expense/Fee → Purchase (Check/CreditCard)
        - Transfer → Transfer
        - Investment → JournalEntry (most flexible)
        """
        from quickbooks.objects.purchase import Purchase
        from quickbooks.objects.deposit import Deposit
        from quickbooks.objects.journalentry import (
            JournalEntry, JournalEntryLine, JournalEntryLineDetail
        )
        from quickbooks.objects.base import Ref

        # Get or create the target account
        account_ref = self._get_account_ref(txn.qbo_account)
        if not account_ref:
            print(f"[QBO] Account not found: {txn.qbo_account}, using journal entry")
            return self._create_journal_entry(txn)

        if txn.txn_type in (TransactionType.EXPENSE, TransactionType.FEE,
                            TransactionType.COMMISSION):
            return self._create_expense(txn, account_ref)
        elif txn.txn_type in (TransactionType.INCOME, TransactionType.DIVIDEND,
                              TransactionType.INTEREST):
            return self._create_deposit(txn, account_ref)
        else:
            # For trades, transfers, and complex transactions, use journal entries
            return self._create_journal_entry(txn)

    def _create_expense(self, txn: UnifiedTransaction, account_ref):
        """Create a QBO Purchase (expense/check)."""
        from quickbooks.objects.purchase import Purchase, PurchaseLine, AccountBasedExpenseLineDetail
        from quickbooks.objects.base import Ref

        purchase = Purchase()
        purchase.PaymentType = "Cash"
        purchase.TxnDate = txn.date.isoformat()
        purchase.PrivateNote = (
            f"[Auto-imported from {txn.source.value}] {txn.memo}"
        )[:4000]

        # Set the bank/payment account
        purchase.AccountRef = self._get_account_ref("Checking")  # Default payment account

        line = PurchaseLine()
        line.Amount = abs(txn.amount)
        line.Description = txn.description[:4000]

        detail = AccountBasedExpenseLineDetail()
        detail.AccountRef = account_ref
        line.AccountBasedExpenseLineDetail = detail
        line.DetailType = "AccountBasedExpenseLineDetail"

        purchase.Line = [line]
        return purchase

    def _create_deposit(self, txn: UnifiedTransaction, account_ref):
        """Create a QBO Deposit."""
        from quickbooks.objects.deposit import Deposit, DepositLine, DepositLineDetail
        from quickbooks.objects.base import Ref

        deposit = Deposit()
        deposit.TxnDate = txn.date.isoformat()
        deposit.DepositToAccountRef = self._get_account_ref("Checking")
        deposit.PrivateNote = (
            f"[Auto-imported from {txn.source.value}] {txn.memo}"
        )[:4000]

        line = DepositLine()
        line.Amount = abs(txn.amount)
        line.Description = txn.description[:4000]

        detail = DepositLineDetail()
        detail.AccountRef = account_ref
        line.DepositLineDetail = detail
        line.DetailType = "DepositLineDetail"

        deposit.Line = [line]
        return deposit

    def _create_journal_entry(self, txn: UnifiedTransaction):
        """
        Create a QBO Journal Entry (most flexible, works for everything).
        This is the safest approach for complex transactions.
        """
        from quickbooks.objects.journalentry import (
            JournalEntry, JournalEntryLine, JournalEntryLineDetail
        )
        from quickbooks.objects.base import Ref

        je = JournalEntry()
        je.TxnDate = txn.date.isoformat()
        je.PrivateNote = (
            f"[{txn.source.value}] {txn.category} | {txn.description[:200]}"
        )[:4000]
        je.DocNumber = f"{txn.source.value}-{txn.id[:8]}"

        # Debit line
        debit_line = JournalEntryLine()
        debit_line.Amount = abs(txn.amount)
        debit_line.Description = txn.description[:4000]
        debit_detail = JournalEntryLineDetail()
        debit_detail.PostingType = "Debit" if txn.amount < 0 else "Credit"
        debit_detail.AccountRef = (
            self._get_account_ref(txn.qbo_account) or
            self._get_account_ref("Uncategorized Expense")
        )
        debit_line.JournalEntryLineDetail = debit_detail
        debit_line.DetailType = "JournalEntryLineDetail"

        # Credit line (offsetting entry)
        credit_line = JournalEntryLine()
        credit_line.Amount = abs(txn.amount)
        credit_line.Description = f"Offset: {txn.description[:200]}"
        credit_detail = JournalEntryLineDetail()
        credit_detail.PostingType = "Credit" if txn.amount < 0 else "Debit"
        credit_detail.AccountRef = self._get_account_ref("Checking")
        credit_line.JournalEntryLineDetail = credit_detail
        credit_line.DetailType = "JournalEntryLineDetail"

        je.Line = [debit_line, credit_line]
        return je

    # ─── Account Helpers ─────────────────────────────────────────

    def _get_account_ref(self, account_name: str):
        """Look up a QBO account by name and return a Ref object."""
        if not self.qb_client:
            return None

        from quickbooks.objects.account import Account
        from quickbooks.objects.base import Ref

        try:
            accounts = Account.filter(
                Name=account_name,
                qb=self.qb_client
            )
            if accounts:
                ref = Ref()
                ref.value = accounts[0].Id
                ref.name = accounts[0].Name
                return ref
        except Exception:
            pass

        return None

    def get_chart_of_accounts(self) -> List[Dict[str, str]]:
        """Fetch the full chart of accounts from QBO."""
        if not self.qb_client:
            return []

        from quickbooks.objects.account import Account
        accounts = Account.all(qb=self.qb_client)
        return [
            {
                "id": a.Id,
                "name": a.Name,
                "type": a.AccountType,
                "sub_type": a.AccountSubType,
                "active": a.Active,
            }
            for a in accounts
        ]

    def get_existing_transactions(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """Fetch existing QBO transactions for a date range."""
        if not self.qb_client:
            return []

        from quickbooks.objects.journalentry import JournalEntry
        from quickbooks.objects.purchase import Purchase
        from quickbooks.objects.deposit import Deposit

        results = []
        for obj_class in [JournalEntry, Purchase, Deposit]:
            try:
                query = (
                    f"SELECT * FROM {obj_class.__name__} "
                    f"WHERE TxnDate >= '{start_date.isoformat()}' "
                    f"AND TxnDate <= '{end_date.isoformat()}'"
                )
                items = obj_class.query(query, qb=self.qb_client)
                results.extend(items)
            except Exception as e:
                print(f"[QBO] Query error for {obj_class.__name__}: {e}")

        return results

    # ─── Token Management ────────────────────────────────────────

    def _load_tokens(self) -> Dict:
        try:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_tokens(self, tokens: Dict):
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f)
        self._tokens = tokens


# ═══════════════════════════════════════════════════════════════════
# QBO File Export (Alternative to API — generates IIF/CSV import files)
# ═══════════════════════════════════════════════════════════════════

class QBOFileExporter:
    """
    Alternative to the API: generates files that can be manually
    imported into QuickBooks. Useful as a fallback or for QBO Desktop.

    Supports:
    - IIF format (QuickBooks Desktop)
    - CSV format (QuickBooks Online bank upload)
    - QBO format (Web Connect / OFX)
    """

    @staticmethod
    def to_csv(transactions: List[UnifiedTransaction], filepath: str):
        """
        Export as CSV that can be imported into QBO via bank feed.
        Format: Date, Description, Amount
        """
        import csv
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Description", "Amount"])
            for txn in sorted(transactions, key=lambda t: t.date):
                writer.writerow([
                    txn.date.strftime("%m/%d/%Y"),
                    txn.description[:200],
                    f"{txn.amount:.2f}",
                ])
        print(f"✓ Exported {len(transactions)} transactions to {filepath}")

    @staticmethod
    def to_iif(transactions: List[UnifiedTransaction], filepath: str):
        """
        Export as IIF (Intuit Interchange Format) for QuickBooks Desktop.
        """
        lines = []
        lines.append("!TRNS\tTRNSID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO")
        lines.append("!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO")
        lines.append("!ENDTRNS")

        for txn in sorted(transactions, key=lambda t: t.date):
            date_str = txn.date.strftime("%m/%d/%Y")
            trns_type = "CHECK" if txn.amount < 0 else "DEPOSIT"
            doc_num = f"{txn.source.value}-{txn.id[:8]}"

            # Main line
            lines.append(
                f"TRNS\t\t{trns_type}\t{date_str}\t"
                f"Checking\t{txn.payee[:40]}\t{txn.amount:.2f}\t"
                f"{doc_num}\t{txn.description[:200]}"
            )
            # Split line (offsetting entry)
            lines.append(
                f"SPL\t\t{trns_type}\t{date_str}\t"
                f"{txn.qbo_account}\t{txn.payee[:40]}\t{-txn.amount:.2f}\t"
                f"{doc_num}\t{txn.description[:200]}"
            )
            lines.append("ENDTRNS")

        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))
        print(f"✓ Exported {len(transactions)} transactions to IIF: {filepath}")

    @staticmethod
    def to_qbo_ofx(transactions: List[UnifiedTransaction], filepath: str):
        """
        Export as QBO/OFX format (Web Connect).
        This can be dragged into QuickBooks Online's bank feed.
        """
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        start = min(t.date for t in transactions).strftime("%Y%m%d")
        end = max(t.date for t in transactions).strftime("%Y%m%d")

        txn_entries = []
        for txn in sorted(transactions, key=lambda t: t.date):
            ttype = "CREDIT" if txn.amount > 0 else "DEBIT"
            txn_entries.append(f"""<STMTTRN>
<TRNTYPE>{ttype}
<DTPOSTED>{txn.date.strftime('%Y%m%d')}
<TRNAMT>{txn.amount:.2f}
<FITID>{txn.id}
<NAME>{txn.payee[:32]}
<MEMO>{txn.description[:255]}
</STMTTRN>""")

        ofx_content = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>{now}
<LANGUAGE>ENG
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>{now}
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<STMTRS>
<CURDEF>USD
<BANKACCTFROM>
<BANKID>000000000
<ACCTID>RECONCILER
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>{start}
<DTEND>{end}
{''.join(txn_entries)}
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""

        with open(filepath, 'w') as f:
            f.write(ofx_content)
        print(f"✓ Exported {len(transactions)} transactions to QBO/OFX: {filepath}")
