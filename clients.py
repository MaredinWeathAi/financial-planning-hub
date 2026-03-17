"""
Client Management.

Stores client information, fee schedules, and billing preferences.
Clients are persisted to a local JSON file (upgrade to DB if needed).
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from config import DATA_DIR

CLIENTS_FILE = os.path.join(DATA_DIR, "clients.json")


# ═══════════════════════════════════════════════════════════════════
# Fee Schedule Models
# ═══════════════════════════════════════════════════════════════════

@dataclass
class FeeItem:
    """A single line item on an invoice."""
    name: str                          # e.g. "Monthly Management Fee"
    description: str = ""              # Detail text shown on invoice
    fee_type: str = "flat"             # "flat", "percent_aum", "percent_pnl", "hourly", "custom"
    rate: float = 0.0                  # Dollar amount, percentage, or hourly rate
    quantity: float = 1.0              # Hours, months, etc.
    minimum: float = 0.0              # Floor amount
    maximum: float = 0.0              # Cap amount (0 = no cap)
    taxable: bool = False
    active: bool = True

    def calculate(self, basis: float = 0.0) -> float:
        """
        Calculate the fee amount.
        basis = AUM, P&L, or other reference value for percentage-based fees.
        """
        if self.fee_type == "flat":
            amount = self.rate * self.quantity
        elif self.fee_type == "percent_aum":
            # Annual rate applied monthly: rate / 12
            amount = basis * (self.rate / 100.0) / 12.0
        elif self.fee_type == "percent_pnl":
            amount = max(0, basis) * (self.rate / 100.0)
        elif self.fee_type == "hourly":
            amount = self.rate * self.quantity
        elif self.fee_type == "custom":
            amount = self.rate
        else:
            amount = self.rate

        # Apply floor and cap
        if self.minimum > 0:
            amount = max(amount, self.minimum)
        if self.maximum > 0:
            amount = min(amount, self.maximum)

        return round(amount, 2)


@dataclass
class FeeSchedule:
    """Collection of fee items that define a client's billing structure."""
    name: str = "Standard"
    items: List[Dict] = field(default_factory=list)
    notes: str = ""

    def get_items(self) -> List[FeeItem]:
        return [FeeItem(**item) for item in self.items]

    def add_item(self, item: FeeItem):
        self.items.append(asdict(item))

    def calculate_total(self, basis: Dict[str, float] = None) -> float:
        basis = basis or {}
        total = 0.0
        for item_data in self.items:
            item = FeeItem(**item_data)
            if not item.active:
                continue
            if item.fee_type == "percent_aum":
                total += item.calculate(basis.get("aum", 0))
            elif item.fee_type == "percent_pnl":
                total += item.calculate(basis.get("pnl", 0))
            else:
                total += item.calculate()
        return round(total, 2)


# ═══════════════════════════════════════════════════════════════════
# Client Model
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Client:
    """A billing client."""
    id: str = ""
    name: str = ""
    company: str = ""
    email: str = ""
    cc_emails: List[str] = field(default_factory=list)   # CC on invoice emails
    phone: str = ""
    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = "US"

    # Billing
    fee_schedule: Dict = field(default_factory=dict)      # Serialized FeeSchedule
    billing_day: int = 1                                  # Day of month to send invoice
    payment_terms: int = 30                               # Net days
    currency: str = "USD"
    tax_rate: float = 0.0                                 # Sales tax % (if applicable)
    tax_id: str = ""                                      # Client's tax ID (for reporting)

    # Account references (link to data sources)
    accounts: Dict[str, str] = field(default_factory=dict)
    # e.g. {"bofa": "****1234", "ibkr": "U1234567", "schwab": "****5678"}

    # Financial Planning (extended data from DocuSign intake forms)
    client_type: str = "individual"             # "individual" or "business"
    financial_profile: Dict[str, Any] = field(default_factory=dict)
    # Stores the full extended profile from docusign_import.profile_to_client_dict()
    # Including: applicant details, co-applicant, dependents, assets, liabilities,
    # insurance, business interests, goals, retirement, estate, tax, risk profile, etc.

    # Metadata
    active: bool = True
    notes: str = ""
    created_at: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            import hashlib
            key = f"{self.name}|{self.email}|{datetime.now().isoformat()}"
            self.id = "cli_" + hashlib.sha256(key.encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def get_fee_schedule(self) -> FeeSchedule:
        if self.fee_schedule:
            return FeeSchedule(**self.fee_schedule)
        return FeeSchedule()

    def set_fee_schedule(self, schedule: FeeSchedule):
        self.fee_schedule = asdict(schedule)

    @property
    def full_address(self) -> str:
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state} {self.zip_code}")
        if self.country and self.country != "US":
            parts.append(self.country)
        return "\n".join(parts)

    @property
    def display_name(self) -> str:
        return self.company or self.name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Client":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════
# Client Storage
# ═══════════════════════════════════════════════════════════════════

class ClientStore:
    """
    Persist clients to a JSON file.
    Simple and portable — upgrade to SQLite or Postgres if needed.
    """

    def __init__(self, filepath: str = None):
        self.filepath = filepath or CLIENTS_FILE
        self._clients: Dict[str, Client] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    data = json.load(f)
                for item in data.get("clients", []):
                    client = Client.from_dict(item)
                    self._clients[client.id] = client
            except Exception as e:
                print(f"Warning: Could not load clients: {e}")

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        data = {"clients": [c.to_dict() for c in self._clients.values()]}
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def add(self, client: Client) -> Client:
        self._clients[client.id] = client
        self._save()
        return client

    def get(self, client_id: str) -> Optional[Client]:
        return self._clients.get(client_id)

    def get_by_name(self, name: str) -> Optional[Client]:
        for c in self._clients.values():
            if c.name.lower() == name.lower() or c.company.lower() == name.lower():
                return c
        return None

    def get_all(self, active_only: bool = True) -> List[Client]:
        clients = list(self._clients.values())
        if active_only:
            clients = [c for c in clients if c.active]
        return sorted(clients, key=lambda c: c.display_name)

    def update(self, client: Client) -> Client:
        self._clients[client.id] = client
        self._save()
        return client

    def delete(self, client_id: str):
        if client_id in self._clients:
            del self._clients[client_id]
            self._save()

    def search(self, query: str) -> List[Client]:
        q = query.lower()
        return [
            c for c in self._clients.values()
            if q in c.name.lower() or q in c.company.lower() or q in c.email.lower()
        ]

    def get_by_email(self, email: str) -> Optional[Client]:
        """Find client by email address."""
        email_lower = email.lower().strip()
        for c in self._clients.values():
            if c.email.lower().strip() == email_lower:
                return c
        return None

    def find_match(self, name: str = "", email: str = "") -> Optional[Client]:
        """Find an existing client by email or name match."""
        if email:
            match = self.get_by_email(email)
            if match:
                return match
        if name:
            match = self.get_by_name(name)
            if match:
                return match
        return None


# ═══════════════════════════════════════════════════════════════════
# Convenience: Create sample clients for testing
# ═══════════════════════════════════════════════════════════════════

def create_sample_clients() -> List[Client]:
    """Create sample clients with fee schedules for testing."""

    # Client 1: Flat monthly management fee
    c1 = Client(
        name="John Smith",
        company="Smith Family Trust",
        email="john@smithfamily.com",
        address_line1="123 Main Street",
        city="Miami", state="FL", zip_code="33101",
        payment_terms=30,
        accounts={"ibkr": "U9876543", "schwab": "****4321"},
        tags=["wealth-management"],
    )
    schedule1 = FeeSchedule(name="Wealth Management — Flat")
    schedule1.add_item(FeeItem(
        name="Monthly Management Fee",
        description="Portfolio management and advisory services",
        fee_type="flat",
        rate=2500.00,
    ))
    schedule1.add_item(FeeItem(
        name="Trading & Execution",
        description="Trade execution and rebalancing",
        fee_type="flat",
        rate=250.00,
    ))
    c1.set_fee_schedule(schedule1)

    # Client 2: AUM-based fee
    c2 = Client(
        name="Sarah Johnson",
        company="Johnson Holdings LLC",
        email="sarah@johnsonholdings.com",
        cc_emails=["accounting@johnsonholdings.com"],
        address_line1="456 Oak Avenue",
        address_line2="Suite 200",
        city="Fort Lauderdale", state="FL", zip_code="33301",
        payment_terms=15,
        accounts={"ibkr": "U1111111", "bofa": "****9999"},
        tags=["aum-fee", "institutional"],
    )
    schedule2 = FeeSchedule(name="AUM-Based")
    schedule2.add_item(FeeItem(
        name="Investment Management Fee",
        description="Annual rate of 1.00% on assets under management, billed monthly",
        fee_type="percent_aum",
        rate=1.0,         # 1% annual
        minimum=500.00,   # $500/mo minimum
    ))
    schedule2.add_item(FeeItem(
        name="Custodian Fee Pass-Through",
        description="IBKR account maintenance",
        fee_type="flat",
        rate=10.00,
    ))
    c2.set_fee_schedule(schedule2)

    # Client 3: Performance fee
    c3 = Client(
        name="Michael Chen",
        company="Chen Capital Partners",
        email="mike@chencapital.com",
        address_line1="789 Biscayne Blvd",
        city="Miami", state="FL", zip_code="33132",
        payment_terms=30,
        accounts={"ibkr": "U2222222", "schwab": "****7777"},
        tags=["performance-fee", "hedge"],
    )
    schedule3 = FeeSchedule(name="2 and 20")
    schedule3.add_item(FeeItem(
        name="Management Fee",
        description="Annual management fee of 2% on AUM, billed monthly",
        fee_type="percent_aum",
        rate=2.0,
    ))
    schedule3.add_item(FeeItem(
        name="Performance Fee",
        description="20% of net new profits above high-water mark",
        fee_type="percent_pnl",
        rate=20.0,
    ))
    c3.set_fee_schedule(schedule3)

    return [c1, c2, c3]
