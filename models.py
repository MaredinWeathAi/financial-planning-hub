"""
Unified transaction model that all source parsers normalize into.
This is the canonical format used for reconciliation and QBO upload.
"""

from dataclasses import dataclass, field
import datetime as _dt
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import hashlib
import json

date = _dt.date


class TransactionSource(Enum):
    BANK_OF_AMERICA = "bofa"
    INTERACTIVE_BROKERS = "ibkr"
    SCHWAB = "schwab"
    QUICKBOOKS = "qbo"


class TransactionType(Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    TRADE_BUY = "trade_buy"
    TRADE_SELL = "trade_sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    COMMISSION = "commission"
    TAX = "tax"
    ADJUSTMENT = "adjustment"
    OTHER = "other"


class ReconciliationStatus(Enum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    PARTIAL_MATCH = "partial_match"
    CONFLICT = "conflict"
    UPLOADED = "uploaded"
    SKIPPED = "skipped"


@dataclass
class UnifiedTransaction:
    """
    Canonical transaction format. Every parser converts its native
    format into this structure before reconciliation.
    """
    # ── Identity ──
    id: str = ""                                  # Internal unique ID
    source: TransactionSource = TransactionSource.BANK_OF_AMERICA
    source_id: str = ""                           # Original ID from the source
    source_raw: Dict[str, Any] = field(default_factory=dict)  # Raw row for audit

    # ── Core Fields ──
    date: _dt.date = field(default_factory=_dt.date.today)
    settlement_date: Optional[_dt.date] = None
    amount: float = 0.0                           # Positive = inflow, Negative = outflow
    currency: str = "USD"

    # ── Classification ──
    txn_type: TransactionType = TransactionType.OTHER
    category: str = ""                            # Source category (e.g., "DIVIDEND")
    qbo_account: str = ""                         # Target QBO account name

    # ── Description ──
    description: str = ""
    memo: str = ""
    payee: str = ""

    # ── Investment-Specific ──
    symbol: str = ""
    quantity: float = 0.0
    price: float = 0.0
    commission: float = 0.0

    # ── Reconciliation ──
    recon_status: ReconciliationStatus = ReconciliationStatus.UNMATCHED
    matched_txn_id: Optional[str] = None
    match_confidence: float = 0.0
    qbo_txn_id: Optional[str] = None             # QBO transaction ID after upload

    # ── Metadata ──
    account_number: str = ""                      # Last 4 digits only
    created_at: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate a deterministic ID from source + key fields."""
        key = f"{self.source.value}|{self.source_id}|{self.date}|{self.amount}|{self.description}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @property
    def is_debit(self) -> bool:
        return self.amount < 0

    @property
    def is_credit(self) -> bool:
        return self.amount > 0

    @property
    def abs_amount(self) -> float:
        return abs(self.amount)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source.value,
            "source_id": self.source_id,
            "date": self.date.isoformat(),
            "settlement_date": self.settlement_date.isoformat() if self.settlement_date else None,
            "amount": self.amount,
            "currency": self.currency,
            "txn_type": self.txn_type.value,
            "category": self.category,
            "qbo_account": self.qbo_account,
            "description": self.description,
            "memo": self.memo,
            "payee": self.payee,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "recon_status": self.recon_status.value,
            "matched_txn_id": self.matched_txn_id,
            "match_confidence": self.match_confidence,
            "qbo_txn_id": self.qbo_txn_id,
            "account_number": self.account_number,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedTransaction":
        data = data.copy()
        data["source"] = TransactionSource(data["source"])
        data["txn_type"] = TransactionType(data["txn_type"])
        data["recon_status"] = ReconciliationStatus(data["recon_status"])
        data["date"] = date.fromisoformat(data["date"])
        if data.get("settlement_date"):
            data["settlement_date"] = date.fromisoformat(data["settlement_date"])
        data.pop("created_at", None)
        data.pop("source_raw", None)
        return cls(**data)

    def __repr__(self):
        return (
            f"Txn({self.source.value} | {self.date} | "
            f"${self.amount:,.2f} | {self.description[:40]} | "
            f"{self.recon_status.value})"
        )
