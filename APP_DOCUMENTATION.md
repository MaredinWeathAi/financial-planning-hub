# Financial Planning Hub - Flask Application Documentation

## Overview

`app.py` is the central web application for the Financial Planning system. It provides a unified Flask server that serves all four portals (Login, Client Portal, Advisor Portal, Dashboard) and comprehensive REST APIs for managing clients, businesses, invoices, and reconciliation.

**Location:** `/sessions/busy-determined-volta/mnt/Financial Planning/app.py`

## Quick Start

### Installation

```bash
# Install required dependencies
pip install flask flask-cors werkzeug

# Navigate to project directory
cd "/sessions/busy-determined-volta/mnt/Financial Planning"

# Run the application
python app.py
```

The application will start on `http://localhost:5000` by default.

### Default Login Credentials

- **Email:** `admin@mgp.com`
- **Password:** `admin`

These credentials can be changed by editing `./data/users.json`.

## Application Architecture

### Port Layout

| Path | Purpose | Requires Auth |
|------|---------|---------------|
| `/` | Root (redirects to login or advisor portal) | No |
| `/login` | Authentication portal | No |
| `/portal` | Client Portal | Yes |
| `/advisor` | Advisor Portal | Yes |
| `/dashboard` | Reconciliation Dashboard | Yes |

### Data Stores

All data is persisted to JSON files in the `./data` directory:

- `./data/clients.json` - Individual clients
- `./data/invoices_data.json` - Generated invoices
- `./data/invoice_registry.json` - Invoice tracking
- `./data/users.json` - User accounts
- `./data/portal_settings.json` - Portal visibility settings
- `./data/business/` - Business client data
- `./data/uploads/` - Uploaded PDFs for import

## REST API Reference

All API responses follow a consistent format:

```json
{
  "success": true,
  "data": { ... }
}
```

or on error:

```json
{
  "success": false,
  "error": "Error message"
}
```

### Authentication API (`/api/auth`)

#### POST `/api/auth/login`
Login with email and password.

**Request:**
```json
{
  "email": "admin@mgp.com",
  "password": "admin"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_admin",
    "email": "admin@mgp.com"
  }
}
```

**Status Codes:** 200 (success), 400 (invalid credentials)

#### POST `/api/auth/logout`
Logout current user (requires authentication).

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Logged out"
  }
}
```

#### GET `/api/auth/me`
Get current user info (requires authentication).

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "usr_admin",
    "email": "admin@mgp.com",
    "name": "Administrator",
    "role": "advisor"
  }
}
```

---

### Clients API (`/api/clients`)

#### GET `/api/clients`
List all clients.

**Query Parameters:**
- `active_only` (bool, default: true) - Only return active clients

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "cli_1234567890",
      "name": "John Smith",
      "company": "Smith Family Trust",
      "email": "john@smithfamily.com",
      "phone": "(305) 555-1234",
      "address_line1": "123 Main Street",
      "city": "Miami",
      "state": "FL",
      "zip_code": "33101",
      "country": "US",
      "active": true,
      "tags": ["wealth-management"],
      "created_at": "2026-01-15T10:30:00"
    }
  ]
}
```

#### GET `/api/clients/<client_id>`
Get a single client by ID.

**Response:** Single client object (same format as list)

#### POST `/api/clients`
Create a new client.

**Request:**
```json
{
  "name": "Jane Doe",
  "company": "Doe Holdings LLC",
  "email": "jane@doeholdings.com",
  "phone": "(305) 555-5678",
  "address_line1": "456 Oak Avenue",
  "city": "Fort Lauderdale",
  "state": "FL",
  "zip_code": "33301",
  "country": "US",
  "accounts": {
    "ibkr": "U1234567",
    "schwab": "****1111"
  },
  "tags": ["aum-fee"],
  "fee_schedule": {
    "name": "AUM-Based",
    "items": [
      {
        "name": "Investment Management Fee",
        "description": "1% annual on AUM, billed monthly",
        "fee_type": "percent_aum",
        "rate": 1.0,
        "quantity": 1.0,
        "minimum": 500.0,
        "maximum": 0,
        "taxable": false,
        "active": true
      }
    ],
    "notes": ""
  }
}
```

**Response:** 201 (created) with new client object

#### PUT `/api/clients/<client_id>`
Update an existing client.

**Request:** Same format as POST (any field can be omitted)

**Response:** 200 with updated client object

#### DELETE `/api/clients/<client_id>`
Soft-delete a client (marks as inactive).

**Response:** 200

#### GET `/api/clients/search?q=<query>`
Search clients by name, company, or email.

**Response:** Array of matching clients

#### POST `/api/clients/init-samples`
Initialize sample clients for testing.

**Response:**
```json
{
  "success": true,
  "data": {
    "created": 3,
    "clients": [ ... ]
  }
}
```

---

### Business Clients API (`/api/business`)

#### GET `/api/business`
List all business clients.

**Response:** Array of business client objects

#### GET `/api/business/<business_id>`
Get a single business client.

**Response:** Business client object

#### POST `/api/business`
Create a new business client.

**Request:**
```json
{
  "name": "TechCorp Inc",
  "ein": "12-3456789",
  "entity_type": "c_corp",
  "industry": "Software Development",
  "description": "Custom enterprise software development",
  "primary_contact_name": "Alice Johnson",
  "primary_contact_email": "alice@techcorp.com",
  "primary_contact_phone": "(305) 555-9999",
  "address_line1": "789 Tech Drive",
  "city": "Miami",
  "state": "FL",
  "zip_code": "33139"
}
```

**Response:** 201 with new business object

#### PUT `/api/business/<business_id>`
Update a business client.

**Response:** 200 with updated business object

#### DELETE `/api/business/<business_id>`
Delete a business client.

**Response:** 200

#### GET `/api/business/<business_id>/financials`
Get financials for a business.

**Response:**
```json
{
  "success": true,
  "data": {
    "business_id": "biz_123",
    "fiscal_year": 2026,
    "revenue": 500000.00,
    "expenses": 300000.00,
    "gross_profit": 200000.00,
    "net_income": 150000.00
  }
}
```

#### POST `/api/business/<business_id>/financials`
Add financial data to a business.

**Request:**
```json
{
  "fiscal_year": 2026,
  "revenue": 500000.00,
  "expenses": 300000.00,
  "gross_profit": 200000.00,
  "net_income": 150000.00
}
```

**Response:** 200

---

### Invoices API (`/api/invoices`)

#### GET `/api/invoices`
List all invoices with optional filtering.

**Query Parameters:**
- `status` - Filter by status (draft, sent, paid, overdue, void)
- `month` - Filter by month (format: YYYY-MM)

**Response:** Array of invoice objects

#### GET `/api/invoices/<invoice_number>`
Get a single invoice by invoice number.

**Response:** Invoice object

#### POST `/api/invoices/generate`
Generate invoices for a billing period.

**Request:**
```json
{
  "month": 2,
  "year": 2026,
  "client_id": "cli_1234567890",  // Optional: generate for single client
  "account_data_map": {
    "cli_1234567890": {
      "aum": 1500000.00,
      "pnl": 45000.00
    }
  }
}
```

**Response:** 201
```json
{
  "success": true,
  "data": {
    "generated": 1,
    "invoices": [
      {
        "invoice_number": "INV-2026-0001",
        "client_id": "cli_1234567890",
        "client_name": "John Smith",
        "issue_date": "2026-02-26",
        "due_date": "2026-03-28",
        "subtotal": 2500.00,
        "tax_amount": 0,
        "total": 2500.00,
        "status": "draft",
        "line_items": [...]
      }
    ]
  }
}
```

---

### PDF Import API (`/api/import`)

#### POST `/api/import/business-pdf`
Upload and parse a business PDF (e.g., tax return, financial statement).

**Request:** Form data with file upload
```
Content-Type: multipart/form-data
file: <PDF file>
```

**Response:** 200
```json
{
  "success": true,
  "data": {
    "filename": "business-tax-return.pdf",
    "filepath": "./data/uploads/business-tax-return.pdf",
    "extracted_data": {
      "entity_name": "TechCorp Inc",
      "ein": "12-3456789",
      "revenue": 500000.00,
      ...
    }
  }
}
```

#### POST `/api/import/individual-pdf`
Upload and parse an individual client PDF (e.g., bank statement, brokerage statement).

**Request:** Form data with file upload

**Response:** 200
```json
{
  "success": true,
  "data": {
    "filename": "schwab-statement.csv",
    "filepath": "./data/uploads/schwab-statement.csv",
    "source": "schwab",
    "transaction_count": 47,
    "sample_transactions": [...]
  }
}
```

#### GET `/api/import/history`
List recent imports.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "filename": "statement.csv",
      "size": 125000,
      "uploaded_at": "2026-02-26T10:30:00"
    }
  ]
}
```

---

### Portal Settings API (`/api/portal`)

#### GET `/api/portal/settings/<client_id>`
Get portal visibility settings for a client.

**Response:**
```json
{
  "success": true,
  "data": {
    "enabled": true,
    "visible_sections": ["accounts", "transactions", "reports"],
    "can_download": true,
    "can_export": false
  }
}
```

#### PUT `/api/portal/settings/<client_id>`
Update portal visibility settings for a client.

**Request:**
```json
{
  "enabled": true,
  "visible_sections": ["accounts", "reports"],
  "can_download": true,
  "can_export": false
}
```

**Response:** 200 with updated settings

#### GET `/api/portal/clients`
List all clients with their portal access status.

**Response:** Array of client objects with nested `portal_settings`

---

### Reconciliation API (`/api/reconciliation`)

#### GET `/api/status`
Get reconciliation status.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "ready",
    "last_reconciliation": null,
    "pending_transactions": 0,
    "matched_transactions": 0
  }
}
```

#### POST `/api/upload`
Upload a file for reconciliation.

**Request:** Form data with file upload

**Response:** 201
```json
{
  "success": true,
  "data": {
    "filename": "bofa-checking.csv",
    "source": "bofa",
    "transaction_count": 32
  }
}
```

---

### System Status API

#### GET `/api/health`
System health check (no authentication required).

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2026-02-26T10:30:00",
    "version": "1.0.0"
  }
}
```

#### GET `/api/stats`
Overall system statistics.

**Response:**
```json
{
  "success": true,
  "data": {
    "total_clients": 3,
    "total_businesses": 2,
    "total_invoices": 15,
    "invoices_by_status": {
      "draft": 0,
      "sent": 10,
      "paid": 5,
      "overdue": 0,
      "void": 0
    },
    "total_invoice_revenue": 45000.00,
    "data_directory": "./data"
  }
}
```

---

## Data Models

### Client Object

```json
{
  "id": "cli_1234567890",
  "name": "John Smith",
  "company": "Smith Family Trust",
  "email": "john@smithfamily.com",
  "cc_emails": [],
  "phone": "(305) 555-1234",
  "address_line1": "123 Main Street",
  "address_line2": "",
  "city": "Miami",
  "state": "FL",
  "zip_code": "33101",
  "country": "US",
  "fee_schedule": {
    "name": "Standard",
    "items": [...],
    "notes": ""
  },
  "billing_day": 1,
  "payment_terms": 30,
  "currency": "USD",
  "tax_rate": 0.0,
  "tax_id": "",
  "accounts": {
    "ibkr": "U9876543",
    "schwab": "****4321"
  },
  "active": true,
  "notes": "",
  "created_at": "2026-01-15T10:30:00",
  "tags": ["wealth-management"]
}
```

### Invoice Object

```json
{
  "invoice_number": "INV-2026-0001",
  "client_id": "cli_1234567890",
  "client_name": "John Smith",
  "client_company": "Smith Family Trust",
  "client_email": "john@smithfamily.com",
  "client_address": "123 Main Street\nMiami, FL 33101",
  "from_name": "Your Name",
  "from_company": "Your Company LLC",
  "from_address": "123 Main Street\nMiami, FL 33101",
  "from_email": "you@yourcompany.com",
  "from_phone": "(305) 555-1234",
  "issue_date": "2026-02-26",
  "due_date": "2026-03-28",
  "period_start": "2026-02-01",
  "period_end": "2026-02-28",
  "line_items": [
    {
      "description": "Monthly Management Fee — February 2026",
      "detail": "$2,500.00/month",
      "quantity": 1.0,
      "unit_price": 2500.00,
      "amount": 2500.00,
      "taxable": false
    }
  ],
  "subtotal": 2500.00,
  "tax_rate": 0.0,
  "tax_amount": 0.0,
  "total": 2500.00,
  "amount_paid": 0.0,
  "balance_due": 2500.00,
  "currency": "USD",
  "notes": "",
  "terms": "Payment due within 30 days of invoice date.",
  "footer": "Thank you for your business.",
  "status": "draft",
  "sent_at": "",
  "paid_at": "",
  "pdf_path": ""
}
```

### Fee Item Object

```json
{
  "name": "Investment Management Fee",
  "description": "Annual rate of 1.00% on assets under management, billed monthly",
  "fee_type": "percent_aum",
  "rate": 1.0,
  "quantity": 1.0,
  "minimum": 500.0,
  "maximum": 0.0,
  "taxable": false,
  "active": true
}
```

**Fee Types:**
- `flat` - Fixed dollar amount
- `percent_aum` - Percentage of Assets Under Management
- `percent_pnl` - Percentage of Profit/Loss
- `hourly` - Hourly rate × quantity
- `custom` - Custom calculation

---

## Usage Examples

### Create a New Client with Fee Schedule

```python
import requests

# Login first
login_response = requests.post('http://localhost:5000/api/auth/login', json={
    'email': 'admin@mgp.com',
    'password': 'admin'
}, cookies={})

cookies = login_response.cookies

# Create client
response = requests.post('http://localhost:5000/api/clients', json={
    'name': 'Jane Doe',
    'company': 'Doe Holdings LLC',
    'email': 'jane@doeholdings.com',
    'address_line1': '456 Oak Avenue',
    'city': 'Fort Lauderdale',
    'state': 'FL',
    'zip_code': '33301',
    'fee_schedule': {
        'name': 'AUM-Based',
        'items': [
            {
                'name': 'Investment Management Fee',
                'description': '1% annual on AUM',
                'fee_type': 'percent_aum',
                'rate': 1.0,
                'minimum': 500.0,
                'active': True
            }
        ]
    }
}, cookies=cookies)

print(response.json())
```

### Generate Invoices for a Month

```python
response = requests.post('http://localhost:5000/api/invoices/generate', json={
    'month': 2,
    'year': 2026,
    'account_data_map': {
        'cli_1234567890': {
            'aum': 1500000.00,
            'pnl': 0
        }
    }
}, cookies=cookies)

invoices = response.json()['data']['invoices']
for invoice in invoices:
    print(f"{invoice['invoice_number']}: ${invoice['total']}")
```

### Update Portal Visibility for a Client

```python
response = requests.put(
    'http://localhost:5000/api/portal/settings/cli_1234567890',
    json={
        'enabled': True,
        'visible_sections': ['accounts', 'reports'],
        'can_download': True,
        'can_export': False
    },
    cookies=cookies
)

print(response.json())
```

---

## Configuration

### Environment Variables

Set these in your environment or `.env` file:

```bash
# Flask Configuration
PORT=5000
SECRET_KEY=your-secret-key-here
FLASK_ENV=development  # or production

# Data Directory
DATA_DIR=./data

# Business Info (for invoices)
BUSINESS_NAME="Your Company LLC"
BUSINESS_ADDRESS="123 Main Street\nMiami, FL 33101"
BUSINESS_PHONE="(305) 555-1234"
```

### User Management

Edit `./data/users.json` to manage users:

```json
{
  "users": [
    {
      "id": "usr_admin",
      "email": "admin@mgp.com",
      "password_hash": "... (use generate_password_hash)",
      "role": "advisor",
      "name": "Administrator",
      "active": true,
      "created_at": "2026-01-15T10:30:00"
    },
    {
      "id": "usr_client_1",
      "email": "john@smithfamily.com",
      "password_hash": "...",
      "role": "client",
      "name": "John Smith",
      "active": true,
      "created_at": "2026-01-15T10:30:00"
    }
  ]
}
```

**To generate a password hash:**

```python
from werkzeug.security import generate_password_hash
hash = generate_password_hash("mypassword")
print(hash)
```

---

## Authentication & Security

### Session-Based Authentication

The app uses Flask sessions with the following security features:

- **HttpOnly Cookies** - Sessions cannot be accessed via JavaScript
- **Secure Cookie Flag** - In production, cookies only sent over HTTPS
- **SameSite=Lax** - CSRF protection
- **7-day Expiration** - Sessions expire after 7 days

### Required Auth

All API endpoints except `/api/health` and `/api/auth/login` require authentication.

Missing or invalid session returns:
```json
{
  "success": false,
  "error": "Authentication required"
}
```

Status Code: **401 Unauthorized**

---

## Error Handling

### Error Response Format

All errors follow this format:

```json
{
  "success": false,
  "error": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request (validation error) |
| 401 | Unauthorized (requires auth) |
| 404 | Not found |
| 500 | Internal server error |

---

## Integration with Existing Modules

### ClientStore Integration

```python
from clients import ClientStore

store = ClientStore()

# Get all active clients
clients = store.get_all(active_only=True)

# Search clients
results = store.search("Smith")

# Get single client
client = store.get("cli_1234567890")
```

### InvoiceBuilder Integration

```python
from invoices import InvoiceBuilder
from config import BUSINESS_INFO

builder = InvoiceBuilder(business_info=BUSINESS_INFO)

# Build invoice for client
invoice = builder.build_invoice(
    client=client,
    billing_month=2,
    billing_year=2026,
    account_data={'aum': 1500000.00}
)

# Build batch
invoices = builder.build_batch(
    clients=clients,
    billing_month=2,
    billing_year=2026
)
```

### Reconciliation Engine Integration

```python
from reconciler import ReconciliationEngine
from parsers import get_parser

engine = ReconciliationEngine()

# Parse transactions
parser = get_parser('bofa')
transactions = parser.parse('./data/bofa.csv')

# Add and reconcile
engine.add_transactions(transactions)
summary = engine.reconcile()

print(f"Matched: {summary['matched']}")
print(f"Unmatched: {summary['unmatched']}")
```

---

## Deployment

### Local Development

```bash
python app.py
```

Access at: `http://localhost:5000`

### Production Deployment

#### Using Gunicorn

```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

#### Using Docker

```dockerfile
FROM python:3.10
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "app:app"]
```

#### Environment Variables for Production

```bash
export FLASK_ENV=production
export SECRET_KEY=your-production-secret-key
export PORT=5000
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'flask'"

Install Flask:
```bash
pip install flask flask-cors
```

### Session not persisting

Ensure `SECRET_KEY` is set and consistent across requests.

### CORS errors from frontend

The app includes `flask_cors` for cross-origin requests. If errors persist:

```python
CORS(app, resources={r"/api/*": {"origins": "*"}})
```

### Users not loading

Check that `./data/users.json` exists and is valid JSON:

```bash
python -m json.tool ./data/users.json
```

---

## File Structure

```
Financial Planning/
├── app.py                    # This Flask application
├── config.py                 # Configuration
├── clients.py               # Client models and storage
├── invoices.py              # Invoice models and PDF generation
├── biz_models.py            # Business client models
├── models.py                # Transaction models
├── reconciler.py            # Reconciliation engine
├── parsers.py               # CSV/PDF parsers
├── biz_pdf_parser.py        # Business PDF parser
├── auth_portal.html         # Login page
├── client_portal.html       # Client portal UI
├── advisor_portal.html      # Advisor portal UI
├── dashboard/
│   └── index.html          # Reconciliation dashboard
└── data/
    ├── clients.json         # Client data
    ├── invoices_data.json   # Invoice data
    ├── users.json           # User accounts
    ├── portal_settings.json # Portal visibility
    ├── business/            # Business client data
    ├── invoices/            # Generated PDFs
    └── uploads/             # Uploaded files
```

---

## Future Enhancements

Potential improvements:

1. **Database Migration** - SQLite or PostgreSQL instead of JSON
2. **Email Integration** - Send invoices via SMTP
3. **PDF Generation** - Generate invoice PDFs via reportlab
4. **Advanced Reporting** - Business intelligence dashboards
5. **Audit Logging** - Track all system changes
6. **Two-Factor Authentication** - Enhanced security
7. **Role-Based Access Control** - Fine-grained permissions
8. **API Documentation** - Swagger/OpenAPI specs
9. **Webhooks** - Event notifications
10. **Batch Operations** - Bulk client/invoice management

---

## Support & Questions

For issues or questions about the Financial Planning Hub, refer to:

- **API Documentation** - This file
- **Code Comments** - See inline documentation in `app.py`
- **Config** - `config.py` for system settings
- **Data Models** - Individual module files for model definitions
