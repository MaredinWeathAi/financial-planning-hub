#!/usr/bin/env python3
"""
Financial Planning Hub — Central Flask Web Application

This is the unified web server for the entire Financial Planning system.
It serves:
- Client Portal (for individual clients)
- Advisor Portal (for advisors/administrators)
- Dashboard (reconciliation & analytics)
- Comprehensive REST APIs for all system components

Architecture:
- Flask Blueprints for modular API endpoints
- Session-based authentication with JSON user store
- Unified error handling and response formatting
- CORS support for cross-origin requests
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for, render_template_string
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Import all project modules
from config import (
    DATA_DIR, BUSINESS_INFO, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
)
from clients import Client, ClientStore, FeeSchedule, FeeItem, create_sample_clients
from biz_models import (
    BusinessClient, BusinessFinancials, BusinessAccount, BusinessDebt,
    BusinessGoal, BusinessPlan
)
from invoices import Invoice, InvoiceBuilder, InvoiceStore, InvoiceLineItem
from models import UnifiedTransaction, ReconciliationStatus
from reconciler import ReconciliationEngine
from parsers import get_parser, auto_detect_source
from biz_pdf_parser import BusinessPDFImporter, BusinessDataStore
from docusign_import import DocuSignIndividualParser, profile_to_client_dict
from smart_pdf_analyzer import SmartPDFAnalyzer, ProfileMerger, classify_document


# ═══════════════════════════════════════════════════════════════════════════
# App Configuration
# ═══════════════════════════════════════════════════════════════════════════

def create_app(config: Dict = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_url_path="/static", static_folder="static")

    # Configuration
    app.config.update({
        "SECRET_KEY": os.getenv("SECRET_KEY", "dev-secret-key-change-in-production"),
        "SESSION_COOKIE_SECURE": os.getenv("FLASK_ENV") == "production",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(days=7),
    })

    # CORS
    CORS(app, supports_credentials=True)

    # Global data stores (initialized on first request)
    app.client_store = None
    app.invoice_store = None
    app.invoice_builder = None
    app.business_store = None

    # Initialize data directories
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "business"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "invoices"), exist_ok=True)

    return app


app = create_app()


# ═══════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════

def get_data_stores():
    """Initialize and return all data stores on first use."""
    if app.client_store is None:
        app.client_store = ClientStore()
    if app.invoice_store is None:
        app.invoice_store = InvoiceStore()
    if app.invoice_builder is None:
        app.invoice_builder = InvoiceBuilder(business_info=BUSINESS_INFO)
    if app.business_store is None:
        app.business_store = BusinessDataStore()
    return {
        "clients": app.client_store,
        "invoices": app.invoice_store,
        "business": app.business_store,
    }


def get_users_file() -> str:
    """Get path to users.json."""
    return os.path.join(DATA_DIR, "users.json")


def init_users_file():
    """Initialize users.json with default admin account if not exists."""
    users_file = get_users_file()
    if not os.path.exists(users_file):
        os.makedirs(os.path.dirname(users_file), exist_ok=True)
        default_users = {
            "users": [
                {
                    "id": "usr_admin",
                    "email": "admin@mgp.com",
                    "password_hash": generate_password_hash("admin"),
                    "role": "advisor",
                    "name": "Marcelo Zinn",
                    "active": True,
                    "created_at": datetime.now().isoformat(),
                },
                {
                    "id": "usr_client1",
                    "email": "client@mgp.com",
                    "password_hash": generate_password_hash("client"),
                    "role": "client",
                    "name": "Demo Client",
                    "active": True,
                    "created_at": datetime.now().isoformat(),
                }
            ]
        }
        with open(users_file, 'w') as f:
            json.dump(default_users, f, indent=2)


def load_users() -> Dict:
    """Load users from JSON file."""
    init_users_file()
    users_file = get_users_file()
    try:
        with open(users_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading users: {e}")
        return {"users": []}


def save_users(users_data: Dict):
    """Save users to JSON file."""
    users_file = get_users_file()
    os.makedirs(os.path.dirname(users_file), exist_ok=True)
    with open(users_file, 'w') as f:
        json.dump(users_data, f, indent=2)


def api_response(success: bool, data: any = None, error: str = None, status: int = None):
    """Format consistent API response."""
    response = {"success": success}
    if data is not None:
        response["data"] = data
    if error:
        response["error"] = error
    code = status if status else (200 if success else 400)
    return jsonify(response), code


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return api_response(False, error="Authentication required", status=401)
        return f(*args, **kwargs)
    return decorated_function


def get_portal_settings_file() -> str:
    """Get path to portal_settings.json."""
    return os.path.join(DATA_DIR, "portal_settings.json")


def init_portal_settings():
    """Initialize portal_settings.json if not exists."""
    settings_file = get_portal_settings_file()
    if not os.path.exists(settings_file):
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, 'w') as f:
            json.dump({"client_settings": {}}, f, indent=2)


def load_portal_settings() -> Dict:
    """Load portal settings."""
    init_portal_settings()
    settings_file = get_portal_settings_file()
    try:
        with open(settings_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading portal settings: {e}")
        return {"client_settings": {}}


def save_portal_settings(settings: Dict):
    """Save portal settings."""
    settings_file = get_portal_settings_file()
    os.makedirs(os.path.dirname(settings_file), exist_ok=True)
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# HTML Portals
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def root():
    """Root redirects to login."""
    if "user_id" in session:
        return redirect(url_for("advisor_portal"))
    return redirect(url_for("login"))


@app.route("/login")
def login():
    """Serve login portal."""
    portal_path = os.path.join(os.path.dirname(__file__), "auth_portal.html")
    if os.path.exists(portal_path):
        with open(portal_path) as f:
            return f.read()
    # Fallback simple login form
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Financial Planning - Login</title>
        <style>
            body { font-family: sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
            .container { max-width: 400px; margin: 100px auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            h1 { text-align: center; color: #333; }
            form { display: flex; flex-direction: column; gap: 15px; }
            input { padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
            button { padding: 10px; background: #16a34a; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; }
            button:hover { background: #15803d; }
            .error { color: #dc2626; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Financial Planning Hub</h1>
            <form method="POST" action="/api/auth/login">
                <input type="email" name="email" placeholder="Email" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
                <p style="text-align: center; font-size: 12px; color: #666;">
                    Default: admin@mgp.com / admin
                </p>
            </form>
        </div>
        <script>
            document.querySelector('form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        email: formData.get('email'),
                        password: formData.get('password')
                    })
                });
                const data = await res.json();
                if (data.success) {
                    window.location.href = '/advisor';
                } else {
                    alert('Login failed: ' + data.error);
                }
            });
        </script>
    </body>
    </html>
    """)


@app.route("/portal")
def client_portal():
    """Serve client portal."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    portal_path = os.path.join(os.path.dirname(__file__), "client_portal.html")
    if os.path.exists(portal_path):
        with open(portal_path) as f:
            return f.read()
    return render_template_string("<h1>Client Portal</h1><p>Coming soon...</p>")


@app.route("/advisor")
def advisor_portal():
    """Serve advisor portal."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    portal_path = os.path.join(os.path.dirname(__file__), "advisor_portal.html")
    if os.path.exists(portal_path):
        with open(portal_path) as f:
            return f.read()
    return render_template_string("<h1>Advisor Portal</h1><p>Coming soon...</p>")


@app.route("/dashboard")
@app.route("/dashboard/")
def dashboard():
    """Serve reconciliation dashboard."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path) as f:
            return f.read()
    return render_template_string("<h1>Dashboard</h1><p>Coming soon...</p>")


# ═══════════════════════════════════════════════════════════════════════════
# Auth API (Blueprint)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Login with email and password."""
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip()
        password = data.get("password", "")

        if not email or not password:
            return api_response(False, error="Email and password required")

        users_data = load_users()
        user = None
        for u in users_data.get("users", []):
            if u.get("email") == email:
                user = u
                break

        if not user or not check_password_hash(user.get("password_hash", ""), password):
            return api_response(False, error="Invalid credentials")

        if not user.get("active", False):
            return api_response(False, error="User account is inactive")

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["role"] = user.get("role", "client")
        session.permanent = True

        return api_response(True, data={"user_id": user["id"], "email": user["email"]})

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    """Create a new user account."""
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        name = data.get("name", "").strip()
        role = data.get("role", "client")  # default to client

        if not email or not password:
            return api_response(False, error="Email and password required")
        if len(password) < 4:
            return api_response(False, error="Password must be at least 4 characters")
        if role not in ("client", "advisor"):
            return api_response(False, error="Role must be 'client' or 'advisor'")

        users_data = load_users()
        # Check if email already exists
        for u in users_data.get("users", []):
            if u.get("email", "").lower() == email:
                return api_response(False, error="An account with this email already exists")

        import uuid
        new_user = {
            "id": f"usr_{uuid.uuid4().hex[:8]}",
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "name": name or email.split("@")[0].title(),
            "active": True,
            "created_at": datetime.now().isoformat(),
        }
        users_data["users"].append(new_user)
        save_users(users_data)

        # Auto-login after signup
        session["user_id"] = new_user["id"]
        session["email"] = new_user["email"]
        session["role"] = new_user["role"]
        session.permanent = True

        return api_response(True, data={
            "user_id": new_user["id"],
            "email": new_user["email"],
            "role": new_user["role"],
            "message": "Account created successfully"
        })

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def auth_logout():
    """Logout user."""
    session.clear()
    return api_response(True, data={"message": "Logged out"})


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def auth_me():
    """Get current user info."""
    users_data = load_users()
    user = None
    for u in users_data.get("users", []):
        if u["id"] == session["user_id"]:
            user = u
            break

    if not user:
        return api_response(False, error="User not found", status=404)

    return api_response(True, data={
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "client"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# Clients API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/clients", methods=["GET"])
@require_auth
def clients_list():
    """List all clients."""
    try:
        stores = get_data_stores()
        active_only = request.args.get("active_only", "true").lower() == "true"
        clients = stores["clients"].get_all(active_only=active_only)
        return api_response(True, data=[c.to_dict() for c in clients])
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients/<client_id>", methods=["GET"])
@require_auth
def clients_get(client_id: str):
    """Get single client."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)
        return api_response(True, data=client.to_dict())
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients", methods=["POST"])
@require_auth
def clients_create():
    """Create new client."""
    try:
        stores = get_data_stores()
        data = request.get_json() or {}

        client = Client(
            name=data.get("name", ""),
            company=data.get("company", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            address_line1=data.get("address_line1", ""),
            address_line2=data.get("address_line2", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            zip_code=data.get("zip_code", ""),
            country=data.get("country", "US"),
            accounts=data.get("accounts", {}),
            tags=data.get("tags", []),
        )

        # Handle fee schedule if provided
        if "fee_schedule" in data:
            schedule_data = data["fee_schedule"]
            schedule = FeeSchedule(
                name=schedule_data.get("name", "Standard"),
                items=schedule_data.get("items", []),
                notes=schedule_data.get("notes", ""),
            )
            client.set_fee_schedule(schedule)

        client = stores["clients"].add(client)
        return api_response(True, data=client.to_dict(), status=201)

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients/<client_id>", methods=["PUT"])
@require_auth
def clients_update(client_id: str):
    """Update client."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)

        data = request.get_json() or {}

        # Update basic fields
        for field in ["name", "company", "email", "phone", "city", "state", "zip_code", "country"]:
            if field in data:
                setattr(client, field, data[field])

        # Update fee schedule if provided
        if "fee_schedule" in data:
            schedule_data = data["fee_schedule"]
            schedule = FeeSchedule(
                name=schedule_data.get("name", "Standard"),
                items=schedule_data.get("items", []),
                notes=schedule_data.get("notes", ""),
            )
            client.set_fee_schedule(schedule)

        client = stores["clients"].update(client)
        return api_response(True, data=client.to_dict())

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients/<client_id>", methods=["DELETE"])
@require_auth
def clients_delete(client_id: str):
    """Soft-delete client (mark inactive)."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)

        client.active = False
        stores["clients"].update(client)
        return api_response(True, data={"message": "Client deleted"})

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients/search", methods=["GET"])
@require_auth
def clients_search():
    """Search clients."""
    try:
        stores = get_data_stores()
        query = request.args.get("q", "").strip()
        if not query:
            return api_response(False, error="Search query required")

        results = stores["clients"].search(query)
        return api_response(True, data=[c.to_dict() for c in results])

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients/init-samples", methods=["POST"])
@require_auth
def clients_init_samples():
    """Initialize sample clients for testing."""
    try:
        stores = get_data_stores()
        samples = create_sample_clients()
        created = []

        for sample in samples:
            client = stores["clients"].add(sample)
            created.append(client.to_dict())

        return api_response(True, data={"created": len(created), "clients": created}, status=201)

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Business Clients API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/business", methods=["GET"])
@require_auth
def business_list():
    """List all business clients."""
    try:
        stores = get_data_stores()
        businesses = stores["business"].get_all_businesses()
        return api_response(True, data=businesses)
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>", methods=["GET"])
@require_auth
def business_get(business_id: str):
    """Get single business."""
    try:
        stores = get_data_stores()
        business = stores["business"].get_business(business_id)
        if not business:
            return api_response(False, error="Business not found", status=404)
        return api_response(True, data=business)
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business", methods=["POST"])
@require_auth
def business_create():
    """Create new business client."""
    try:
        stores = get_data_stores()
        data = request.get_json() or {}

        business = BusinessClient(
            name=data.get("name", ""),
            ein=data.get("ein", ""),
            entity_type=data.get("entity_type", "llc"),
            industry=data.get("industry", ""),
            description=data.get("description", ""),
            primary_contact_name=data.get("primary_contact_name", ""),
            primary_contact_email=data.get("primary_contact_email", ""),
            primary_contact_phone=data.get("primary_contact_phone", ""),
            address_line1=data.get("address_line1", ""),
            address_line2=data.get("address_line2", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            zip_code=data.get("zip_code", ""),
        )

        biz_dict = business.to_dict()
        stores["business"].add_business(biz_dict)
        return api_response(True, data=biz_dict, status=201)

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>", methods=["PUT"])
@require_auth
def business_update(business_id: str):
    """Update business client."""
    try:
        stores = get_data_stores()
        business = stores["business"].get_business(business_id)
        if not business:
            return api_response(False, error="Business not found", status=404)

        data = request.get_json() or {}

        # Update fields (this is simplified; adjust based on BusinessClient fields)
        for field in ["name", "ein", "entity_type", "industry", "description",
                      "primary_contact_name", "primary_contact_email", "primary_contact_phone",
                      "city", "state", "zip_code"]:
            if field in data:
                setattr(business, field, data[field])

        business = stores["business"].update(business)
        return api_response(True, data=business.to_dict() if hasattr(business, 'to_dict') else business)

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>", methods=["DELETE"])
@require_auth
def business_delete(business_id: str):
    """Delete business client."""
    try:
        stores = get_data_stores()
        stores["business"].delete_business(business_id)
        return api_response(True, data={"message": "Business deleted"})
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>/financials", methods=["GET"])
@require_auth
def business_financials_get(business_id: str):
    """Get financials for a business."""
    try:
        stores = get_data_stores()
        business = stores["business"].get_business(business_id)
        if not business:
            return api_response(False, error="Business not found", status=404)

        # Return financials if available
        financials = getattr(business, "financials", None)
        return api_response(True, data=financials.to_dict() if financials and hasattr(financials, 'to_dict') else {})
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>/financials", methods=["POST"])
@require_auth
def business_financials_add(business_id: str):
    """Add financial data to a business."""
    try:
        stores = get_data_stores()
        business = stores["business"].get_business(business_id)
        if not business:
            return api_response(False, error="Business not found", status=404)

        data = request.get_json() or {}

        # Create or update financials
        financials = BusinessFinancials(
            business_id=business_id,
            fiscal_year=data.get("fiscal_year", datetime.now().year),
            revenue=data.get("revenue", 0.0),
            expenses=data.get("expenses", 0.0),
            gross_profit=data.get("gross_profit", 0.0),
            net_income=data.get("net_income", 0.0),
        )
        business.financials = financials
        business = stores["business"].update(business)

        return api_response(True, data={
            "message": "Financials added",
            "financials": financials.to_dict() if hasattr(financials, 'to_dict') else {}
        })

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Business Ownership & Employees API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/business/<business_id>/people", methods=["GET"])
@require_auth
def business_people_list(business_id: str):
    """List all people (owners, key employees, employees) for a business."""
    try:
        people_file = os.path.join(DATA_DIR, "business", f"{business_id}_people.json")
        if not os.path.exists(people_file):
            return api_response(True, data={"owners": [], "key_employees": [], "employees": []})
        with open(people_file) as f:
            return api_response(True, data=json.load(f))
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>/people", methods=["POST"])
@require_auth
def business_people_add(business_id: str):
    """Add a person (owner, key employee, or employee) to a business.
    Also auto-creates them as an individual client with business_linked=true and a 'B' badge tag.
    """
    try:
        import uuid
        data = request.get_json() or {}

        person_type = data.get("person_type", "employee")  # "owner", "key_employee", "employee"
        if person_type not in ("owner", "key_employee", "employee"):
            return api_response(False, error="person_type must be 'owner', 'key_employee', or 'employee'")

        person = {
            "id": f"per_{uuid.uuid4().hex[:8]}",
            "person_type": person_type,
            "business_id": business_id,
            # Personal info
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "date_of_birth": data.get("date_of_birth", ""),
            "ssn_last4": data.get("ssn_last4", ""),
            # Role info
            "title": data.get("title", ""),
            "ownership_percentage": data.get("ownership_percentage", 0.0),
            "start_date": data.get("start_date", ""),
            "salary": data.get("salary", 0.0),
            "bonus": data.get("bonus", 0.0),
            # Census info
            "marital_status": data.get("marital_status", ""),
            "dependents": data.get("dependents", 0),
            "beneficiary": data.get("beneficiary", ""),
            # Contributions
            "individual_contribution": data.get("individual_contribution", 0.0),
            "individual_contribution_type": data.get("individual_contribution_type", "percent"),  # "percent" or "dollar"
            "corp_contribution": data.get("corp_contribution", 0.0),
            "corp_contribution_type": data.get("corp_contribution_type", "percent"),
            "corp_match_formula": data.get("corp_match_formula", ""),
            # Metadata
            "notes": data.get("notes", ""),
            "active": True,
            "created_at": datetime.now().isoformat(),
            "linked_client_id": None,  # Will be set when auto-linked
        }

        # Load existing people
        os.makedirs(os.path.join(DATA_DIR, "business"), exist_ok=True)
        people_file = os.path.join(DATA_DIR, "business", f"{business_id}_people.json")
        if os.path.exists(people_file):
            with open(people_file) as f:
                people_data = json.load(f)
        else:
            people_data = {"owners": [], "key_employees": [], "employees": []}

        # Determine which list to add to
        list_key = {"owner": "owners", "key_employee": "key_employees", "employee": "employees"}[person_type]
        people_data[list_key].append(person)

        with open(people_file, 'w') as f:
            json.dump(people_data, f, indent=2)

        # Auto-link: create as individual client with "B" badge
        linked_client_id = None
        full_name = f"{person['first_name']} {person['last_name']}".strip()
        if full_name:
            stores = get_data_stores()
            # Check if client already exists by email or name
            existing = None
            if person["email"]:
                existing = stores["clients"].get_by_email(person["email"])
            if not existing and full_name:
                existing = stores["clients"].get_by_name(full_name)

            if existing:
                # Update existing client with business link
                if "business_linked" not in (existing.tags or []):
                    existing.tags = existing.tags or []
                    existing.tags.append("business_linked")
                    existing.tags.append(f"biz:{business_id}")
                    stores["clients"].update(existing)
                linked_client_id = existing.id
            else:
                # Create new individual client
                from clients import Client
                new_client = Client(
                    name=full_name,
                    email=person.get("email", ""),
                    phone=person.get("phone", ""),
                    company="",
                    tags=["business_linked", f"biz:{business_id}"],
                    notes=f"Auto-created from business plan. Role: {person_type.replace('_', ' ').title()}",
                    client_type="individual",
                )
                added = stores["clients"].add(new_client)
                linked_client_id = added.id

            # Update person record with linked client ID
            person["linked_client_id"] = linked_client_id
            with open(people_file, 'w') as f:
                json.dump(people_data, f, indent=2)

        return api_response(True, data={"person": person, "linked_client_id": linked_client_id}, status=201)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>/people/<person_id>", methods=["PUT"])
@require_auth
def business_people_update(business_id: str, person_id: str):
    """Update a person in a business."""
    try:
        people_file = os.path.join(DATA_DIR, "business", f"{business_id}_people.json")
        if not os.path.exists(people_file):
            return api_response(False, error="No people found for this business", status=404)

        with open(people_file) as f:
            people_data = json.load(f)

        data = request.get_json() or {}
        found = False

        for list_key in ["owners", "key_employees", "employees"]:
            for i, person in enumerate(people_data.get(list_key, [])):
                if person["id"] == person_id:
                    # Update all provided fields
                    for key, value in data.items():
                        if key not in ("id", "created_at", "linked_client_id"):
                            person[key] = value
                    person["updated_at"] = datetime.now().isoformat()
                    people_data[list_key][i] = person
                    found = True

                    with open(people_file, 'w') as f:
                        json.dump(people_data, f, indent=2)
                    return api_response(True, data=person)

        if not found:
            return api_response(False, error="Person not found", status=404)

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/business/<business_id>/people/<person_id>", methods=["DELETE"])
@require_auth
def business_people_delete(business_id: str, person_id: str):
    """Remove a person from a business."""
    try:
        people_file = os.path.join(DATA_DIR, "business", f"{business_id}_people.json")
        if not os.path.exists(people_file):
            return api_response(False, error="No people found for this business", status=404)

        with open(people_file) as f:
            people_data = json.load(f)

        found = False
        for list_key in ["owners", "key_employees", "employees"]:
            for i, person in enumerate(people_data.get(list_key, [])):
                if person["id"] == person_id:
                    people_data[list_key].pop(i)
                    found = True
                    break
            if found:
                break

        if not found:
            return api_response(False, error="Person not found", status=404)

        with open(people_file, 'w') as f:
            json.dump(people_data, f, indent=2)

        return api_response(True, data={"message": "Person removed"})

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# PDF Import API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/import/business-pdf", methods=["POST"])
@require_auth
def import_business_pdf():
    """Upload and parse business PDF."""
    try:
        if "file" not in request.files:
            return api_response(False, error="No file provided")

        file = request.files["file"]
        if not file.filename:
            return api_response(False, error="Empty filename")

        # Save uploaded file
        uploads_dir = os.path.join(DATA_DIR, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        filepath = os.path.join(uploads_dir, filename)
        file.save(filepath)

        # Parse PDF
        importer = BusinessPDFImporter()
        try:
            extracted_data = importer.extract_from_pdf(filepath)
            return api_response(True, data={
                "filename": filename,
                "filepath": filepath,
                "extracted_data": extracted_data,
            })
        except Exception as e:
            return api_response(False, error=f"PDF parsing failed: {str(e)}")

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/import/individual-pdf", methods=["POST"])
@require_auth
def import_individual_pdf():
    """Upload and parse individual client PDF."""
    try:
        if "file" not in request.files:
            return api_response(False, error="No file provided")

        file = request.files["file"]
        if not file.filename:
            return api_response(False, error="Empty filename")

        # Save uploaded file
        uploads_dir = os.path.join(DATA_DIR, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        filepath = os.path.join(uploads_dir, filename)
        file.save(filepath)

        # Detect source and parse
        try:
            source = auto_detect_source(filepath)
            parser = get_parser(source)
            if not parser:
                return api_response(False, error=f"No parser for source: {source}")

            transactions = parser.parse(filepath)
            return api_response(True, data={
                "filename": filename,
                "filepath": filepath,
                "source": source,
                "transaction_count": len(transactions),
                "sample_transactions": [t.__dict__ if hasattr(t, '__dict__') else t for t in transactions[:3]],
            })
        except Exception as e:
            return api_response(False, error=f"PDF parsing failed: {str(e)}")

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/import/history", methods=["GET"])
@require_auth
def import_history():
    """List recent imports."""
    try:
        uploads_dir = os.path.join(DATA_DIR, "uploads")
        if not os.path.exists(uploads_dir):
            return api_response(True, data=[])

        files = []
        for f in os.listdir(uploads_dir):
            filepath = os.path.join(uploads_dir, f)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    "filename": f,
                    "size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

        return api_response(True, data=sorted(files, key=lambda x: x["uploaded_at"], reverse=True))

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Smart PDF Upload & Analyze API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/smart-upload/analyze", methods=["POST"])
@require_auth
def smart_upload_analyze():
    """
    Upload one or more PDFs for intelligent analysis.
    Returns classification, extracted data, and routing suggestions.
    Does NOT apply changes — that requires a separate confirm call.
    """
    try:
        if "files" not in request.files and "file" not in request.files:
            return api_response(False, error="No files provided")

        files = request.files.getlist("files") or [request.files.get("file")]
        target_type = request.form.get("target_type", "individual")  # "individual" or "business"
        target_id = request.form.get("target_id", "")  # client_id or business_id

        uploads_dir = os.path.join(DATA_DIR, "uploads", "smart_analyze")
        os.makedirs(uploads_dir, exist_ok=True)

        analyzer = SmartPDFAnalyzer()
        results = []

        for file in files:
            if not file or not file.filename:
                continue

            filename = secure_filename(file.filename)
            filepath = os.path.join(uploads_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
            file.save(filepath)

            # Analyze the PDF
            analysis = analyzer.analyze(filepath)
            analysis["target_type"] = target_type
            analysis["target_id"] = target_id

            results.append(analysis)

        return api_response(True, data={
            "total_files": len(results),
            "successful": sum(1 for r in results if r.get("success")),
            "results": results,
        })

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/smart-upload/confirm", methods=["POST"])
@require_auth
def smart_upload_confirm():
    """
    Confirm and apply analyzed PDF data to a household or business profile.
    Expects JSON body with:
      - target_type: "individual" or "business"
      - target_id: client_id or business_id
      - results: list of analysis results to apply (from /api/smart-upload/analyze)
    """
    try:
        body = request.get_json()
        if not body:
            return api_response(False, error="JSON body required")

        target_type = body.get("target_type", "individual")
        target_id = body.get("target_id", "")
        results_to_apply = body.get("results", [])

        if not target_id:
            return api_response(False, error="target_id is required")

        if not results_to_apply:
            return api_response(False, error="No results to apply")

        stores = get_data_stores()
        applied = []

        if target_type == "individual":
            client = stores["clients"].get(target_id)
            if not client:
                return api_response(False, error=f"Client not found: {target_id}")

            profile = client.financial_profile or {}

            for result in results_to_apply:
                if result.get("success"):
                    profile = ProfileMerger.merge_into_individual_profile(profile, result)
                    applied.append({
                        "filename": result.get("filename", ""),
                        "doc_type": result.get("classification", {}).get("doc_type", ""),
                        "summary": result.get("routing", {}).get("summary", ""),
                    })

            client.financial_profile = profile
            stores["clients"].update(client)

            return api_response(True, data={
                "target_type": "individual",
                "target_id": target_id,
                "client_name": client.display_name,
                "applied_count": len(applied),
                "applied": applied,
            })

        elif target_type == "business":
            business_store = stores.get("business")
            if not business_store:
                return api_response(False, error="Business store not available")

            business = business_store.get_business(target_id)
            if not business:
                return api_response(False, error=f"Business not found: {target_id}")

            for result in results_to_apply:
                if result.get("success"):
                    business = ProfileMerger.merge_into_business_profile(business, result)
                    applied.append({
                        "filename": result.get("filename", ""),
                        "doc_type": result.get("classification", {}).get("doc_type", ""),
                        "summary": result.get("routing", {}).get("summary", ""),
                    })

            business_store.add_business(business)

            return api_response(True, data={
                "target_type": "business",
                "target_id": target_id,
                "business_name": business.get("name", ""),
                "applied_count": len(applied),
                "applied": applied,
            })

        else:
            return api_response(False, error=f"Invalid target_type: {target_type}")

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/smart-upload/history/<target_id>", methods=["GET"])
@require_auth
def smart_upload_history(target_id):
    """Get import history for a client or business."""
    try:
        stores = get_data_stores()
        target_type = request.args.get("type", "individual")

        if target_type == "individual":
            client = stores["clients"].get(target_id)
            if not client:
                return api_response(False, error="Client not found")
            history = (client.financial_profile or {}).get("import_history", [])
        elif target_type == "business":
            business_store = stores.get("business")
            if not business_store:
                return api_response(False, error="Business store not available")
            business = business_store.get_business(target_id)
            if not business:
                return api_response(False, error="Business not found")
            history = business.get("import_history", [])
        else:
            history = []

        return api_response(True, data=history)

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Invoices API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/invoices", methods=["GET"])
@require_auth
def invoices_list():
    """List invoices with optional filtering."""
    try:
        stores = get_data_stores()
        all_invoices = stores["invoices"].get_all()

        # Filter by status if provided
        status = request.args.get("status", "").strip()
        if status:
            all_invoices = [i for i in all_invoices if i.status == status]

        # Filter by month if provided (format: YYYY-MM)
        month = request.args.get("month", "").strip()
        if month:
            all_invoices = [i for i in all_invoices if i.issue_date.startswith(month)]

        return api_response(True, data=[i.to_dict() for i in all_invoices])

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/invoices/<invoice_number>", methods=["GET"])
@require_auth
def invoices_get(invoice_number: str):
    """Get single invoice."""
    try:
        stores = get_data_stores()
        invoice = stores["invoices"].get(invoice_number)
        if not invoice:
            return api_response(False, error="Invoice not found", status=404)
        return api_response(True, data=invoice.to_dict())
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/invoices/generate", methods=["POST"])
@require_auth
def invoices_generate():
    """Generate invoices for a billing period."""
    try:
        stores = get_data_stores()
        data = request.get_json() or {}

        month = data.get("month")
        year = data.get("year")
        client_id = data.get("client_id")  # Optional: generate only for one client
        account_data_map = data.get("account_data_map", {})

        if not month or not year:
            return api_response(False, error="Month and year required")

        # Get clients to invoice
        if client_id:
            client = stores["clients"].get(client_id)
            if not client:
                return api_response(False, error="Client not found")
            clients_to_bill = [client]
        else:
            clients_to_bill = stores["clients"].get_all(active_only=True)

        # Generate invoices
        invoices = app.invoice_builder.build_batch(
            clients=clients_to_bill,
            billing_month=month,
            billing_year=year,
            account_data_map=account_data_map,
        )

        # Save invoices
        stores["invoices"].save_batch(invoices)

        return api_response(True, data={
            "generated": len(invoices),
            "invoices": [i.to_dict() for i in invoices],
        }), 201

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Portal Settings API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/portal/settings/<client_id>", methods=["GET"])
@require_auth
def portal_settings_get(client_id: str):
    """Get portal visibility settings for a client."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)

        settings = load_portal_settings()
        client_settings = settings.get("client_settings", {}).get(client_id, {
            "enabled": True,
            "visible_sections": ["accounts", "transactions", "reports"],
            "can_download": True,
            "can_export": False,
        })

        return api_response(True, data=client_settings)

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/portal/settings/<client_id>", methods=["PUT"])
@require_auth
def portal_settings_update(client_id: str):
    """Update portal visibility settings for a client."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)

        data = request.get_json() or {}
        settings = load_portal_settings()

        if "client_settings" not in settings:
            settings["client_settings"] = {}

        settings["client_settings"][client_id] = {
            "enabled": data.get("enabled", True),
            "visible_sections": data.get("visible_sections", ["accounts", "transactions", "reports"]),
            "can_download": data.get("can_download", True),
            "can_export": data.get("can_export", False),
            "updated_at": datetime.now().isoformat(),
        }

        save_portal_settings(settings)
        return api_response(True, data=settings["client_settings"][client_id])

    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/portal/clients", methods=["GET"])
@require_auth
def portal_clients_list():
    """List all clients with their portal access status."""
    try:
        stores = get_data_stores()
        clients = stores["clients"].get_all(active_only=True)
        settings = load_portal_settings()
        client_settings = settings.get("client_settings", {})

        result = []
        for client in clients:
            client_data = client.to_dict()
            client_data["portal_settings"] = client_settings.get(client.id, {
                "enabled": True,
                "visible_sections": ["accounts", "transactions", "reports"],
                "can_download": True,
                "can_export": False,
            })
            result.append(client_data)

        return api_response(True, data=result)

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Reconciliation API (Keep Existing)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/status", methods=["GET"])
@require_auth
def reconciliation_status():
    """Get reconciliation status."""
    try:
        return api_response(True, data={
            "status": "ready",
            "last_reconciliation": None,
            "pending_transactions": 0,
            "matched_transactions": 0,
        })
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/upload", methods=["POST"])
@require_auth
def reconciliation_upload():
    """Upload file for reconciliation."""
    try:
        if "file" not in request.files:
            return api_response(False, error="No file provided")

        file = request.files["file"]
        if not file.filename:
            return api_response(False, error="Empty filename")

        # Save uploaded file
        uploads_dir = os.path.join(DATA_DIR, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        filepath = os.path.join(uploads_dir, filename)
        file.save(filepath)

        # Detect source and parse
        source = auto_detect_source(filepath)
        parser = get_parser(source)
        if not parser:
            return api_response(False, error=f"No parser for source: {source}")

        transactions = parser.parse(filepath)

        return api_response(True, data={
            "filename": filename,
            "source": source,
            "transaction_count": len(transactions),
        }), 201

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# DocuSign Import API (Individual Client Intake)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/import/docusign", methods=["POST"])
@require_auth
def import_docusign():
    """
    Import one or more DocuSign files (PDF or JSON).
    Parses the form fields, creates or updates the client record.

    Accepts multipart/form-data with one or more files under key 'files'.
    Returns the parsed profile and created/updated client.
    """
    try:
        if "files" not in request.files and "file" not in request.files:
            return api_response(False, error="No files provided")

        # Collect all uploaded files
        uploaded_files = request.files.getlist("files") or []
        if not uploaded_files:
            single = request.files.get("file")
            if single:
                uploaded_files = [single]

        if not uploaded_files:
            return api_response(False, error="No files provided")

        # Save uploaded files and collect paths
        uploads_dir = os.path.join(DATA_DIR, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        saved_paths = []
        saved_names = []

        for file in uploaded_files:
            if not file.filename:
                continue
            filename = secure_filename(file.filename)
            filepath = os.path.join(uploads_dir, filename)
            file.save(filepath)
            saved_paths.append(filepath)
            saved_names.append(filename)

        if not saved_paths:
            return api_response(False, error="No valid files uploaded")

        # Parse with DocuSign parser
        parser = DocuSignIndividualParser()

        if len(saved_paths) == 1:
            profile = parser.parse(saved_paths[0])
        else:
            profile = parser.parse_multiple(saved_paths)

        # Convert profile to client data
        client_data = profile_to_client_dict(profile)
        core = client_data["core"]
        extended = client_data["extended"]

        # Check for existing client
        stores = get_data_stores()
        existing_client = stores["clients"].find_match(
            name=core.get("name", ""),
            email=core.get("email", ""),
        )

        action = "created"
        if existing_client:
            # Update existing client with new data
            action = "updated"
            for field_name in ["name", "email", "phone", "address_line1",
                               "city", "state", "country"]:
                new_val = core.get(field_name, "")
                if new_val:
                    setattr(existing_client, field_name, new_val)

            # Merge tags
            existing_tags = set(existing_client.tags or [])
            existing_tags.update(core.get("tags", []))
            existing_client.tags = list(existing_tags)

            # Merge financial profile
            if existing_client.financial_profile:
                # Deep merge: new data takes priority
                merged = {**existing_client.financial_profile, **extended}
                existing_client.financial_profile = merged
            else:
                existing_client.financial_profile = extended

            existing_client.client_type = "individual"
            client = stores["clients"].update(existing_client)
        else:
            # Create new client
            client = Client(
                name=core.get("name", ""),
                email=core.get("email", ""),
                phone=core.get("phone", ""),
                address_line1=core.get("address_line1", ""),
                city=core.get("city", ""),
                state=core.get("state", ""),
                country=core.get("country", "US"),
                tags=core.get("tags", []),
                client_type="individual",
                financial_profile=extended,
            )
            client = stores["clients"].add(client)

        # Build response with summary of what was imported
        summary = {
            "action": action,
            "client_id": client.id,
            "client_name": client.name,
            "files_processed": saved_names,
            "templates_detected": [profile.source_template] if hasattr(profile, 'source_template') else [],
            "fields_populated": _count_populated_fields(extended),
            "risk_score": extended.get("risk_score", 0),
            "has_co_applicant": "co_applicant" in extended,
            "dependents_count": len(extended.get("dependents", [])),
            "total_assets": extended.get("assets", {}).get("total_assets", 0),
            "total_liabilities": extended.get("liabilities", {}).get("total", 0),
            "net_worth": extended.get("assets", {}).get("total_net_worth", 0),
        }

        return api_response(True, data={
            "summary": summary,
            "client": client.to_dict(),
            "profile": extended,
        }, status=201)

    except json.JSONDecodeError as e:
        return api_response(False, error=f"Invalid JSON file: {str(e)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(False, error=str(e))


@app.route("/api/clients/<client_id>/financial-profile", methods=["GET"])
@require_auth
def client_financial_profile(client_id: str):
    """Get the full financial planning profile for a client."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)
        return api_response(True, data={
            "client_id": client.id,
            "client_name": client.name,
            "client_type": client.client_type,
            "financial_profile": client.financial_profile or {},
        })
    except Exception as e:
        return api_response(False, error=str(e))


@app.route("/api/clients/<client_id>/financial-profile", methods=["PUT"])
@require_auth
def update_financial_profile(client_id: str):
    """Update specific sections of a client's financial profile."""
    try:
        stores = get_data_stores()
        client = stores["clients"].get(client_id)
        if not client:
            return api_response(False, error="Client not found", status=404)

        data = request.get_json() or {}

        if not client.financial_profile:
            client.financial_profile = {}

        # Deep merge the incoming data
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(client.financial_profile.get(key), dict):
                client.financial_profile[key] = {**client.financial_profile[key], **value}
            else:
                client.financial_profile[key] = value

        client = stores["clients"].update(client)
        return api_response(True, data=client.financial_profile)

    except Exception as e:
        return api_response(False, error=str(e))


def _count_populated_fields(data: dict, prefix: str = "") -> int:
    """Count the number of non-empty fields in a nested dict."""
    count = 0
    for key, value in data.items():
        if isinstance(value, dict):
            count += _count_populated_fields(value, f"{prefix}{key}.")
        elif isinstance(value, list):
            if value:
                count += 1
        elif isinstance(value, (int, float)):
            if value:
                count += 1
        elif isinstance(value, str):
            if value:
                count += 1
    return count


# ═══════════════════════════════════════════════════════════════════════════
# System Status API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    """System health check."""
    stores = get_data_stores()
    return api_response(True, data={
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    })


@app.route("/api/stats", methods=["GET"])
@require_auth
def stats():
    """Overall system statistics."""
    try:
        stores = get_data_stores()

        clients = stores["clients"].get_all(active_only=True)
        invoices = stores["invoices"].get_all()

        return api_response(True, data={
            "total_clients": len(clients),
            "total_businesses": len(stores["business"].get_all_businesses()),
            "total_invoices": len(invoices),
            "invoices_by_status": {
                status: len([i for i in invoices if i.status == status])
                for status in ["draft", "sent", "paid", "overdue", "void"]
            },
            "total_invoice_revenue": sum(i.total for i in invoices),
            "data_directory": DATA_DIR,
        })

    except Exception as e:
        return api_response(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Error Handlers
# ═══════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return api_response(False, error="Not found", status=404)


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors."""
    return api_response(False, error="Internal server error", status=500)


# ═══════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n{'='*60}")
    print(f"  Financial Planning Hub")
    print(f"  Running at http://localhost:{port}")
    print(f"{'='*60}")
    print(f"  Client Portal:  http://localhost:{port}/portal")
    print(f"  Advisor Portal: http://localhost:{port}/advisor")
    print(f"  Login:          http://localhost:{port}/login")
    print(f"  Dashboard:      http://localhost:{port}/dashboard")
    print(f"  API Docs:       http://localhost:{port}/api/health")
    print(f"{'='*60}\n")
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
