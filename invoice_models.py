"""
Client & Fee Models.

Defines the data structures for clients, fee schedules,
invoice line items, and completed invoices.
"""

import json
import os
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from config import DATA_DIR

CLIENTS_FILE = os.path.join(DATA_DIR, "clients.json")
INVOICES_DIR = os.path.join(DATA_DIR, "invoices")


class FeeType(Enum):
    MANAGEMENT_FEE = "management_fee"
    PERFORMANCE_FEE = "performance_fee"
    ADVISORY_FEE = "advisory_fee"
    PLATFORM_FEE = "platform_fee"
    TRANSACTION_FEE = "transaction_fee"
    ADMINISTRATION_FEE = "admin_fee"
    CUSTODY_FEE = "custody_fee"
    REPORTING_FEE = "reporting_fee"
    PASSTHROUGH = "passthrough"
    CUSTOM = "custom"


class InvoiceStatus(Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


@dataclass
class FeeScheduleItem:
    """A single fee rule in a client's fee schedule."""
    fee_type: FeeType = FeeType.MANAGEMENT_FEE
    label: str = ""
    rate: float = 0.0
    rate_type: str = "percent"              # "percent" | "flat" | "per_trade"
    applies_to: str = ""                    # "aum", "gains", "trades", "fixed"
    min_fee: float = 0.0
    max_fee: float = 0.0
    active: bool = True
    notes: str = ""

    def calculate(self, basis: float, trade_count: int = 0) -> float:
        if not self.active:
            return 0.0
        if self.rate_type == "percent":
            amount = basis * (self.rate / 100.0)
        elif self.rate_type == "per_trade":
            amount = trade_count * self.rate
        else:
            amount = self.rate
        if self.min_fee > 0:
            amount = max(amount, self.min_fee)
        if self.max_fee > 0:
            amount = min(amount, self.max_fee)
        return round(amount, 2)

    def to_dict(self) -> dict:
        d = vars(self).copy()
        d["fee_type"] = self.fee_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FeeScheduleItem":
        d = d.copy()
        d["fee_type"] = FeeType(d["fee_type"])
        return cls(**d)


@dataclass
class Client:
    """A client who receives fee invoices."""
    id: str = ""
    name: str = ""
    company: str = ""
    email: str = ""
    cc_emails: List[str] = field(default_factory=list)
    phone: str = ""
    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    account_numbers: Dict[str, str] = field(default_factory=dict)
    aum: float = 0.0
    fee_schedule: List[FeeScheduleItem] = field(default_factory=list)
    invoice_day: int = 1
    payment_terms: int = 30
    currency: str = "USD"
    active: bool = True
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(
                f"{self.name}|{self.email}|{datetime.now()}".encode()
            ).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def full_address(self) -> str:
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state} {self.zip_code}")
        return "\n".join(p for p in parts if p.strip())

    def to_dict(self) -> dict:
        d = {}
        for k, v in vars(self).items():
            if k == "fee_schedule":
                d[k] = [f.to_dict() for f in v]
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Client":
        d = d.copy()
        d["fee_schedule"] = [FeeScheduleItem.from_dict(f) for f in d.get("fee_schedule", [])]
        return cls(**d)


@dataclass
class InvoiceLineItem:
    """A single line on an invoice."""
    description: str = ""
    fee_type: str = ""
    quantity: float = 1.0
    unit_label: str = ""
    rate: float = 0.0
    basis: float = 0.0
    amount: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return vars(self)

    @classmethod
    def from_dict(cls, d: dict) -> "InvoiceLineItem":
        return cls(**d)


@dataclass
class Invoice:
    """A complete fee invoice for a client."""
    id: str = ""
    invoice_number: str = ""
    client_id: str = ""
    client_name: str = ""
    client_email: str = ""
    client_address: str = ""
    period_start: str = ""
    period_end: str = ""
    period_label: str = ""
    company_name: str = ""
    company_address: str = ""
    company_email: str = ""
    company_phone: str = ""
    company_logo_path: str = ""
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    issue_date: str = ""
    due_date: str = ""
    payment_terms: int = 30
    status: InvoiceStatus = InvoiceStatus.DRAFT
    sent_at: Optional[str] = None
    paid_at: Optional[str] = None
    notes: str = ""
    internal_notes: str = ""
    footer_text: str = "Thank you for your business."
    pdf_path: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(
                f"{self.client_id}|{self.period_label}|{datetime.now()}".encode()
            ).hexdigest()[:12]

    def calculate_totals(self):
        self.subtotal = round(sum(item.amount for item in self.line_items), 2)
        self.tax_amount = round(self.subtotal * (self.tax_rate / 100.0), 2)
        self.total = round(self.subtotal + self.tax_amount, 2)

    def to_dict(self) -> dict:
        d = {}
        for k, v in vars(self).items():
            if k == "line_items":
                d[k] = [li.to_dict() for li in v]
            elif k == "status":
                d[k] = v.value
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Invoice":
        d = d.copy()
        d["line_items"] = [InvoiceLineItem.from_dict(li) for li in d.get("line_items", [])]
        d["status"] = InvoiceStatus(d.get("status", "draft"))
        return cls(**d)


class ClientStore:
    """Simple JSON-backed client database."""

    def __init__(self, filepath: str = None):
        self.filepath = filepath or CLIENTS_FILE
        self._clients: Dict[str, Client] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                data = json.load(f)
            self._clients = {c["id"]: Client.from_dict(c) for c in data.get("clients", [])}

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        with open(self.filepath, 'w') as f:
            json.dump({"clients": [c.to_dict() for c in self._clients.values()]}, f, indent=2)

    def add(self, client: Client) -> Client:
        self._clients[client.id] = client
        self._save()
        return client

    def get(self, client_id: str) -> Optional[Client]:
        return self._clients.get(client_id)

    def get_by_name(self, name: str) -> Optional[Client]:
        for c in self._clients.values():
            if c.name.lower() == name.lower():
                return c
        return None

    def list_all(self, active_only: bool = True) -> List[Client]:
        clients = list(self._clients.values())
        if active_only:
            clients = [c for c in clients if c.active]
        return sorted(clients, key=lambda c: c.name)

    def update(self, client: Client):
        self._clients[client.id] = client
        self._save()

    def delete(self, client_id: str):
        self._clients.pop(client_id, None)
        self._save()


class InvoiceStore:
    """JSON-backed invoice persistence."""

    def __init__(self, directory: str = None):
        self.directory = directory or INVOICES_DIR
        os.makedirs(self.directory, exist_ok=True)
        self._index_file = os.path.join(self.directory, "_index.json")
        self._index: Dict[str, dict] = {}
        self._load_index()

    def _load_index(self):
        if os.path.exists(self._index_file):
            with open(self._index_file) as f:
                self._index = json.load(f)

    def _save_index(self):
        with open(self._index_file, 'w') as f:
            json.dump(self._index, f, indent=2)

    def save(self, invoice: Invoice) -> str:
        filepath = os.path.join(self.directory, f"inv_{invoice.id}.json")
        with open(filepath, 'w') as f:
            json.dump(invoice.to_dict(), f, indent=2)
        self._index[invoice.id] = {
            "id": invoice.id, "invoice_number": invoice.invoice_number,
            "client_id": invoice.client_id, "client_name": invoice.client_name,
            "period_label": invoice.period_label, "total": invoice.total,
            "status": invoice.status.value, "issue_date": invoice.issue_date,
            "pdf_path": invoice.pdf_path,
        }
        self._save_index()
        return filepath

    def get(self, invoice_id: str) -> Optional[Invoice]:
        filepath = os.path.join(self.directory, f"inv_{invoice_id}.json")
        if os.path.exists(filepath):
            with open(filepath) as f:
                return Invoice.from_dict(json.load(f))
        return None

    def list_all(self, client_id: str = None) -> List[dict]:
        items = list(self._index.values())
        if client_id:
            items = [i for i in items if i["client_id"] == client_id]
        return sorted(items, key=lambda i: i.get("issue_date", ""), reverse=True)

    def get_next_invoice_number(self, prefix: str = "INV") -> str:
        existing = [v.get("invoice_number", "") for v in self._index.values()
                    if v.get("invoice_number", "").startswith(prefix)]
        if not existing:
            return f"{prefix}-0001"
        max_num = 0
        for num_str in existing:
            try:
                max_num = max(max_num, int(num_str.split("-")[-1]))
            except (ValueError, IndexError):
                pass
        return f"{prefix}-{max_num + 1:04d}"
