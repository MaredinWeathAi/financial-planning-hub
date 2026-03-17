"""
Automated Data Fetchers.

These modules pull transaction data programmatically from
each institution's API, so you don't have to manually export CSVs.

Status by institution:
  ✅ Interactive Brokers — Flex Web Service API (fully automated)
  🟡 Bank of America — Plaid API (requires Plaid account, ~$500/mo minimum)
  🟡 Schwab — developer.schwab.com API (requires registration)
  🟡 QuickBooks — OAuth2 API (python-quickbooks, fully supported)
  ⚪ Bank of America — Manual CSV download (always works, free)
  ⚪ Schwab — Manual CSV download (always works, free)
"""

import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
from pathlib import Path

from config import IBKR_FLEX_TOKEN, IBKR_QUERY_ID, IMPORT_DIR


# ═══════════════════════════════════════════════════════════════════
# Interactive Brokers Flex Web Service
# ═══════════════════════════════════════════════════════════════════

class IBKRFlexFetcher:
    """
    Fetches reports from IBKR Flex Web Service API.

    Setup:
    1. Log into IBKR Client Portal
    2. Go to Performance & Reports > Flex Queries
    3. Create an Activity Flex Query with sections:
       - Cash Transactions (Select All)
       - Trades (Select All)
       - Open Positions (optional)
       - Dividends (optional — included in Cash Transactions)
    4. Note the Query ID
    5. Go to Settings > Flex Web Service
    6. Generate a Flex Token
    7. Set IBKR_FLEX_TOKEN and IBKR_QUERY_ID in config.py

    The API has two steps:
    1. Request a report (returns a reference code)
    2. Download the report using the reference code
    """

    BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"

    def __init__(self, token: str = None, query_id: str = None):
        self.token = token or IBKR_FLEX_TOKEN
        self.query_id = query_id or IBKR_QUERY_ID

    def fetch(self, output_dir: str = None, format: str = "csv") -> Optional[str]:
        """
        Fetch the latest Flex Query report.
        Returns the filepath of the downloaded report.
        """
        try:
            import requests
        except ImportError:
            print("Install requests: pip install requests")
            return None

        output_dir = output_dir or IMPORT_DIR
        os.makedirs(output_dir, exist_ok=True)

        print("[IBKR] Requesting Flex Query report...")

        # Step 1: Request the report
        request_url = (
            f"{self.BASE_URL}/SendRequest"
            f"?t={self.token}"
            f"&q={self.query_id}"
            f"&v=3"
        )

        response = requests.get(request_url)
        if response.status_code != 200:
            print(f"[IBKR] Request failed: HTTP {response.status_code}")
            return None

        # Parse the XML response to get the reference code
        root = ET.fromstring(response.text)
        status = root.find('.//Status')
        if status is not None and status.text != "Success":
            error_msg = root.find('.//ErrorMessage')
            print(f"[IBKR] Error: {error_msg.text if error_msg is not None else 'Unknown'}")
            return None

        ref_code = root.find('.//ReferenceCode')
        if ref_code is None:
            print("[IBKR] No reference code in response")
            return None

        ref = ref_code.text
        print(f"[IBKR] Reference code: {ref}")

        # Step 2: Poll for the report (may take a few seconds)
        for attempt in range(10):
            time.sleep(3)
            print(f"[IBKR] Checking report status (attempt {attempt + 1}/10)...")

            download_url = (
                f"{self.BASE_URL}/GetStatement"
                f"?t={self.token}"
                f"&q={ref}"
                f"&v=3"
            )

            resp = requests.get(download_url)
            if resp.status_code != 200:
                continue

            # Check if it's still processing
            if '<FlexQueryResponse' in resp.text or '<FlexStatementResponse' in resp.text:
                root = ET.fromstring(resp.text)
                status = root.find('.//Status')
                if status is not None and status.text == "Warn":
                    # Still processing
                    continue

            # Check if it's actual data
            if resp.text.startswith('<?xml') or ',' in resp.text[:200]:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = "xml" if resp.text.startswith('<?xml') else "csv"
                filename = f"ibkr_flex_{timestamp}.{ext}"
                filepath = os.path.join(output_dir, filename)

                with open(filepath, 'w') as f:
                    f.write(resp.text)

                print(f"[IBKR] ✓ Report downloaded: {filepath}")
                return filepath

        print("[IBKR] Timed out waiting for report")
        return None


# ═══════════════════════════════════════════════════════════════════
# Plaid Integration (for Bank of America + others)
# ═══════════════════════════════════════════════════════════════════

class PlaidFetcher:
    """
    Uses Plaid API to fetch transactions from Bank of America
    (and potentially Schwab) accounts.

    Plaid Pricing (as of 2025):
    - Free tier: Limited (Sandbox only)
    - Launch plan: Pay-per-connection (~$0.30/connection/month for established)
    - Growth plan: Volume discounts

    For personal use with 2-3 accounts, expect ~$50-100/month.
    Consider if the time savings justify this vs manual CSV export.

    Setup:
    1. Sign up at https://dashboard.plaid.com
    2. Get Client ID and Secret
    3. Use Plaid Link to connect your Bank of America account
    4. Save the access_token
    """

    def __init__(self):
        from config import PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV
        self.client_id = PLAID_CLIENT_ID
        self.secret = PLAID_SECRET
        self.env = PLAID_ENV

    def fetch_transactions(
        self,
        access_token: str,
        start_date: str,
        end_date: str,
        output_dir: str = None
    ) -> Optional[str]:
        """Fetch transactions via Plaid and save as CSV."""
        try:
            import plaid
            from plaid.api import plaid_api
            from plaid.model.transactions_sync_request import TransactionsSyncRequest
        except ImportError:
            print("Install Plaid: pip install plaid-python")
            return None

        output_dir = output_dir or IMPORT_DIR
        os.makedirs(output_dir, exist_ok=True)

        configuration = plaid.Configuration(
            host=getattr(plaid.Environment, self.env.capitalize()),
            api_key={
                'clientId': self.client_id,
                'secret': self.secret,
            }
        )

        api_client = plaid.ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)

        # Use transactions/sync for incremental updates
        request = TransactionsSyncRequest(access_token=access_token)
        response = client.transactions_sync(request)

        transactions = response.added
        print(f"[Plaid] Fetched {len(transactions)} new transactions")

        if transactions:
            import csv
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(output_dir, f"plaid_bofa_{timestamp}.csv")

            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Description", "Amount", "Category", "Account"])
                for txn in transactions:
                    writer.writerow([
                        txn.date,
                        txn.name,
                        -txn.amount,  # Plaid uses positive for debits
                        ','.join(txn.category or []),
                        txn.account_id,
                    ])

            print(f"[Plaid] ✓ Saved to: {filepath}")
            return filepath

        return None


# ═══════════════════════════════════════════════════════════════════
# Schwab Developer API
# ═══════════════════════════════════════════════════════════════════

class SchwabFetcher:
    """
    Uses Schwab's new Retail Account Aggregation API.

    Setup:
    1. Register at https://developer.schwab.com
    2. Create an app and get API credentials
    3. Complete OAuth2 flow

    Note: Schwab's developer API is still relatively new (post-TD Ameritrade
    merger). Access may be limited. CSV export is the reliable fallback.
    """

    def __init__(self):
        from config import SCHWAB_API_KEY, SCHWAB_API_SECRET
        self.api_key = SCHWAB_API_KEY
        self.api_secret = SCHWAB_API_SECRET

    def fetch_transactions(self, account_hash: str, start_date: str, end_date: str):
        """
        Placeholder for Schwab API integration.
        The API is still maturing — CSV export remains the most reliable method.
        """
        print("[Schwab] API integration is in development.")
        print("[Schwab] For now, manually export CSV from:")
        print("  1. Log into schwab.com")
        print("  2. Go to Accounts > History")
        print("  3. Set date range and account")
        print("  4. Click Export (top right) > CSV")
        print("  5. Save the file to ./data/imports/")
        return None


# ═══════════════════════════════════════════════════════════════════
# Orchestrator — runs all fetchers
# ═══════════════════════════════════════════════════════════════════

def fetch_all(output_dir: str = None) -> dict:
    """
    Attempt to fetch fresh data from all automated sources.
    Returns dict of source → filepath for successfully fetched files.
    """
    output_dir = output_dir or IMPORT_DIR
    results = {}

    # IBKR (fully automated if configured)
    if IBKR_FLEX_TOKEN and IBKR_FLEX_TOKEN != "your_flex_token":
        fetcher = IBKRFlexFetcher()
        path = fetcher.fetch(output_dir)
        if path:
            results["ibkr"] = path

    # Others require manual CSV for now
    print("\n" + "=" * 60)
    print("MANUAL STEPS NEEDED:")
    print("=" * 60)
    print("""
Bank of America:
  1. Log into bankofamerica.com
  2. Go to your account > Download Transactions
  3. Select date range, format: CSV
  4. Save to: {dir}/

Charles Schwab:
  1. Log into schwab.com
  2. Go to Accounts > History
  3. Set date range, click Export > CSV
  4. Save to: {dir}/

QuickBooks (optional, for reconciliation baseline):
  1. Log into QuickBooks Online
  2. Go to Reports > Transaction Detail
  3. Set date range, export as CSV
  4. Save to: {dir}/
""".format(dir=output_dir))

    return results
