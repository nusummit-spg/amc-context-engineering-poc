# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
sebi_feed_ingester.py
=====================
Automated SEBI RSS feed poller and circular downloader.
Official syndication feed acquisition channel (zero legal ambiguity).
"""
from __future__ import annotations
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import requests
import config
import ingestion_gateway
import provenance_ledger

USER_AGENT = "AMC-ContextEngineering-RegulatoryBot/1.0 (+http://amc.internal/compliance-ai)"

SUPERSESSION_PATTERNS = [
    (re.compile(r"Amendment to (?:SEBI )?Circular (?:dated|on) (.+?) dated", re.I), "AMENDED_BY"),
    (re.compile(r"Addendum to (?:SEBI )?Circular(?: on)?(.+)", re.I), "AMENDED_BY"),
    (re.compile(r"Extension of timeline for implementation of(.*?)dated", re.I), "EXTENDS"),
    (re.compile(r"Deferment of timeline for(.*?)dated", re.I), "DEFERS"),
    (re.compile(r"Clarification(?: on| regarding)(.*?)Circular", re.I), "CLARIFIES"),
    (re.compile(r"(?:Modification|Review) of (?:framework|provisions)(.*)", re.I), "MODIFIES"),
]


@dataclass
class FeedEntry:
    circular_id: str
    title: str
    source_url: str
    published_date: str
    department: str
    entity_type: str
    doc_type: str
    pdf_url: str
    supersedes_title: Optional[str] = None


def detect_supersession(title: str) -> Optional[str]:
    for pattern, rel_type in SUPERSESSION_PATTERNS:
        match = pattern.search(title)
        if match:
            return match.group(1).strip()
    return None


def _infer_department(title: str) -> str:
    t = title.upper()
    if "IMD" in t or "MUTUAL FUND" in t:
        return "IMD"
    elif "MRD" in t or "MARKET" in t:
        return "MRD"
    elif "MIRSD" in t or "INTERMEDIARY" in t:
        return "MIRSD"
    elif "CFD" in t or "CORPORATE" in t:
        return "CFD"
    return "HO"


def poll_sebi_rss(feed_url: str = None) -> List[FeedEntry]:
    url = feed_url or getattr(config, "SEBI_RSS_URL", "https://www.sebi.gov.in/rss.html")
    entries: List[FeedEntry] = []
    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"  [SEBI RSS] HTTP {resp.status_code} from {url}", flush=True)
            return entries

        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(".//item")

        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            pdf_url = link if link.endswith(".pdf") else ""

            if title:
                dept = _infer_department(title)
                sup = detect_supersession(title)
                entries.append(FeedEntry(
                    circular_id=title[:50],
                    title=title,
                    source_url=link,
                    published_date=pub_date or datetime.now().isoformat(),
                    department=dept,
                    entity_type="AMC" if "MUTUAL" in title.upper() or "SCHEME" in title.upper() else "All",
                    doc_type="master_circular" if "MASTER CIRCULAR" in title.upper() else "circular",
                    pdf_url=pdf_url,
                    supersedes_title=sup
                ))
    except Exception as exc:
        print(f"  [SEBI RSS] Notice: RSS polling encountered: {exc}", flush=True)
    return entries


def download_circular_pdf(url: str, dest_dir: Path) -> Optional[Path]:
    if not url or not url.startswith("http"):
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1]
    if not filename.endswith(".pdf"):
        filename = f"sebi_circular_{int(time.time())}.pdf"
    dest_path = dest_dir / filename

    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        if resp.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return dest_path
    except Exception as exc:
        print(f"  [SEBI RSS] Download error for {url}: {exc}", flush=True)
    return None


def run_daily_sebi_poll() -> Dict[str, Any]:
    print("== Running SEBI RSS Daily Poll ==", flush=True)
    entries = poll_sebi_rss()
    downloaded, skipped, failed = 0, 0, 0
    tmp_dir = config.PROJECT_ROOT / "scratch" / "sebi_rss_downloads"

    for entry in entries:
        if not entry.pdf_url:
            continue
        pdf_path = download_circular_pdf(entry.pdf_url, tmp_dir)
        if not pdf_path:
            failed += 1
            continue

        req = ingestion_gateway.IngestRequest(
            filepath=pdf_path,
            acquisition_channel="sebi_rss",
            source_url=entry.source_url,
            doc_type=entry.doc_type,
            department=entry.department,
            entity_type=entry.entity_type,
            status="active",
            authorized_by="sebi_rss_daemon",
            supersedes=entry.supersedes_title
        )
        res = ingestion_gateway.process_ingest(req)
        if res.accepted:
            downloaded += 1
        else:
            skipped += 1

        time.sleep(0.5)  # Respectful rate limiting

    report = {
        "polled_count": len(entries),
        "downloaded_count": downloaded,
        "skipped_count": skipped,
        "failed_count": failed,
        "timestamp": datetime.now().isoformat()
    }
    print(f"  [SEBI RSS] Completed poll: {downloaded} new, {skipped} skipped, {failed} failed.", flush=True)
    return report
