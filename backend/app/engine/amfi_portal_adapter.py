# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
amfi_portal_adapter.py
=======================
Channel B: Fetch data from AMFI portal endpoints.
- NAVAll.txt: daily NAV data for all funds
- SID/SAI listing: scheme identification numbers
- Monthly AUM: assets under management

All data is ingested as structured CSV/text files, extracted for taxonomy,
and checked for changes using hash-based diff detection.
"""
from __future__ import annotations
import hashlib
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests

from app.engine import config
from app.engine.ingestion_gateway import (
    IngestNamespace,
    IngestRequest,
    IngestionChannel,
    compute_document_hash,
    process_ingest,
)


logger = logging.getLogger(__name__)
_AMFI_FETCH_LOG = config.LOG_DIR / "amfi_fetch_log.jsonl"


class AMFIPortalAdapter:
    """Adapter for AMFI portal endpoints."""
    
    def __init__(
        self,
        nav_url: str = config.AMFI_NAV_URL,
        sid_url: str = config.AMFI_SID_SAI_URL,
        aum_url: str = config.AMFI_MONTHLY_AUM_URL,
        timeout: int = 30
    ):
        self.nav_url = nav_url
        self.sid_url = sid_url
        self.aum_url = aum_url
        self.timeout = timeout
        self.session = requests.Session()
    
    def fetch_nav_all(self) -> Tuple[Optional[pd.DataFrame], bool]:
        """
        Fetch NAVAll.txt and parse into DataFrame.
        
        Returns:
            (dataframe, changed) where changed=True if content differs from last fetch
        """
        logger.info("[amfi] Fetching NAVAll.txt...")
        
        try:
            resp = self.session.get(self.nav_url, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error(f"[amfi] Failed to fetch NAVAll: {e}")
            return None, False
        
        # Parse: NAVAll.txt has tab-separated columns
        try:
            df = pd.read_csv(
                io.StringIO(content),
                sep="\t",
                dtype=str,
                engine="python"
            )
        except Exception as e:
            logger.error(f"[amfi] Failed to parse NAVAll: {e}")
            return None, False
        
        # Check if content changed (hash-based)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        changed = self._check_content_change("nav", content_hash)
        
        logger.info(
            f"[amfi] NAVAll fetched: {len(df)} rows, "
            f"{'NEW' if changed else 'unchanged'}"
        )
        
        return df, changed
    
    def fetch_scheme_history(self) -> Tuple[Optional[pd.DataFrame], bool]:
        """Fetch SID/SAI listing and parse into DataFrame."""
        logger.info("[amfi] Fetching SID/SAI listing...")
        
        try:
            resp = self.session.get(self.sid_url, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error(f"[amfi] Failed to fetch SID/SAI: {e}")
            return None, False
        
        try:
            df = pd.read_csv(
                io.StringIO(content),
                sep="|",
                dtype=str,
                engine="python"
            )
        except Exception as e:
            logger.error(f"[amfi] Failed to parse SID/SAI: {e}")
            return None, False
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        changed = self._check_content_change("sid_sai", content_hash)
        
        logger.info(
            f"[amfi] SID/SAI listing fetched: {len(df)} rows, "
            f"{'NEW' if changed else 'unchanged'}"
        )
        
        return df, changed
    
    def fetch_amfi_monthly_aum(self) -> Tuple[Optional[pd.DataFrame], bool]:
        """Fetch monthly AUM data."""
        logger.info("[amfi] Fetching monthly AUM...")
        
        try:
            resp = self.session.get(self.aum_url, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error(f"[amfi] Failed to fetch AUM: {e}")
            return None, False
        
        try:
            df = pd.read_csv(
                io.StringIO(content),
                sep=",",
                dtype=str,
                engine="python"
            )
        except Exception as e:
            logger.error(f"[amfi] Failed to parse AUM: {e}")
            return None, False
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        changed = self._check_content_change("aum", content_hash)
        
        logger.info(
            f"[amfi] AUM data fetched: {len(df)} rows, "
            f"{'NEW' if changed else 'unchanged'}"
        )
        
        return df, changed
    
    def _check_content_change(self, endpoint: str, content_hash: str) -> bool:
        """
        Track endpoint content hash to detect changes.
        Returns True if hash differs from previous fetch.
        """
        hash_file = config.LOG_DIR / f"amfi_{endpoint}_hash.txt"
        
        if hash_file.exists():
            prev_hash = hash_file.read_text().strip()
            if prev_hash == content_hash:
                return False
        
        hash_file.write_text(content_hash)
        return True
    
    def ingest_nav_as_document(self, df: pd.DataFrame) -> bool:
        """
        Convert NAV DataFrame to CSV and ingest as a document.
        Used to track NAV data in provenance ledger.
        
        Returns:
            True if ingestion succeeded
        """
        csv_bytes = df.to_csv(index=False).encode()
        
        # Create temp file
        temp_dir = config.LOG_DIR / "amfi_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        temp_path = temp_dir / f"nav_all_{timestamp}.csv"
        temp_path.write_bytes(csv_bytes)
        
        # Ingest through gateway
        req = IngestRequest(
            file_path=temp_path,
            source_channel=IngestionChannel.AMFI_NAV,
            namespace=IngestNamespace.AMFI_REGULATORY,
            source_url=self.nav_url,
            ingested_by="amfi_adapter",
            metadata={
                "row_count": len(df),
                "columns": list(df.columns)
            }
        )
        
        result = process_ingest(req)
        
        if result.success:
            logger.info(f"[amfi] Ingested NAV as {temp_path.name}")
        else:
            logger.info(f"[amfi] NAV ingest skipped: {result.reason}")
        
        return result.success
    
    def extract_taxonomy_delta(self, df: pd.DataFrame, endpoint: str) -> Dict[str, Any]:
        """
        Extract new fund houses/schemes from fetched data.
        Returns structured delta for Phase 6 (taxonomy extractor).
        
        Args:
            df: fetched data
            endpoint: "nav", "sid_sai", or "aum"
            
        Returns:
            dict with fund_houses, schemes, fund_managers, etc.
        """
        delta = {
            "endpoint": endpoint,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fund_houses": set(),
            "schemes": set(),
            "fund_managers": set(),
            "categories": set(),
            "benchmarks": set(),
        }
        
        if endpoint == "nav":
            # NAVAll.txt typically has columns: AMCName, SchemeName, NAV, etc.
            for col in df.columns:
                if "amc" in col.lower() or "fund" in col.lower():
                    delta["fund_houses"].update(df[col].dropna().unique())
                if "scheme" in col.lower():
                    delta["schemes"].update(df[col].dropna().unique())
                if "benchmark" in col.lower():
                    delta["benchmarks"].update(df[col].dropna().unique())
        
        elif endpoint == "sid_sai":
            # SID/SAI: Scheme ID, Scheme Name, Fund House, etc.
            for col in df.columns:
                if "scheme" in col.lower():
                    delta["schemes"].update(df[col].dropna().unique())
                if "fund" in col.lower() or "amc" in col.lower():
                    delta["fund_houses"].update(df[col].dropna().unique())
        
        # Convert sets to sorted lists
        for key in delta:
            if isinstance(delta[key], set):
                delta[key] = sorted(delta[key])
        
        return delta
    
    def run_full_fetch_cycle(self) -> Dict[str, Any]:
        """
        Run complete fetch cycle for all endpoints.
        
        Returns:
            Report with fetch results and changes detected
        """
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoints": {}
        }
        
        # NAV
        nav_df, nav_changed = self.fetch_nav_all()
        report["endpoints"]["nav"] = {
            "success": nav_df is not None,
            "changed": nav_changed,
            "row_count": len(nav_df) if nav_df is not None else 0,
        }
        if nav_df is not None and nav_changed:
            self.ingest_nav_as_document(nav_df)
            delta = self.extract_taxonomy_delta(nav_df, "nav")
            report["endpoints"]["nav"]["delta"] = delta
        
        # SID/SAI
        sid_df, sid_changed = self.fetch_scheme_history()
        report["endpoints"]["sid_sai"] = {
            "success": sid_df is not None,
            "changed": sid_changed,
            "row_count": len(sid_df) if sid_df is not None else 0,
        }
        if sid_df is not None and sid_changed:
            delta = self.extract_taxonomy_delta(sid_df, "sid_sai")
            report["endpoints"]["sid_sai"]["delta"] = delta
        
        # AUM
        aum_df, aum_changed = self.fetch_amfi_monthly_aum()
        report["endpoints"]["aum"] = {
            "success": aum_df is not None,
            "changed": aum_changed,
            "row_count": len(aum_df) if aum_df is not None else 0,
        }
        
        logger.info(f"[amfi] Fetch cycle complete: {report}")
        return report


if __name__ == "__main__":
    adapter = AMFIPortalAdapter()
    report = adapter.run_full_fetch_cycle()
    print(report)
