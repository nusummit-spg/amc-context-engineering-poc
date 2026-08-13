"""
AMC Context Engineering — Admin Panel & RBAC Governance Tab
Provides User Management Table, User Creation Form, Interactive Access Matrix Inspector,
and Live System Audit Logs.
"""

import streamlit as st
import pandas as pd
from rbac import get_rbac_manager, AMCRole, ROLE_DOMAIN_ACCESS, ROLE_PERMISSIONS


def render_admin_view():
    st.markdown("## 👥 Admin Panel & Enterprise RBAC Governance")
    st.caption("Manage user profiles, assign AMC organizational roles, inspect clearance boundaries, and view audit trails.")

    manager = get_rbac_manager()

    tab1, tab2, tab3, tab4 = st.tabs([
        "👤 User Profile Management",
        "🛡️ Role Access Matrix",
        "📋 Security & Audit Logs",
        "📥 Authorized Ingest & Pipeline"
    ])

    # ── TAB 1: USER MANAGEMENT ────────────────────────────────────────────────
    with tab1:
        st.subheader("Active User Profiles")

        df = pd.DataFrame(manager.users)
        st.dataframe(df, use_container_width=True)

        st.markdown("---")
        st.subheader("➕ Create / Update User Profile")

        with st.form("create_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("Username", placeholder="e.g. j_doe_compliance")
                full_name = st.text_input("Full Name", placeholder="e.g. Jane Doe")
                email = st.text_input("Email Address", placeholder="jane.doe@amc.com")
            with col2:
                role_options = [r.value for r in AMCRole]
                selected_role = st.selectbox("Assign AMC Organizational Role", role_options)
                department = st.text_input("Department / Unit", placeholder="e.g. Legal & Compliance")

            submitted = st.form_submit_button("Save User Profile", type="primary")
            if submitted:
                if username and full_name:
                    new_user = manager.add_user(username, full_name, selected_role, department, email)
                    st.success(f"User profile '{username}' ({selected_role}) successfully created/updated!")
                    st.rerun()
                else:
                    st.error("Please fill in both Username and Full Name.")

        # Delete user option
        st.markdown("---")
        st.subheader("❌ Remove User Profile")
        del_user = st.selectbox("Select User to Remove", [u["username"] for u in manager.users if u["username"] != "sarah_compliance"])
        if st.button("Delete Selected Profile", type="secondary"):
            manager.delete_user(del_user)
            st.success(f"User profile '{del_user}' removed.")
            st.rerun()

    # ── TAB 2: ROLE ACCESS MATRIX ─────────────────────────────────────────────
    with tab2:
        st.subheader("AMC Organizational Clearance & Access Matrix")

        matrix_rows = []
        for role in AMCRole:
            domains = ", ".join(sorted(ROLE_DOMAIN_ACCESS.get(role, [])))
            perms = ROLE_PERMISSIONS.get(role, {})
            matrix_rows.append({
                "Role Name": role.value,
                "Authorized Domains": domains,
                "Admin Access": "YES" if perms.get("can_view_admin_panel") else "NO",
                "Audit Logs": "YES" if perms.get("can_view_audit_logs") else "NO",
                "Unredacted PII": "YES" if perms.get("can_view_unredacted_pii") else "NO",
                "Cypher Tool": "YES" if perms.get("can_run_cypher_tools") else "NO",
                "Compare & Analytics": "YES" if perms.get("can_access_compare_tab") else "NO",
            })

        st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True)

        st.markdown("""
        > **Security Policy**:
        > - **Level 1 (Compliance Officer)**: Complete supervisory clearance across all domains, audit logs, and unredacted PII.
        > - **Level 2 (Fund Manager)**: Full investment analytics, scheme performance, holdings, and ESG disclosures.
        > - **Level 3 (ESG Analyst)**: Dedicated ESG sustainability, BRSR, and decarbonization report scope.
        > - **Level 4 (Sales Manager)**: Customer-facing SID/KIM, NAV, and TER document scope. Masked from internal compliance notes.
        > - **Level 5 (Retail Investor)**: Public facts only. Mandatory SEBI Risk Disclaimer enforced, SEBI RIA Advice Shield active.
        """)

    # ── TAB 3: AUDIT LOGS ─────────────────────────────────────────────────────
    with tab3:
        st.subheader("System Governance & Compliance Audit Stream")
        import os
        from pathlib import Path
        log_file = Path(__file__).parent / "logs" / "query_execution_audit.jsonl"
        if os.path.exists(log_file):
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            st.caption(f"Displaying recent {min(len(lines), 30)} audit events from `{log_file.name}`:")
            st.code("\n".join(lines[-30:]), language="json")
        else:
            st.info("No query audit events recorded yet.")

    # ── TAB 4: AUTHORIZED INGEST & PIPELINE ──────────────────────────────────
    with tab4:
        st.subheader("🚀 Production Data Acquisition & Governance Controls")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("▶️ Run Production Ingestion Pipeline", type="primary", use_container_width=True):
                with st.spinner("Running RSS poll, AMFI fetch, gateway validation, and graph enrichment..."):
                    import pipeline_scheduler
                    rep = pipeline_scheduler.run_production_pipeline("incremental")
                    st.success(f"Pipeline finished in {rep.get('elapsed_seconds')}s! Downloaded: {rep.get('sebi_rss',{}).get('downloaded_count',0)} new circulars.")
                    st.json(rep)

        with c2:
            if st.button("🔍 Run Staleness Drift Detection", use_container_width=True):
                with st.spinner("Checking SHA-256 hashes and HTTP HEAD headers..."):
                    import staleness_monitor
                    rep = staleness_monitor.run_drift_check(sample_size=15)
                    st.markdown(staleness_monitor.generate_staleness_alert(rep))

        st.markdown("---")
        st.subheader("📥 Authorized Document Ingest (SEBI Reg 16C)")

        with st.form("authorized_ingest_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                ingest_url = st.text_input("Source URL (optional)", placeholder="https://sebi.gov.in/legal/circulars/...")
                uploaded_pdf = st.file_uploader("Upload PDF Document", type=["pdf", "docx", "txt"])
                doc_type = st.selectbox("Document Type", ["circular", "master_circular", "faq", "nav_data"])
            with col_b:
                department = st.selectbox("Department", ["IMD", "MRD", "MIRSD", "HO", "CFD", "GENERAL"])
                entity_type = st.selectbox("Entity Type", ["AMC", "Broker", "RA", "All"])
                authorized_by = st.text_input("Authorizing Officer", value="sarah_compliance")

            if st.form_submit_button("Ingest & Index Document", type="primary"):
                if uploaded_pdf or ingest_url:
                    import ingestion_gateway, config
                    target_dir = config.PROJECT_ROOT / "scratch" / "admin_uploads"
                    target_dir.mkdir(parents=True, exist_ok=True)

                    if uploaded_pdf:
                        temp_path = target_dir / uploaded_pdf.name
                        with open(temp_path, "wb") as f:
                            f.write(uploaded_pdf.getbuffer())
                    else:
                        import sebi_feed_ingester
                        temp_path = sebi_feed_ingester.download_circular_pdf(ingest_url, target_dir)

                    if temp_path and temp_path.exists():
                        req = ingestion_gateway.IngestRequest(
                            filepath=temp_path,
                            acquisition_channel="admin_authorized_upload" if uploaded_pdf else "admin_authorized_url",
                            source_url=ingest_url or f"upload://{temp_path.name}",
                            doc_type=doc_type,
                            department=department,
                            entity_type=entity_type,
                            authorized_by=authorized_by
                        )
                        res = ingestion_gateway.process_ingest(req)
                        if res.accepted:
                            st.success(f"Document '{temp_path.name}' accepted! SHA-256: `{res.sha256_hash[:12]}`. Indexing in background...")
                        else:
                            st.warning(f"Ingest notice: {res.reason} — file already registered in provenance ledger.")
                    else:
                        st.error("Failed to acquire document from provided URL.")
                else:
                    st.error("Please provide a Source URL or upload a file.")

        st.markdown("---")
        st.subheader("⚖️ Proposed Regulatory Supersession Edges (Review Queue)")
        import regulatory_lifecycle_enricher
        proposed_edges = regulatory_lifecycle_enricher.get_pending_proposed_edges()

        if proposed_edges:
            st.caption(f"Review {len(proposed_edges)} auto-detected regulatory supersession relationships:")
            for p in proposed_edges:
                col_info, col_act1, col_act2 = st.columns([3, 1, 1])
                col_info.markdown(f"**{p['source']}** `-[{p['rel']}]->` **{p['target']}**")
                if col_act1.button("Confirm", key=f"conf_{p['edge_id']}"):
                    regulatory_lifecycle_enricher.confirm_supersession_edge(p["edge_id"], authorized_by="sarah_compliance")
                    st.success("Edge confirmed!")
                    st.rerun()
                if col_act2.button("Reject", key=f"rej_{p['edge_id']}"):
                    regulatory_lifecycle_enricher.reject_supersession_edge(p["edge_id"])
                    st.toast("Edge rejected.")
                    st.rerun()
        else:
            st.info("No pending proposed supersession edges requiring review.")

        st.markdown("---")
        st.subheader("📄 Regulation 16C Legal Audit Report Export")
        import provenance_ledger
        report_md = provenance_ledger.generate_compliance_report()
        st.download_button(
            "Download Regulation 16C Audit Report (.md)",
            data=report_md,
            file_name="SEBI_Reg16C_Compliance_Audit_Report.md",
            mime="text/markdown"
        )
        with st.expander("Preview Compliance Report"):
            st.markdown(report_md)

