#!/usr/bin/env python
"""Quick test of CSV ingestion."""

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vector.client import get_vector_store

async def test():
    vs = get_vector_store()
    
    # Test 1: Overview query
    print("Test 1: Overview Query")
    hits = await vs.search("What is in mutual_fund_data.csv?", top_k=3)
    print(f"  Found {len(hits)} results")
    if hits:
        print(f"  Top result: {hits[0].get('text', '')[:150]}...")
    
    # Test 2: Specific NAV query
    print("\nTest 2: NAV Query")
    hits = await vs.search("NAV of Aditya Birla Sun Life Large & Mid Cap Fund Regular Growth", top_k=5)
    print(f"  Found {len(hits)} results")
    found_nav = False
    for i, h in enumerate(hits, 1):
        text = h.get('text', '')
        if '922.67' in text:
            print(f"  [OK] Found NAV value 922.67 at rank {i} ({h.get('document_title')})")
            found_nav = True
            break
    if not found_nav:
        print(f"  [FAIL] NAV value 922.67 not found in top {len(hits)} hits")

if __name__ == "__main__":
    asyncio.run(test())
