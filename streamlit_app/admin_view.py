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

    tab1, tab2, tab3 = st.tabs(["👤 User Profile Management", "🛡️ Role Access Matrix", "📋 Security & Audit Logs"])

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
