"""
amfi_portal_adapter.py
======================
AMFI Data Acquisition Channel — NAV data, SID/SAI/KIM documents, factsheets.
AMFI functions as a SEBI-mandated central repository (Tier 1 open access).
"""
from __future__ import annotations
import io
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

import requests
import pandas as pd
import config
import ingestion_gateway
import provenance_ledger

NAV_ALL_URL = getattr(config, "AMFI_NAV_URL", "https://portal.amfiindia.com/spages/NAVAll.txt")
MFAPI_BASE_URL = "https://api.mfapi.in/mf"


def fetch_nav_all() -> pd.DataFrame:
    """
    Fetch daily NAV dataset for all Indian mutual fund schemes from AMFI public text feed.
    Saves to data/AMFI/NAVAll.txt and computes hash to detect change.
    """
    try:
        resp = requests.get(NAV_ALL_URL, timeout=30)
        if resp.status_code != 200:
            print(f"  [AMFI Adapter] NAVAll.txt returned HTTP {resp.status_code}", flush=True)
            return pd.DataFrame()

        content_text = resp.text
        amfi_dir = config.PROJECT_ROOT / "data" / "AMFI"
        amfi_dir.mkdir(parents=True, exist_ok=True)
        nav_file = amfi_dir / "NAVAll.txt"

        current_hash = provenance_ledger.compute_file_hash(nav_file) if nav_file.exists() else ""
        new_hash = pd.util.hash_array(content_text.encode()) if hasattr(pd.util, "hash_array") else str(hash(content_text))

        with open(nav_file, "w", encoding="utf-8") as f:
            f.write(content_text)

        # Parse text file (semicolon delimited)
        lines = content_text.splitlines()
        rows = []
        current_house = "General"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            if len(parts) >= 6:
                rows.append({
                    "scheme_code": parts[0],
                    "scheme_name": parts[1],
                    "isin_div_payout": parts[2],
                    "isin_div_reinvest": parts[3],
                    "nav": parts[4],
                    "date": parts[5],
                    "fund_house": current_house
                })
            elif len(parts) == 1 and not parts[0].replace(".", "").isdigit():
                current_house = parts[0]

        df = pd.DataFrame(rows)
        print(f"  [AMFI Adapter] Ingested {len(df)} scheme NAV records from AMFI feed.", flush=True)

        req = ingestion_gateway.IngestRequest(
            filepath=nav_file,
            acquisition_channel="amfi_portal",
            source_url=NAV_ALL_URL,
            doc_type="nav_data",
            department="AMFI",
            entity_type="AMC",
            authorized_by="amfi_adapter_daemon"
        )
        ingestion_gateway.process_ingest(req)
        return df
    except Exception as exc:
        print(f"  [AMFI Adapter] Error fetching NAVAll: {exc}", flush=True)
        return pd.DataFrame()


def fetch_scheme_history(scheme_code: str) -> Dict[str, Any]:
    """Fetch NAV history for a specific scheme from public mfapi.in API."""
    url = f"{MFAPI_BASE_URL}/{scheme_code}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        print(f"  [AMFI Adapter] Error fetching scheme {scheme_code}: {exc}", flush=True)
    return {}


def fetch_sid_sai_listing() -> List[Dict[str, str]]:
    """Mock listing of central AMFI SID/SAI repository documents for AMC scheme offer documents."""
    return [
        {
            "title": "AMFI Central SID Repository — Equity Schemes",
            "url": "https://portal.amfiindia.com/sid_sai_equity.pdf",
            "doc_type": "SID",
            "department": "AMFI"
        },
        {
            "title": "AMFI Central SAI Repository — Master Statement of Additional Information",
            "url": "https://portal.amfiindia.com/sai_master.pdf",
            "doc_type": "SAI",
            "department": "AMFI"
        }
    ]
