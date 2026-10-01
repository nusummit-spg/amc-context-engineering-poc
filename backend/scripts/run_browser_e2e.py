#!/usr/bin/env python
"""
run_browser_e2e.py
==================
Automated real-browser end-to-end test runner for the AMC Context Engineering Platform.
Drives real browser (Edge/Chrome) through Playwright, monitoring console logs,
network traffic, API responses, database operations, and system telemetry.
"""

import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("browser_e2e")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data.db"
APP_LOG_PATH = BASE_DIR / "logs" / "app.log"
FRONTEND_URL = "http://localhost:5173"


def get_db_stats():
    """Query current counts of all tables in data.db."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    tables = [
        row[0]
        for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if not row[0].startswith("sqlite")
    ]
    counts = {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    conn.close()
    return counts


def close_modal_safely(page):
    """Ensure any open modal is completely closed and overlay removed."""
    overlays = page.query_selector_all(".cg-modal-overlay")
    if overlays:
        logger.info("Closing open modal...")
        close_btn = page.query_selector(".cg-modal-close-btn")
        if close_btn and close_btn.is_visible():
            close_btn.click()
            page.wait_for_timeout(400)
        else:
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
    page.wait_for_selector(".cg-modal-overlay", state="hidden", timeout=5000)


def run_e2e_tests():
    report = {
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "initial_db_stats": get_db_stats(),
        "scenarios": [],
        "console_errors": [],
        "console_warnings": [],
        "failed_network_requests": [],
        "api_responses": [],
        "bugs_encountered": [],
    }

    logger.info("Initial DB Stats: %s", report["initial_db_stats"])

    with sync_playwright() as p:
        logger.info("Launching browser (Microsoft Edge)...")
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Listen to console messages
        def on_console(msg):
            text = msg.text
            if msg.type == "error":
                report["console_errors"].append({"text": text, "location": msg.location})
                logger.warning("Browser Console Error: %s", text)
            elif msg.type == "warning":
                report["console_warnings"].append({"text": text})

        page.on("console", on_console)

        # Listen to page errors (unhandled JS exceptions)
        def on_page_error(err):
            report["console_errors"].append({"text": str(err), "type": "uncaught_page_error"})
            logger.error("Uncaught Page Exception: %s", err)

        page.on("pageerror", on_page_error)

        # Listen to network requests & responses
        def on_response(resp):
            url = resp.url
            status = resp.status
            if "/api/" in url:
                report["api_responses"].append({
                    "url": url,
                    "status": status,
                    "method": resp.request.method,
                })
                if status >= 400:
                    report["failed_network_requests"].append({
                        "url": url,
                        "status": status,
                        "method": resp.request.method,
                        "status_text": resp.status_text,
                    })
                    logger.warning("API Error [%s] %s -> %d", resp.request.method, url, status)

        page.on("response", on_response)

        # -------------------------------------------------------------
        # STEP 1: Authentication Flow
        # -------------------------------------------------------------
        logger.info("Step 1: Navigating to %s for Authentication...", FRONTEND_URL)
        t0 = time.time()
        page.goto(FRONTEND_URL, wait_until="networkidle")

        scenario_auth = {"name": "Authentication Flow", "status": "PENDING", "details": {}}
        try:
            page.wait_for_selector("#login-user-id", timeout=10000)
            logger.info("Login form detected. Filling credentials...")

            page.fill("#login-user-id", "sarah_compliance")
            page.fill("#login-password", "Compliance@2026")
            page.click("button.login-submit-btn")

            # Wait for dashboard to appear
            page.wait_for_selector(".stApp", timeout=15000)
            page.wait_for_timeout(1000)

            scenario_auth["status"] = "PASSED"
            scenario_auth["latency_s"] = round(time.time() - t0, 2)
            logger.info("✓ Authentication succeeded in %.2fs!", scenario_auth["latency_s"])
        except Exception as e:
            scenario_auth["status"] = "FAILED"
            scenario_auth["error"] = str(e)
            logger.error("✗ Authentication failed: %s", e)
            report["bugs_encountered"].append({
                "component": "Authentication / LoginScreen",
                "severity": "CRITICAL",
                "description": f"Failed to authenticate user: {e}",
            })
        report["scenarios"].append(scenario_auth)

        # -------------------------------------------------------------
        # STEP 2: Real Query 1 (Borrowing limits) & Modals & Feedback
        # -------------------------------------------------------------
        q1 = "What are SEBI's borrowing limits for mutual funds?"
        scenario_q1 = {"name": "Query 1: SEBI Borrowing Limits", "query": q1, "status": "PENDING"}
        try:
            logger.info("Step 2: Submitting Query 1: '%s'...", q1)
            t0 = time.time()

            chat_input = page.wait_for_selector(".cg-chatgpt-query-input", timeout=10000)
            chat_input.fill(q1)

            send_btn = page.wait_for_selector("button.cg-chatgpt-send-btn", timeout=5000)
            send_btn.click()

            logger.info("Waiting for streaming response...")
            page.wait_for_selector(".cg-chatgpt-send-btn:not(.cg-chatgpt-send-btn--streaming)", timeout=60000)
            page.wait_for_timeout(2000)

            answers = page.query_selector_all(".cg-answer")
            if not answers:
                raise RuntimeError("No assistant answer element found in DOM!")

            latest_answer_text = answers[-1].inner_text()
            scenario_q1["latency_s"] = round(time.time() - t0, 2)
            scenario_q1["answer_preview"] = latest_answer_text[:200] + "..."
            scenario_q1["answer_length"] = len(latest_answer_text)
            logger.info("✓ Query 1 responded in %.2fs (%d chars)", scenario_q1["latency_s"], len(latest_answer_text))

            # Test Modals
            # 1. Evidence Modal
            logger.info("Testing Evidence Modal...")
            evidence_btn = page.query_selector("button:has-text('Evidence')")
            if evidence_btn:
                evidence_btn.click()
                page.wait_for_selector(".cg-modal-card", timeout=5000)
                logger.info("✓ Evidence modal displayed.")
                close_modal_safely(page)
            else:
                logger.warning("Evidence button not found on assistant message")

            # 2. Ontology Modal
            logger.info("Testing Ontology View Modal...")
            ontology_btn = page.query_selector("button:has-text('Ontology View')")
            if ontology_btn:
                ontology_btn.click()
                page.wait_for_selector(".cg-modal-card", timeout=5000)
                logger.info("✓ Ontology modal displayed.")
                close_modal_safely(page)
            else:
                logger.warning("Ontology View button not found on assistant message")

            # 3. Feedback Modal & Submission
            logger.info("Testing Feedback Modal & Submission...")
            feedback_btn = page.query_selector("button:has-text('Feedback')")
            if feedback_btn:
                feedback_btn.click()
                page.wait_for_selector(".cg-modal-card", timeout=5000)
                logger.info("Feedback modal open. Submitting rating & commentary...")

                # Type into .cg-feedback-input
                feedback_input = page.wait_for_selector(".cg-feedback-input", timeout=5000)
                feedback_input.fill("E2E Test: Highly accurate SEBI borrowing limit citation under Regulation 42(1).")
                page.wait_for_timeout(500)

                # Click Submit button
                submit_fb = page.wait_for_selector("button.cg-feedback-submit-btn:not([disabled])", timeout=5000)
                submit_fb.click()

                # Wait for success status
                page.wait_for_selector(".cg-feedback-status--success", timeout=10000)
                logger.info("✓ Feedback successfully recorded and acknowledged in UI!")

                # Close modal
                close_modal_safely(page)
                page.wait_for_timeout(500)

            scenario_q1["status"] = "PASSED"
        except Exception as e:
            scenario_q1["status"] = "FAILED"
            scenario_q1["error"] = str(e)
            logger.error("✗ Query 1 failed: %s", e)
            close_modal_safely(page)
            report["bugs_encountered"].append({
                "component": "Chat Execution / Query 1",
                "severity": "HIGH",
                "description": f"Query 1 failed: {e}",
            })
        report["scenarios"].append(scenario_q1)

        # -------------------------------------------------------------
        # STEP 3: Real Query 2 (Circular & Solution Oriented Schemes)
        # -------------------------------------------------------------
        q2 = "How does the 2026 SEBI circular change the categorization of Solution Oriented Schemes and the 'Other Schemes' section?"
        scenario_q2 = {"name": "Query 2: SEBI Circular & Solution Oriented Schemes", "query": q2, "status": "PENDING"}
        try:
            logger.info("Step 3: Submitting Query 2: '%s'...", q2)
            t0 = time.time()
            chat_input = page.wait_for_selector(".cg-chatgpt-query-input", timeout=10000)
            chat_input.fill(q2)
            send_btn = page.wait_for_selector("button.cg-chatgpt-send-btn", timeout=5000)
            send_btn.click()

            page.wait_for_selector(".cg-chatgpt-send-btn:not(.cg-chatgpt-send-btn--streaming)", timeout=60000)
            page.wait_for_timeout(2000)

            answers = page.query_selector_all(".cg-answer")
            latest_answer_text = answers[-1].inner_text()
            scenario_q2["latency_s"] = round(time.time() - t0, 2)
            scenario_q2["answer_preview"] = latest_answer_text[:200] + "..."
            scenario_q2["answer_length"] = len(latest_answer_text)
            scenario_q2["status"] = "PASSED"
            logger.info("✓ Query 2 responded in %.2fs (%d chars)", scenario_q2["latency_s"], len(latest_answer_text))
        except Exception as e:
            scenario_q2["status"] = "FAILED"
            scenario_q2["error"] = str(e)
            logger.error("✗ Query 2 failed: %s", e)
            report["bugs_encountered"].append({
                "component": "Chat Execution / Query 2",
                "severity": "HIGH",
                "description": f"Query 2 failed: {e}",
            })
        report["scenarios"].append(scenario_q2)

        # -------------------------------------------------------------
        # STEP 4: Real Query 3 (Liquid Fund Characteristics)
        # -------------------------------------------------------------
        q3 = "Can you give me the characteristics of the liquid fund"
        scenario_q3 = {"name": "Query 3: Liquid Fund Characteristics", "query": q3, "status": "PENDING"}
        try:
            logger.info("Step 4: Submitting Query 3: '%s'...", q3)
            t0 = time.time()
            chat_input = page.wait_for_selector(".cg-chatgpt-query-input", timeout=10000)
            chat_input.fill(q3)
            send_btn = page.wait_for_selector("button.cg-chatgpt-send-btn", timeout=5000)
            send_btn.click()

            page.wait_for_selector(".cg-chatgpt-send-btn:not(.cg-chatgpt-send-btn--streaming)", timeout=60000)
            page.wait_for_timeout(2000)

            answers = page.query_selector_all(".cg-answer")
            latest_answer_text = answers[-1].inner_text()
            scenario_q3["latency_s"] = round(time.time() - t0, 2)
            scenario_q3["answer_preview"] = latest_answer_text[:200] + "..."
            scenario_q3["answer_length"] = len(latest_answer_text)
            scenario_q3["status"] = "PASSED"
            logger.info("✓ Query 3 responded in %.2fs (%d chars)", scenario_q3["latency_s"], len(latest_answer_text))
        except Exception as e:
            scenario_q3["status"] = "FAILED"
            scenario_q3["error"] = str(e)
            logger.error("✗ Query 3 failed: %s", e)
            report["bugs_encountered"].append({
                "component": "Chat Execution / Query 3",
                "severity": "HIGH",
                "description": f"Query 3 failed: {e}",
            })
        report["scenarios"].append(scenario_q3)

        # -------------------------------------------------------------
        # STEP 5: Multi-Tab & Subpage Navigation
        # -------------------------------------------------------------
        logger.info("Step 5: Testing multi-tab and page navigation...")
        scenario_nav = {"name": "Tab & Page Navigation", "status": "PENDING", "tabs": {}}
        try:
            # 5.1 Compare Tab
            compare_tab_btn = page.query_selector("button.stTabs-tab:has-text('Compare'), .cg-nav-item:has-text('Compare')")
            if compare_tab_btn:
                compare_tab_btn.click()
                page.wait_for_timeout(1500)
                scenario_nav["tabs"]["compare"] = "LOADED"
                logger.info("✓ Compare tab loaded.")

            # 5.2 Analytics Tab
            analytics_tab_btn = page.query_selector("button.stTabs-tab:has-text('Analytics'), .cg-nav-item:has-text('Analytics')")
            if analytics_tab_btn:
                analytics_tab_btn.click()
                page.wait_for_timeout(1500)
                scenario_nav["tabs"]["analytics"] = "LOADED"
                logger.info("✓ Analytics tab loaded.")

            # 5.3 Admin & Governance Tab
            admin_tab_btn = page.query_selector("button.stTabs-tab:has-text('Admin & Governance'), .cg-nav-item:has-text('Admin & Governance')")
            if admin_tab_btn:
                admin_tab_btn.click()
                page.wait_for_timeout(1500)
                scenario_nav["tabs"]["admin"] = "LOADED"
                logger.info("✓ Admin tab loaded.")

                # Switch admin subtabs
                for subtab in ["Role Access Matrix", "Security & Audit Logs", "Authorized Ingest & Pipeline", "User Profile Management"]:
                    sub_btn = page.query_selector(f"button.stTabs-tab:has-text('{subtab}')")
                    if sub_btn:
                        sub_btn.click()
                        page.wait_for_timeout(800)
                        logger.info("  Subtab '%s' loaded.", subtab)

            # 5.4 Sidebar Subpages
            modules = [
                ("scorecard", "Compliance Scorecard"),
                ("violations", "Violations Explorer"),
                ("funds", "Fund Schemes Matrix"),
                ("remediation", "Remediation & SLA"),
                ("multi_region", "Multi-Jurisdiction"),
                ("governance", "Governance Review Queue"),
            ]
            for mod_key, mod_name in modules:
                side_btn = page.query_selector(f".stSidebar button:has-text('{mod_name}'), .cg-nav-item:has-text('{mod_name}')")
                if side_btn:
                    side_btn.click()
                    page.wait_for_timeout(1000)
                    scenario_nav["tabs"][mod_key] = "LOADED"
                    logger.info("  Sidebar page '%s' loaded.", mod_name)

            scenario_nav["status"] = "PASSED"
        except Exception as e:
            scenario_nav["status"] = "FAILED"
            scenario_nav["error"] = str(e)
            logger.error("✗ Navigation test failed: %s", e)
            report["bugs_encountered"].append({
                "component": "Navigation / Tabs",
                "severity": "MEDIUM",
                "description": f"Tab navigation issue: {e}",
            })
        report["scenarios"].append(scenario_nav)

        # -------------------------------------------------------------
        # STEP 6: Capture final telemetry & DB updates
        # -------------------------------------------------------------
        report["final_db_stats"] = get_db_stats()
        logger.info("Final DB Stats: %s", report["final_db_stats"])

        # Check DB growth
        db_diff = {}
        for table, final_c in report["final_db_stats"].items():
            init_c = report["initial_db_stats"].get(table, 0)
            if final_c != init_c:
                db_diff[table] = {"before": init_c, "after": final_c, "diff": final_c - init_c}
        report["db_growth"] = db_diff
        logger.info("Database Growth: %s", db_diff)

        browser.close()

    # Save detailed report
    report_file = BASE_DIR / "logs" / "e2e_browser_test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("=== E2E Browser Testing Completed! Report saved to %s ===", report_file)
    return report


if __name__ == "__main__":
    run_e2e_tests()
