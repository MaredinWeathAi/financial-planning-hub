"""
Parsers for each financial institution.
Each parser reads the institution's native CSV/export format
and converts rows into UnifiedTransaction objects.
"""

import csv
import io
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any

from models import (
    UnifiedTransaction, TransactionSource, TransactionType,
    ReconciliationStatus
)
from config import ACCOUNT_MAPPING


# ═══════════════════════════════════════════════════════════════════
# Base Parser
# ═══════════════════════════════════════════════════════════════════

class BaseParser(ABC):
    """Base class for all institution parsers."""

    source: TransactionSource

    @abstractmethod
    def parse_file(self, filepath: str) -> List[UnifiedTransaction]:
        """Parse a file and return list of unified transactions."""
        pass

    @abstractmethod
    def parse_rows(self, rows: List[Dict[str, str]]) -> List[UnifiedTransaction]:
        """Parse pre-read rows (e.g., from an API response)."""
        pass

    def _clean_amount(self, value: str) -> float:
        """Parse dollar amounts from various formats."""
        if not value or value.strip() in ("", "--", "N/A"):
            return 0.0
        cleaned = re.sub(r'[,$\s]', '', str(value))
        # Handle parentheses as negative: (100.00) -> -100.00
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _parse_date(self, value: str, formats: List[str] = None) -> date:
        """Try multiple date formats."""
        if not formats:
            formats = [
                "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y",
                "%m/%d/%y", "%Y%m%d", "%d-%b-%Y",
                "%b %d, %Y", "%B %d, %Y",
            ]
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
        raise ValueError(f"Cannot parse date: {value}")


# ═══════════════════════════════════════════════════════════════════
# Bank of America Parser
# ═══════════════════════════════════════════════════════════════════

class BankOfAmericaParser(BaseParser):
    """
    Parses Bank of America CSV exports.

    BofA CSV format (typical checking/savings):
    Date, Description, Amount, Running Bal.

    BofA credit card CSV:
    Posted Date, Reference Number, Payee, Address, Amount
    """

    source = TransactionSource.BANK_OF_AMERICA

    # Map BofA description keywords to transaction types
    TYPE_KEYWORDS = {
        "INTEREST": TransactionType.INTEREST,
        "FEE": TransactionType.FEE,
        "SERVICE CHARGE": TransactionType.FEE,
        "DIVIDEND": TransactionType.DIVIDEND,
        "TRANSFER": TransactionType.TRANSFER,
        "WIRE": TransactionType.TRANSFER,
        "CHECK": TransactionType.EXPENSE,
        "ATM": TransactionType.EXPENSE,
        "PAYMENT": TransactionType.EXPENSE,
        "DEPOSIT": TransactionType.INCOME,
        "DIRECT DEP": TransactionType.INCOME,
        "PAYROLL": TransactionType.INCOME,
    }

    def parse_file(self, filepath: str) -> List[UnifiedTransaction]:
        rows = []
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            # BofA CSVs sometimes have header junk — skip until we find the header row
            content = f.read()

        # Try to find the actual CSV header
        lines = content.strip().split('\n')
        header_idx = 0
        for i, line in enumerate(lines):
            lower = line.lower()
            if 'date' in lower and ('amount' in lower or 'description' in lower):
                header_idx = i
                break

        csv_content = '\n'.join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            rows.append(dict(row))

        return self.parse_rows(rows)

    def parse_rows(self, rows: List[Dict[str, str]]) -> List[UnifiedTransaction]:
        transactions = []
        for row in rows:
            try:
                txn = self._parse_row(row)
                if txn:
                    transactions.append(txn)
            except Exception as e:
                print(f"[BofA] Skipping row: {e} — {row}")
        return transactions

    def _parse_row(self, row: Dict[str, str]) -> Optional[UnifiedTransaction]:
        # Normalize column names (BofA varies between account types)
        norm = {k.strip().lower().replace(' ', '_'): v for k, v in row.items()}

        date_str = norm.get('date') or norm.get('posted_date') or norm.get('posting_date', '')
        if not date_str or not date_str.strip():
            return None

        description = (
            norm.get('description', '') or
            norm.get('payee', '') or
            norm.get('original_description', '')
        ).strip()

        amount = self._clean_amount(
            norm.get('amount', '0')
        )

        txn_type = self._classify(description, amount)
        category_key = txn_type.value.upper()
        bofa_map = ACCOUNT_MAPPING.bofa
        qbo_account = bofa_map.get(category_key, "Checking")

        return UnifiedTransaction(
            source=self.source,
            source_id=norm.get('reference_number', ''),
            source_raw=row,
            date=self._parse_date(date_str),
            amount=amount,
            txn_type=txn_type,
            category=category_key,
            qbo_account=qbo_account,
            description=description,
            payee=norm.get('payee', description[:60]),
            account_number=norm.get('account_number', '')[-4:] if norm.get('account_number') else '',
        )

    def _classify(self, description: str, amount: float) -> TransactionType:
        desc_upper = description.upper()
        for keyword, ttype in self.TYPE_KEYWORDS.items():
            if keyword in desc_upper:
                return ttype
        return TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE


# ═══════════════════════════════════════════════════════════════════
# Interactive Brokers Parser
# ═══════════════════════════════════════════════════════════════════

class InteractiveBrokersParser(BaseParser):
    """
    Parses Interactive Brokers Flex Query CSV exports.

    IBKR Flex Queries can export:
    - Trades: Symbol, DateTime, Quantity, Price, Commission, etc.
    - Cash Transactions: Type, Amount, Description, Date
    - Dividends, Interest, Fees, Withholding Tax
    """

    source = TransactionSource.INTERACTIVE_BROKERS

    # IBKR cash transaction type codes
    IBKR_TYPE_MAP = {
        "Dividends": TransactionType.DIVIDEND,
        "Payment In Lieu Of Dividends": TransactionType.DIVIDEND,
        "Withholding Tax": TransactionType.TAX,
        "Broker Interest Paid": TransactionType.INTEREST,
        "Broker Interest Received": TransactionType.INTEREST,
        "Bond Interest Paid": TransactionType.INTEREST,
        "Bond Interest Received": TransactionType.INTEREST,
        "Other Fees": TransactionType.FEE,
        "Commission Adjustments": TransactionType.COMMISSION,
        "Deposits/Withdrawals": TransactionType.TRANSFER,
        "Deposits": TransactionType.TRANSFER,
        "Withdrawals": TransactionType.TRANSFER,
    }

    def parse_file(self, filepath: str) -> List[UnifiedTransaction]:
        path = Path(filepath)

        # Handle both CSV and XML Flex Query exports
        if path.suffix.lower() == '.xml':
            return self._parse_xml(filepath)

        rows = []
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()

        # IBKR CSVs may have multiple sections — we parse trades + cash txns
        transactions = []
        transactions.extend(self._parse_csv_section(content, "Trades"))
        transactions.extend(self._parse_csv_section(content, "Cash Transactions"))
        transactions.extend(self._parse_csv_section(content, "CashTransaction"))

        # If no sections found, try parsing as a flat CSV
        if not transactions:
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                rows.append(dict(row))
            transactions = self.parse_rows(rows)

        return transactions

    def _parse_csv_section(self, content: str, section_name: str) -> List[UnifiedTransaction]:
        """Extract and parse a named section from an IBKR multi-section CSV."""
        lines = content.split('\n')
        section_lines = []
        in_section = False

        for line in lines:
            if line.startswith(section_name + ',') or line.startswith(f'"{section_name}"'):
                # Check if it's a header vs data line
                if 'Header' in line:
                    in_section = True
                    # Extract column names from this header line
                    parts = next(csv.reader(io.StringIO(line)))
                    section_lines.append(','.join(parts[2:]))  # Skip section name + "Header"
                    continue
                elif in_section and 'Data' in line:
                    parts = next(csv.reader(io.StringIO(line)))
                    section_lines.append(','.join(parts[2:]))  # Skip section name + "Data"
                elif in_section and ('Total' in line or 'SubTotal' in line):
                    continue
                elif in_section:
                    section_lines.append(line)
            elif in_section and not line.startswith(section_name):
                break

        if not section_lines:
            return []

        csv_text = '\n'.join(section_lines)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = [dict(row) for row in reader]
        return self.parse_rows(rows)

    def _parse_xml(self, filepath: str) -> List[UnifiedTransaction]:
        """Parse IBKR Flex Query XML export."""
        tree = ET.parse(filepath)
        root = tree.getroot()
        transactions = []

        # Parse trades
        for trade in root.iter('Trade'):
            txn = self._xml_trade_to_txn(trade.attrib)
            if txn:
                transactions.append(txn)

        # Parse cash transactions
        for cash in root.iter('CashTransaction'):
            txn = self._xml_cash_to_txn(cash.attrib)
            if txn:
                transactions.append(txn)

        return transactions

    def _xml_trade_to_txn(self, attrib: Dict) -> Optional[UnifiedTransaction]:
        try:
            qty = float(attrib.get('quantity', 0))
            price = float(attrib.get('tradePrice', 0))
            commission = abs(float(attrib.get('ibCommission', 0)))
            proceeds = float(attrib.get('proceeds', qty * price))

            return UnifiedTransaction(
                source=self.source,
                source_id=attrib.get('tradeID', ''),
                source_raw=attrib,
                date=self._parse_date(attrib.get('tradeDate', attrib.get('dateTime', '')[:8]),
                                      ["%Y%m%d", "%Y-%m-%d"]),
                amount=proceeds - commission,
                txn_type=TransactionType.TRADE_BUY if qty > 0 else TransactionType.TRADE_SELL,
                category="TRADE",
                qbo_account=ACCOUNT_MAPPING.ibkr.get("TRADE", "Investment Trading"),
                description=f"{'BUY' if qty > 0 else 'SELL'} {abs(qty)} {attrib.get('symbol', '')} @ {price}",
                symbol=attrib.get('symbol', ''),
                quantity=qty,
                price=price,
                commission=commission,
                currency=attrib.get('currency', 'USD'),
            )
        except (ValueError, KeyError) as e:
            print(f"[IBKR] Skipping trade: {e}")
            return None

    def _xml_cash_to_txn(self, attrib: Dict) -> Optional[UnifiedTransaction]:
        try:
            amount = float(attrib.get('amount', 0))
            ibkr_type = attrib.get('type', 'Other')
            txn_type = self.IBKR_TYPE_MAP.get(ibkr_type, TransactionType.OTHER)
            category = ibkr_type.upper().replace(' ', '_')

            return UnifiedTransaction(
                source=self.source,
                source_id=attrib.get('transactionID', ''),
                source_raw=attrib,
                date=self._parse_date(attrib.get('dateTime', attrib.get('reportDate', ''))[:8],
                                      ["%Y%m%d", "%Y-%m-%d"]),
                amount=amount,
                txn_type=txn_type,
                category=category,
                qbo_account=ACCOUNT_MAPPING.ibkr.get(category, "Investment Account"),
                description=attrib.get('description', ibkr_type),
                symbol=attrib.get('symbol', ''),
                currency=attrib.get('currency', 'USD'),
            )
        except (ValueError, KeyError) as e:
            print(f"[IBKR] Skipping cash txn: {e}")
            return None

    def parse_rows(self, rows: List[Dict[str, str]]) -> List[UnifiedTransaction]:
        """Parse flat CSV rows (when section parsing doesn't apply)."""
        transactions = []
        for row in rows:
            try:
                norm = {k.strip(): v.strip() for k, v in row.items() if k}

                # Determine if this is a trade or cash transaction
                if 'Quantity' in norm or 'TradePrice' in norm or 'T. Price' in norm:
                    txn = self._parse_trade_row(norm)
                else:
                    txn = self._parse_cash_row(norm)

                if txn:
                    transactions.append(txn)
            except Exception as e:
                print(f"[IBKR] Skipping row: {e}")
        return transactions

    def _parse_trade_row(self, row: Dict) -> Optional[UnifiedTransaction]:
        qty = self._clean_amount(row.get('Quantity', '0'))
        price = self._clean_amount(row.get('TradePrice', row.get('T. Price', '0')))
        comm = abs(self._clean_amount(row.get('IBCommission', row.get('Comm/Fee', '0'))))
        proceeds = self._clean_amount(row.get('Proceeds', str(qty * price)))

        date_str = row.get('TradeDate', row.get('Date/Time', row.get('DateTime', '')))
        if not date_str:
            return None

        symbol = row.get('Symbol', '')
        return UnifiedTransaction(
            source=self.source,
            source_id=row.get('TradeID', row.get('OrderID', '')),
            source_raw=row,
            date=self._parse_date(date_str.split(';')[0].split(',')[0].strip()),
            amount=proceeds - comm,
            txn_type=TransactionType.TRADE_BUY if qty > 0 else TransactionType.TRADE_SELL,
            category="TRADE",
            qbo_account="Investment Trading",
            description=f"{'BUY' if qty > 0 else 'SELL'} {abs(qty)} {symbol} @ {price}",
            symbol=symbol,
            quantity=qty,
            price=price,
            commission=comm,
        )

    def _parse_cash_row(self, row: Dict) -> Optional[UnifiedTransaction]:
        amount = self._clean_amount(row.get('Amount', '0'))
        date_str = row.get('Date', row.get('Settle Date', row.get('DateTime', '')))
        if not date_str:
            return None

        ibkr_type = row.get('Type', row.get('Description', 'Other'))
        txn_type = self.IBKR_TYPE_MAP.get(ibkr_type, TransactionType.OTHER)

        return UnifiedTransaction(
            source=self.source,
            source_id=row.get('TransactionID', ''),
            source_raw=row,
            date=self._parse_date(date_str.split(';')[0].strip()),
            amount=amount,
            txn_type=txn_type,
            category=ibkr_type.upper().replace(' ', '_'),
            qbo_account=ACCOUNT_MAPPING.ibkr.get(ibkr_type.upper().replace(' ', '_'), "Investment Account"),
            description=row.get('Description', ibkr_type),
            symbol=row.get('Symbol', ''),
        )


# ═══════════════════════════════════════════════════════════════════
# Charles Schwab Parser
# ═══════════════════════════════════════════════════════════════════

class SchwabParser(BaseParser):
    """
    Parses Charles Schwab CSV exports.

    Schwab brokerage CSV format:
    "Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"

    Schwab checking CSV format:
    "Date","Type","Check #","Description","Withdrawal (-)","Deposit (+)","RunningBalance"
    """

    source = TransactionSource.SCHWAB

    ACTION_MAP = {
        "Buy": TransactionType.TRADE_BUY,
        "Sell": TransactionType.TRADE_SELL,
        "Sell Short": TransactionType.TRADE_SELL,
        "Buy to Cover": TransactionType.TRADE_BUY,
        "Qualified Dividend": TransactionType.DIVIDEND,
        "Cash Dividend": TransactionType.DIVIDEND,
        "Non-Qualified Div": TransactionType.DIVIDEND,
        "Reinvest Dividend": TransactionType.DIVIDEND,
        "Reinvest Shares": TransactionType.DIVIDEND,
        "Long Term Cap Gain": TransactionType.DIVIDEND,
        "Short Term Cap Gain": TransactionType.DIVIDEND,
        "Bank Interest": TransactionType.INTEREST,
        "Bond Interest": TransactionType.INTEREST,
        "Credit Interest": TransactionType.INTEREST,
        "Margin Interest": TransactionType.FEE,
        "ADR Mgmt Fee": TransactionType.FEE,
        "Foreign Tax Paid": TransactionType.TAX,
        "Wire Funds": TransactionType.TRANSFER,
        "Wire Funds Received": TransactionType.TRANSFER,
        "MoneyLink Transfer": TransactionType.TRANSFER,
        "Funds Received": TransactionType.TRANSFER,
        "Journal": TransactionType.TRANSFER,
        "Misc Cash Entry": TransactionType.ADJUSTMENT,
        "Service Fee": TransactionType.FEE,
    }

    def parse_file(self, filepath: str) -> List[UnifiedTransaction]:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()

        # Schwab CSVs often start with account info header lines
        lines = content.strip().split('\n')
        header_idx = 0
        for i, line in enumerate(lines):
            lower = line.lower().replace('"', '')
            if 'date' in lower and ('action' in lower or 'type' in lower or 'description' in lower):
                header_idx = i
                break

        # Also strip trailing summary lines (Schwab adds totals)
        end_idx = len(lines)
        for i in range(len(lines) - 1, header_idx, -1):
            if lines[i].strip().startswith('"Transactions Total"') or lines[i].strip() == '':
                end_idx = i
            else:
                break

        csv_content = '\n'.join(lines[header_idx:end_idx])
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = [dict(row) for row in reader]

        return self.parse_rows(rows)

    def parse_rows(self, rows: List[Dict[str, str]]) -> List[UnifiedTransaction]:
        transactions = []
        for row in rows:
            try:
                txn = self._parse_row(row)
                if txn:
                    transactions.append(txn)
            except Exception as e:
                print(f"[Schwab] Skipping row: {e} — {row}")
        return transactions

    def _parse_row(self, row: Dict[str, str]) -> Optional[UnifiedTransaction]:
        norm = {k.strip().replace('"', ''): v.strip().replace('"', '') for k, v in row.items() if k}

        date_str = norm.get('Date', '')
        if not date_str or date_str.lower() in ('', 'pending'):
            return None

        # Handle "as of MM/DD/YYYY" dates
        date_str = re.sub(r'as of\s+', '', date_str).strip()

        action = norm.get('Action', norm.get('Type', ''))
        description = norm.get('Description', '')
        symbol = norm.get('Symbol', '')
        quantity = self._clean_amount(norm.get('Quantity', '0'))
        price = self._clean_amount(norm.get('Price', '0'))
        fees = abs(self._clean_amount(norm.get('Fees & Comm', norm.get('Fees', '0'))))

        # Amount field
        amount = self._clean_amount(norm.get('Amount', '0'))
        if amount == 0:
            # For checking accounts with separate columns
            withdrawal = self._clean_amount(norm.get('Withdrawal (-)', '0'))
            deposit = self._clean_amount(norm.get('Deposit (+)', '0'))
            amount = deposit - abs(withdrawal) if deposit else -abs(withdrawal)

        txn_type = self.ACTION_MAP.get(action, TransactionType.OTHER)
        if txn_type == TransactionType.OTHER and amount != 0:
            txn_type = TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE

        category = action.upper().replace(' ', '_') if action else "OTHER"
        qbo_account = ACCOUNT_MAPPING.schwab.get(category, "Investment Account")

        desc_parts = [action, symbol, description]
        full_desc = ' — '.join([p for p in desc_parts if p])

        return UnifiedTransaction(
            source=self.source,
            source_id='',
            source_raw=row,
            date=self._parse_date(date_str),
            amount=amount,
            txn_type=txn_type,
            category=category,
            qbo_account=qbo_account,
            description=full_desc,
            payee=description[:60],
            symbol=symbol,
            quantity=quantity,
            price=price,
            commission=fees,
        )


# ═══════════════════════════════════════════════════════════════════
# QuickBooks Export Parser (for reconciliation comparison)
# ═══════════════════════════════════════════════════════════════════

class QuickBooksParser(BaseParser):
    """
    Parses QuickBooks Online CSV exports (for reconciliation matching).
    Used when comparing what's already in QBO vs what's coming from other sources.
    """

    source = TransactionSource.QUICKBOOKS

    def parse_file(self, filepath: str) -> List[UnifiedTransaction]:
        rows = []
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return self.parse_rows(rows)

    def parse_rows(self, rows: List[Dict[str, str]]) -> List[UnifiedTransaction]:
        transactions = []
        for row in rows:
            try:
                norm = {k.strip(): v.strip() for k, v in row.items() if k}

                date_str = norm.get('Date', norm.get('Transaction Date', ''))
                if not date_str:
                    continue

                amount = self._clean_amount(norm.get('Amount', '0'))
                if amount == 0:
                    debit = self._clean_amount(norm.get('Debit', '0'))
                    credit = self._clean_amount(norm.get('Credit', '0'))
                    amount = credit - debit if credit else -debit

                txn = UnifiedTransaction(
                    source=self.source,
                    source_id=norm.get('Num', norm.get('Transaction ID', '')),
                    source_raw=row,
                    date=self._parse_date(date_str),
                    amount=amount,
                    txn_type=TransactionType.OTHER,
                    category=norm.get('Transaction Type', ''),
                    qbo_account=norm.get('Account', ''),
                    description=norm.get('Description', norm.get('Memo/Description', '')),
                    payee=norm.get('Name', norm.get('Payee', '')),
                    qbo_txn_id=norm.get('Transaction ID', ''),
                )
                transactions.append(txn)
            except Exception as e:
                print(f"[QBO] Skipping row: {e}")
        return transactions


# ═══════════════════════════════════════════════════════════════════
# Parser Registry
# ═══════════════════════════════════════════════════════════════════

PARSERS = {
    "bofa": BankOfAmericaParser(),
    "ibkr": InteractiveBrokersParser(),
    "schwab": SchwabParser(),
    "qbo": QuickBooksParser(),
}


def get_parser(source: str) -> BaseParser:
    """Get parser by source name."""
    if source not in PARSERS:
        raise ValueError(f"Unknown source: {source}. Available: {list(PARSERS.keys())}")
    return PARSERS[source]


def auto_detect_source(filepath: str) -> Optional[str]:
    """Try to auto-detect the file source from content."""
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            head = f.read(2000).lower()

        if 'interactive brokers' in head or 'ibkr' in head or 'flexqueryresponse' in head:
            return "ibkr"
        elif 'schwab' in head or 'charles schwab' in head:
            return "schwab"
        elif 'bank of america' in head or 'bofa' in head:
            return "bofa"
        elif 'quickbooks' in head or 'intuit' in head:
            return "qbo"
        # Check column patterns
        elif 'action' in head and 'symbol' in head and 'fees & comm' in head:
            return "schwab"
        elif 'tradeid' in head or 'ibcommission' in head:
            return "ibkr"
        elif 'running bal' in head:
            return "bofa"

    except Exception:
        pass

    return None
