# Financial Planning Hub - Quick Start Guide

## Getting Started in 5 Minutes

### 1. Install Dependencies

```bash
pip install flask flask-cors werkzeug
```

### 2. Start the Server

```bash
cd "/sessions/busy-determined-volta/mnt/Financial Planning"
python app.py
```

You'll see:
```
============================================================
  Financial Planning Hub
  Running at http://localhost:5000
============================================================
  Client Portal:  http://localhost:5000/portal
  Advisor Portal: http://localhost:5000/advisor
  Login:          http://localhost:5000/login
  Dashboard:      http://localhost:5000/dashboard
  API Docs:       http://localhost:5000/api/health
============================================================
```

### 3. Open Your Browser

Visit: `http://localhost:5000/login`

**Default Credentials:**
- Email: `admin@mgp.com`
- Password: `admin`

---

## Key URLs

| URL | Purpose |
|-----|---------|
| http://localhost:5000/login | Login page |
| http://localhost:5000/advisor | Advisor dashboard |
| http://localhost:5000/portal | Client portal |
| http://localhost:5000/dashboard | Reconciliation dashboard |
| http://localhost:5000/api/health | API health check |
| http://localhost:5000/api/stats | System statistics |

---

## Common API Calls

### Check System Status

```bash
curl http://localhost:5000/api/health
```

### Login

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@mgp.com",
    "password": "admin"
  }' \
  -c cookies.txt
```

### List All Clients

```bash
curl http://localhost:5000/api/clients \
  -b cookies.txt
```

### Create Sample Clients

```bash
curl -X POST http://localhost:5000/api/clients/init-samples \
  -b cookies.txt
```

### Generate Invoices for February 2026

```bash
curl -X POST http://localhost:5000/api/invoices/generate \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "month": 2,
    "year": 2026,
    "account_data_map": {
      "cli_1234567890": {
        "aum": 1500000,
        "pnl": 0
      }
    }
  }'
```

### Get System Statistics

```bash
curl http://localhost:5000/api/stats \
  -b cookies.txt
```

---

## Python Usage Examples

### Create a Client

```python
import requests
import json

# Login
session = requests.Session()
session.post('http://localhost:5000/api/auth/login', json={
    'email': 'admin@mgp.com',
    'password': 'admin'
})

# Create client
response = session.post('http://localhost:5000/api/clients', json={
    'name': 'Jane Doe',
    'company': 'Doe Holdings',
    'email': 'jane@doeholdings.com',
    'city': 'Miami',
    'state': 'FL'
})

client = response.json()['data']
print(f"Created client: {client['id']}")
```

### Generate Invoices

```python
# Get all active clients
clients_response = session.get('http://localhost:5000/api/clients?active_only=true')
clients = clients_response.json()['data']

# Generate invoices for February 2026
invoice_response = session.post(
    'http://localhost:5000/api/invoices/generate',
    json={
        'month': 2,
        'year': 2026,
        'account_data_map': {
            client['id']: {'aum': 1500000, 'pnl': 0}
            for client in clients
        }
    }
)

invoices = invoice_response.json()['data']['invoices']
print(f"Generated {len(invoices)} invoices")
```

### Search Clients

```python
response = session.get('http://localhost:5000/api/clients/search?q=Smith')
results = response.json()['data']
for client in results:
    print(f"{client['name']} - {client['email']}")
```

---

## Data Directory Structure

After running the app, you'll find:

```
./data/
├── clients.json              # All client data
├── invoices_data.json        # All invoices
├── invoice_registry.json     # Invoice numbering
├── users.json               # User accounts
├── portal_settings.json     # Portal visibility
├── business/                # Business client data
├── invoices/                # Generated PDF invoices
└── uploads/                 # Uploaded files
```

---

## Common Tasks

### Add a New User

Edit `./data/users.json`:

```python
from werkzeug.security import generate_password_hash

# In Python:
password_hash = generate_password_hash("newpassword")
print(password_hash)
```

Then add to `users.json`:

```json
{
  "id": "usr_client_1",
  "email": "john@smithfamily.com",
  "password_hash": "<paste the hash here>",
  "role": "client",
  "name": "John Smith",
  "active": true,
  "created_at": "2026-02-26T10:30:00"
}
```

### Update Business Info (for Invoices)

Edit `config.py`:

```python
BUSINESS_INFO = {
    "name": "Your Name",
    "company": "Your Company LLC",
    "address": "123 Main Street\nMiami, FL 33101",
    "email": "you@yourcompany.com",
    "phone": "(305) 555-1234",
    "logo_path": "",
    "footer": "Thank you for your business.",
}
```

### Upload a Statement for Reconciliation

```bash
curl -X POST http://localhost:5000/api/import/individual-pdf \
  -b cookies.txt \
  -F "file=@/path/to/statement.csv"
```

### Change Admin Password

```python
from werkzeug.security import generate_password_hash
import json

new_hash = generate_password_hash("newadminpassword")

with open('./data/users.json', 'r') as f:
    data = json.load(f)

for user in data['users']:
    if user['email'] == 'admin@mgp.com':
        user['password_hash'] = new_hash

with open('./data/users.json', 'w') as f:
    json.dump(data, f, indent=2)

print("Admin password updated")
```

---

## Troubleshooting

### Port 5000 Already in Use

Use a different port:

```bash
PORT=8080 python app.py
```

### Module Not Found Error

Make sure you're in the correct directory:

```bash
cd "/sessions/busy-determined-volta/mnt/Financial Planning"
python app.py
```

### Users File Not Found

The app creates `./data/users.json` automatically on first login attempt.

### Can't Login

Check that `./data/users.json` exists:

```bash
cat ./data/users.json
```

If it doesn't exist, the default admin account will be created.

---

## Next Steps

1. **Create Sample Data**
   ```bash
   curl -X POST http://localhost:5000/api/clients/init-samples -b cookies.txt
   ```

2. **Generate Test Invoices**
   - Use the API or web interface

3. **Explore the Portals**
   - Admin: http://localhost:5000/advisor
   - Client: http://localhost:5000/portal
   - Dashboard: http://localhost:5000/dashboard

4. **Read Full Documentation**
   - See `APP_DOCUMENTATION.md` for complete API reference

---

## Performance Tips

- **For Large Datasets**: Consider migrating to a database (SQLite, PostgreSQL)
- **For Multiple Users**: Use a production WSGI server (Gunicorn, Waitress)
- **For Security**: Set `FLASK_ENV=production` and strong `SECRET_KEY`

---

## Architecture Overview

```
┌─────────────────────────────────────┐
│         Web Browsers                 │
│  (Admin / Client / Public)           │
└────────────┬────────────────────────┘
             │ HTTP/HTTPS
             ▼
┌─────────────────────────────────────┐
│      Flask Web Application           │
│  ┌─────────────────────────────────┐ │
│  │  HTML Portals (Login/Admin/     │ │
│  │  Client/Dashboard)              │ │
│  └─────────────────────────────────┘ │
│  ┌─────────────────────────────────┐ │
│  │  REST API Endpoints             │ │
│  │  (Clients, Invoices, Business)  │ │
│  └─────────────────────────────────┘ │
│  ┌─────────────────────────────────┐ │
│  │  Data Stores & Business Logic   │ │
│  │  (ClientStore, InvoiceBuilder)  │ │
│  └─────────────────────────────────┘ │
└────────────┬────────────────────────┘
             │ JSON File I/O
             ▼
┌─────────────────────────────────────┐
│    ./data/ Directory                 │
│  (clients.json, users.json, etc.)    │
└─────────────────────────────────────┘
```

---

## API Response Format

**Success:**
```json
{
  "success": true,
  "data": { ... }
}
```

**Error:**
```json
{
  "success": false,
  "error": "Error message"
}
```

---

## Support

- **Full Docs**: `APP_DOCUMENTATION.md`
- **Code**: See inline comments in `app.py`
- **Config**: `config.py`
- **Issues**: Check error messages in Flask console output

Enjoy using the Financial Planning Hub!
