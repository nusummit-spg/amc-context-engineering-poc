# Context Engineering Platform — Documentation Hub

Welcome to the central documentation repository for the **Context Engineering Platform** (Enterprise RAG system for Asset Management Companies).

All architectural designs, implementation specifications, regulatory compliance audits, operations runbooks, evaluation benchmarks, and UI wireframes have been organized into structured categories.

---

## 🗂️ Documentation Categories

| Category | Description | File Count |
| :--- | :--- | :--- |
| [**`01-Guides-and-Setup/`**](./01-Guides-and-Setup/) | Developer onboarding, user guides, video walkthroughs, and troubleshooting | 13 files |
| [**`02-Architecture-and-Design/`**](./02-Architecture-and-Design/) | System architecture, zero-token warm cache, Neo4j graph models, and DDL schemas | 26 files |
| [**`03-Implementation-Plans/`**](./03-Implementation-Plans/) | Feature tracks (Tracks 3–8), master engineering plans, and convergence roadmaps | 39 files |
| [**`04-Audits-and-Compliance/`**](./04-Audits-and-Compliance/) | Codebase audit reports, SEBI compliance audits, 45-pillar IP defense, and defect tracking | 38 files |
| [**`05-Operations-and-Deployment/`**](./05-Operations-and-Deployment/) | Production deployment guides, compliance runbooks, and incident response SOPs | 10 files |
| [**`06-Evaluation-and-Testing/`**](./06-Evaluation-and-Testing/) | Retrieval latency profiling, multi-turn test suites, and benchmark comparisons | 29 files |
| [**`07-Frontend-and-UI/`**](./07-Frontend-and-UI/) | React app design, design tokens, Streamlit migration diff, and wireframes | 9 files |
| [**`08-Research-and-Feedback/`**](./08-Research-and-Feedback/) | Website crawl manifests, human feedback loop designs, and meeting notes | 6 files |
| [**`09-Diagrams-and-Presentations/`**](./09-Diagrams-and-Presentations/) | Interactive HTML flowcharts, visual architecture maps, and presentation decks | 12 files |
| [**`10-Historical-and-Phases/`**](./10-Historical-and-Phases/) | Historical phase documentation (Phases 0 through 4), legacy reports, and audit archives | 28 files |

---

## 📦 Preserved Specialized Directories

The following specialized subdirectories contain project datasets, test fixtures, and standalone artifacts:

- [**`baseline/`**](./baseline/) — Query fixtures, cypher queries, and baseline evaluation reports.
- [**`feedback_finding_repair/`**](./feedback_finding_repair/) — Patch layer route specifications and batch repair HTML guides.
- [**`Keerthi/`**](./Keerthi/) — Feedback loop technical design documents and realtime scenario LLDs.
- [**`latest_test_reports/`**](./latest_test_reports/) — Query audit JSONL files, showcase results, and evaluation dashboard.
- [**`selected_source_documents/`**](./selected_source_documents/) — Source SEBI regulations, annual reports, ESG disclosures, and mutual fund CSV datasets.

---

## 🔍 Master Index of All Documents

### 01 Guides and Setup ([`01-Guides-and-Setup/`](./01-Guides-and-Setup/))

- [`00_CHIEF_ARCHITECT_START_HERE.md`](./01-Guides-and-Setup/00_CHIEF_ARCHITECT_START_HERE.md) — Executive onboarding and high-level architectural walkthrough for Chief Architects.
- [`00_START_HERE.md`](./01-Guides-and-Setup/00_START_HERE.md) — Primary onboarding document and orientation guide for developers.
- [`ANSWERS_TO_YOUR_QUESTIONS.md`](./01-Guides-and-Setup/ANSWERS_TO_YOUR_QUESTIONS.md) — FAQ and architectural Q&A addressing project design questions.
- [`api_integration.md`](./01-Guides-and-Setup/api_integration.md) — FastAPI endpoint consumption, response adapter patterns, and integration contracts.
- [`EFFICIENCY_QUICK_START.md`](./01-Guides-and-Setup/EFFICIENCY_QUICK_START.md) — Quick-start reference for executing efficiency improvements and optimizations.
- [`IMPLEMENTATION_QUICK_START.md`](./01-Guides-and-Setup/IMPLEMENTATION_QUICK_START.md) — Step-by-step developer installation and local execution guide.
- [`QUICK_START_CHECKLIST.md`](./01-Guides-and-Setup/QUICK_START_CHECKLIST.md) — 5-minute setup checklist: dependencies, environment, and verification commands.
- [`rbac_guide.md`](./01-Guides-and-Setup/rbac_guide.md) — Role-Based Access Control (RBAC) rules, role hierarchies, and permission matrix.
- [`START_HERE.md`](./01-Guides-and-Setup/START_HERE.md) — Quick orientation guide for newcomers to the project.
- [`training_guide.md`](./01-Guides-and-Setup/training_guide.md) — Onboarding curriculum and developer workflow instructions.
- [`troubleshooting.md`](./01-Guides-and-Setup/troubleshooting.md) — Common debugging steps, failure modes, and recovery procedures.
- [`user_guide.md`](./01-Guides-and-Setup/user_guide.md) — End-user instructions for executing queries, reviewing citations, and checking compliance.
- [`video_walkthrough.md`](./01-Guides-and-Setup/video_walkthrough.md) — Script, storyboard, and walkthrough notes for feature demonstrations.

### 02 Architecture and Design ([`02-Architecture-and-Design/`](./02-Architecture-and-Design/))

- [`Advanced AI Engineering Concepts.md`](./02-Architecture-and-Design/Advanced%20AI%20Engineering%20Concepts.md) — Deep architectural foundations: memory models, agentic flows, and latent graph mappings.
- [`amc_rag_context_graph_design_plan.md`](./02-Architecture-and-Design/amc_rag_context_graph_design_plan.md) — Architecture plan for AMC RAG context graph construction and entity relationship models.
- [`architecture.md`](./02-Architecture-and-Design/architecture.md) — System architecture guide: FastAPI, Neo4j, FAISS, and React integration topology.
- [`ARCHITECTURE_AND_INTEGRATION.md`](./02-Architecture-and-Design/ARCHITECTURE_AND_INTEGRATION.md) — Comprehensive system architecture, module boundaries, and service integration.
- [`autocrawling_taxonomy_design.md`](./02-Architecture-and-Design/autocrawling_taxonomy_design.md) — Architecture for automated crawling and dynamic SEBI / AMC taxonomy classification.
- [`Cache_Token_Optimization_Zero_Token_Warm_Hit_Architecture.md`](./02-Architecture-and-Design/Cache_Token_Optimization_Zero_Token_Warm_Hit_Architecture.md) — Zero-token warm cache architecture and prompt caching cost reduction.
- [`CLEANUP & ORGANIZATION PLAN.md`](./02-Architecture-and-Design/CLEANUP%20%26%20ORGANIZATION%20PLAN.md) — Structural reorganization and cleanup blueprint for project files.
- [`Configurable Resilience & Release Architecture.md`](./02-Architecture-and-Design/Configurable%20Resilience%20%26%20Release%20Architecture.md) — Circuit breakers, fallbacks, retry policies, and deployment resilience.
- [`Conversation Knowledge Graph + Full Impact Analysis.md`](./02-Architecture-and-Design/Conversation%20Knowledge%20Graph%20%2B%20Full%20Impact%20Analysis.md) — Conversation graph memory model, multi-turn entity tracking, and impact analysis.
- [`design.md`](./02-Architecture-and-Design/design.md) — Core technical specification for the Streamlit-to-React migration and backend API layer.
- [`DESIGN_IMPLEMENTATION_GAP_ANALYSIS.md`](./02-Architecture-and-Design/DESIGN_IMPLEMENTATION_GAP_ANALYSIS.md) — Detailed gap analysis between original design specifications and production code.
- [`design_vs_reality_mapping.md`](./02-Architecture-and-Design/design_vs_reality_mapping.md) — Traceability matrix comparing designed architecture specifications against actual codebase implementation.
- [`Dynamic Content-Driven Domain Architecture.md`](./02-Architecture-and-Design/Dynamic%20Content-Driven%20Domain%20Architecture.md) — Content-driven micro-domains and adaptive entity schema definitions.
- [`Enterprise Role-Based Access Control (RBAC) & AMC Admin Panel.md`](./02-Architecture-and-Design/Enterprise%20Role-Based%20Access%20Control%20%28RBAC%29%20%26%20AMC%20Admin%20Panel.md) — Admin console architecture, security boundaries, and authorization flow.
- [`Enterprise Role-Based Access Control (RBAC) & AMC Admin Panel_v1.md`](./02-Architecture-and-Design/Enterprise%20Role-Based%20Access%20Control%20%28RBAC%29%20%26%20AMC%20Admin%20Panel_v1.md) — Initial version specification of enterprise RBAC architecture.
- [`Industry-Grade Agentic AI — Deep Architecture Vision.md`](./02-Architecture-and-Design/Industry-Grade%20Agentic%20AI%20%E2%80%94%20Deep%20Architecture%20Vision.md) — Architectural vision for industrial-grade financial agentic AI.
- [`INDUSTRY_GRADE_RECOMMENDATIONS.md`](./02-Architecture-and-Design/INDUSTRY_GRADE_RECOMMENDATIONS.md) — Recommendations for hardening the system to enterprise financial industry grade.
- [`Intent-Aware System Architecture Plan.md`](./02-Architecture-and-Design/Intent-Aware%20System%20Architecture%20Plan.md) — Intent classification engine, query routing, and deterministic rule matching.
- [`OPENTELEMETRY_TRACE_ID_GUIDE.md`](./02-Architecture-and-Design/OPENTELEMETRY_TRACE_ID_GUIDE.md) — Distributed tracing standard, W3C Trace Context propagation, and Span ID conventions.
- [`PROJECT_FILES.md`](./02-Architecture-and-Design/PROJECT_FILES.md) — Master inventory, file catalog, and architectural status of all repository files.
- [`QUICK_REFERENCE_SCHEMA.md`](./02-Architecture-and-Design/QUICK_REFERENCE_SCHEMA.md) — Cheat sheet for SQLite tables, Neo4j label constraints, and relationship types.
- [`README_SCHEMA_AUDIT_DOCS.md`](./02-Architecture-and-Design/README_SCHEMA_AUDIT_DOCS.md) — Overview index for schema and audit documentation suite.
- [`RUST_INTEGRATION_KNOWLEDGE_BASE.md`](./02-Architecture-and-Design/RUST_INTEGRATION_KNOWLEDGE_BASE.md) — Knowledge base and technical guide for Rust/PyO3 integration in retrieval pipelines.
- [`SCHEMA_AND_AUDIT_STRUCTURE.md`](./02-Architecture-and-Design/SCHEMA_AND_AUDIT_STRUCTURE.md) — Storage architecture evaluation: JSON vs relational tables for audit trails.
- [`SQL_SCHEMA_IMPLEMENTATION.sql`](./02-Architecture-and-Design/SQL_SCHEMA_IMPLEMENTATION.sql) — DDL schema script for SQLite tables, foreign keys, and audit log tables.
- [`stream.md`](./02-Architecture-and-Design/stream.md) — SSE (Server-Sent Events) streaming architecture for token-by-token retrieval responses.

### 03 Implementation Plans ([`03-Implementation-Plans/`](./03-Implementation-Plans/))

- [`AMC_implementation_plan_scale_up.md`](./03-Implementation-Plans/AMC_implementation_plan_scale_up.md) — Horizontal scaling, concurrency handling, and enterprise workload support.
- [`AMC_RAG_Consolidated_Implementation_Plan.md`](./03-Implementation-Plans/AMC_RAG_Consolidated_Implementation_Plan.md) — Consolidated implementation plan uniting graph and vector retrieval.
- [`AMC_RAG_consolidated_implementation_plan_v1.md`](./03-Implementation-Plans/AMC_RAG_consolidated_implementation_plan_v1.md) — Initial draft of consolidated implementation plan (v1).
- [`AMC_RAG_consolidated_implementation_plan_v2.md`](./03-Implementation-Plans/AMC_RAG_consolidated_implementation_plan_v2.md) — Second revision of consolidated implementation plan (v2).
- [`assurance_first_next_action_plan.md`](./03-Implementation-Plans/assurance_first_next_action_plan.md) — Assurance-first delivery milestones and validation gates.
- [`convergence_implementation_plan.md`](./03-Implementation-Plans/convergence_implementation_plan.md) — Convergence roadmap for reconciling baseline and target graph schemas.
- [`DELIVERY_SUMMARY_IMPLEMENTATION_PLAN.md`](./03-Implementation-Plans/DELIVERY_SUMMARY_IMPLEMENTATION_PLAN.md) — Deliverables summary and acceptance checklist for implementation plans.
- [`DETAILED_IMPLEMENTATION_PLAN.md`](./03-Implementation-Plans/DETAILED_IMPLEMENTATION_PLAN.md) — Comprehensive engineering implementation plan across backend, graph, and UI.
- [`DETAILED_IMPLEMENTATION_PLAN_PHASE1_2.md`](./03-Implementation-Plans/DETAILED_IMPLEMENTATION_PLAN_PHASE1_2.md) — Detailed phase 1 & 2 implementation steps and milestones.
- [`EFFICIENCY_IMPROVEMENT_PLAN.md`](./03-Implementation-Plans/EFFICIENCY_IMPROVEMENT_PLAN.md) — Engineering roadmap for reducing retrieval latency and memory footprint.
- [`EFFICIENCY_PLAN_INDEX.md`](./03-Implementation-Plans/EFFICIENCY_PLAN_INDEX.md) — Index of efficiency plans, benchmarks, and optimization targets.
- [`feedback_container_implementation_spec.md`](./03-Implementation-Plans/feedback_container_implementation_spec.md) — Specification for isolated feedback containers and human-in-the-loop repair.
- [`final_master_plan.md`](./03-Implementation-Plans/final_master_plan.md) — Master release plan covering all workstreams and sign-off criteria.
- [`IMPLEMENTATION_CODE_SNIPPETS.md`](./03-Implementation-Plans/IMPLEMENTATION_CODE_SNIPPETS.md) — Reference code snippets and implementation templates for common patterns.
- [`IMPLEMENTATION_EXECUTIVE_SUMMARY.md`](./03-Implementation-Plans/IMPLEMENTATION_EXECUTIVE_SUMMARY.md) — High-level implementation status summary for leadership.
- [`implementation_plan (1).md`](./03-Implementation-Plans/implementation_plan%20%281%29.md) — Interim operational implementation steps and checkpoint tracker.
- [`IMPLEMENTATION_PLAN_INDEX.md`](./03-Implementation-Plans/IMPLEMENTATION_PLAN_INDEX.md) — Navigation index of all implementation plans and track guides.
- [`implementation_plan_tracks.md`](./03-Implementation-Plans/implementation_plan_tracks.md) — Master roadmap for independent feedback loop & correction engine (Tracks 3–8).
- [`IMPLEMENTATION_ROADMAP_COMPLETE.md`](./03-Implementation-Plans/IMPLEMENTATION_ROADMAP_COMPLETE.md) — Complete master implementation roadmap across all engineering tracks.
- [`IMPLEMENTATION_ROADMAP_WEEKS3_6.md`](./03-Implementation-Plans/IMPLEMENTATION_ROADMAP_WEEKS3_6.md) — Execution roadmap for weeks 3 to 6 covering core graph retrieval enhancements.
- [`IMPLEMENTATION_SUMMARY.md`](./03-Implementation-Plans/IMPLEMENTATION_SUMMARY.md) — Executive implementation summary of completed modules and pending tasks.
- [`Latency Reduction Implementation Plan.md`](./03-Implementation-Plans/Latency%20Reduction%20Implementation%20Plan.md) — Strategy for sub-second retrieval, vector pre-filtering, and response caching.
- [`login_screen_plan.md`](./03-Implementation-Plans/login_screen_plan.md) — Authentication and login interface design and implementation specification.
- [`Master Implementation Plan — Comprehensive Open-Source.md`](./03-Implementation-Plans/Master%20Implementation%20Plan%20%E2%80%94%20Comprehensive%20Open-Source.md) — Architecture and migration strategy using strictly open-source components.
- [`master_implementation_plan.md`](./03-Implementation-Plans/master_implementation_plan.md) — Foundational master engineering implementation plan for RAG engine.
- [`Master_Implementation_Walkthrough.md`](./03-Implementation-Plans/Master_Implementation_Walkthrough.md) — Step-by-step developer walkthrough for executing core system features.
- [`metrices_implementation_plan.md`](./03-Implementation-Plans/metrices_implementation_plan.md) — End-to-end metrics logging, query latency instrumentation, and accuracy scoring.
- [`mf-context-engine_implementation_plan.md`](./03-Implementation-Plans/mf-context-engine_implementation_plan.md) — React frontend implementation: response provenance, tooltips, and sidebar logic.
- [`NEXT_PHASE_DECISION.md`](./03-Implementation-Plans/NEXT_PHASE_DECISION.md) — Architectural decision record detailing next phase priorities and tech choices.
- [`parallel_approach.md`](./03-Implementation-Plans/parallel_approach.md) — Parallel workstream execution strategy for multi-agent development.
- [`phase_1_implementation_plan.md`](./03-Implementation-Plans/phase_1_implementation_plan.md) — Phase 1 delivery items: schema unification, core retrieval, and validation.
- [`post_convergence_action_plan.md`](./03-Implementation-Plans/post_convergence_action_plan.md) — Post-convergence hardening, cleanup, and regression mitigation checklist.
- [`production_data_pipeline_plan.md`](./03-Implementation-Plans/production_data_pipeline_plan.md) — Production ingestion pipeline: PDF extraction, chunking, and embedding.
- [`README_EFFICIENCY_PLAN.md`](./03-Implementation-Plans/README_EFFICIENCY_PLAN.md) — Overview of the efficiency improvement initiative and success metrics.
- [`rust_python_implementation_plan.md`](./03-Implementation-Plans/rust_python_implementation_plan.md) — Hybrid Rust-Python core integration plan via PyO3 for ultra-fast graph traversal.
- [`track_3_4.md`](./03-Implementation-Plans/track_3_4.md) — Detailed implementation spec for Track 3 (Feedback Capture) & Track 4 (Correction).
- [`track_4_5.md`](./03-Implementation-Plans/track_4_5.md) — Detailed implementation spec for Track 4 (Audit Log) & Track 5 (Rule Engine).
- [`track_6_7.md`](./03-Implementation-Plans/track_6_7.md) — Detailed implementation spec for Track 6 (Evaluation) & Track 7 (Admin Console).
- [`track_8.md`](./03-Implementation-Plans/track_8.md) — Detailed implementation spec for Track 8 (Production Deployment & E2E Verification).

### 04 Audits and Compliance ([`04-Audits-and-Compliance/`](./04-Audits-and-Compliance/))

- [`00_AUDIT_INDEX.md`](./04-Audits-and-Compliance/00_AUDIT_INDEX.md) — Master audit index listing all codebase and compliance audits.
- [`00_READ_ME_FIRST_AUDIT.md`](./04-Audits-and-Compliance/00_READ_ME_FIRST_AUDIT.md) — Executive summary and primary starting point for reviewing system audits.
- [`AGENTIC_SOLUTION_AUDIT.md`](./04-Audits-and-Compliance/AGENTIC_SOLUTION_AUDIT.md) — In-depth audit of the agentic workflow and decision-making logic.
- [`AMC Context Engineering — Audit Report v2.md`](./04-Audits-and-Compliance/AMC%20Context%20Engineering%20%E2%80%94%20Audit%20Report%20v2.md) — Comprehensive audit report evaluating architectural robustness and API contracts (v2).
- [`AMC Context Engineering — Full Codebase Audit Report.md`](./04-Audits-and-Compliance/AMC%20Context%20Engineering%20%E2%80%94%20Full%20Codebase%20Audit%20Report.md) — Complete codebase audit covering backend, graph store, vector store, and frontend.
- [`AMC Context Engineering — System IP & Feature Compendium.md`](./04-Audits-and-Compliance/AMC%20Context%20Engineering%20%E2%80%94%20System%20IP%20%26%20Feature%20Compendium.md) — Proprietary innovations, algorithms, and intellectual property compendium.
- [`AMC_compliance_audit_v3.md`](./04-Audits-and-Compliance/AMC_compliance_audit_v3.md) — Latest iteration (v3) of AMC / SEBI regulatory compliance audit.
- [`AMC_compliant_audit.md`](./04-Audits-and-Compliance/AMC_compliant_audit.md) — Baseline compliance audit evaluating investment advisory and disclosure rules.
- [`AMC_compliant_audit_v1.md`](./04-Audits-and-Compliance/AMC_compliant_audit_v1.md) — Verification report of compliance rules across mutual fund categories (v1).
- [`AMC_compliant_audit_v2.md`](./04-Audits-and-Compliance/AMC_compliant_audit_v2.md) — Deep audit of compliance logic, citation extraction, and regulatory checks (v2).
- [`AMC_Context_Engineering_IP_Feature_Defense_Guide.md`](./04-Audits-and-Compliance/AMC_Context_Engineering_IP_Feature_Defense_Guide.md) — Defense manual explaining IP moat, patented features, and competitive advantages.
- [`AMC_PERSPECTIVE_AUDIT.md`](./04-Audits-and-Compliance/AMC_PERSPECTIVE_AUDIT.md) — Audit from the perspective of an Asset Management Company compliance team.
- [`AUDIT_COMPLETION_SUMMARY.txt`](./04-Audits-and-Compliance/AUDIT_COMPLETION_SUMMARY.txt) — Text summary of audit completion status.
- [`AUDIT_DELIVERABLES_INDEX.md`](./04-Audits-and-Compliance/AUDIT_DELIVERABLES_INDEX.md) — Index of all audit deliverables, evidence files, and report artifacts.
- [`AUDIT_MANIFEST.md`](./04-Audits-and-Compliance/AUDIT_MANIFEST.md) — Complete manifest of audited code modules, test cases, and pass/fail states.
- [`audit_report_02_09_26.md`](./04-Audits-and-Compliance/audit_report_02_09_26.md) — Metrics and implementation audit conducted on 2026-09-02.
- [`audit_report_06_08_26.md`](./04-Audits-and-Compliance/audit_report_06_08_26.md) — Progress and defect audit conducted on 2026-08-06.
- [`audit_report_29_07_26.md`](./04-Audits-and-Compliance/audit_report_29_07_26.md) — Baseline codebase audit conducted on 2026-07-29.
- [`AUDIT_REPORT_EFFICIENCY_IMPLEMENTATION.md`](./04-Audits-and-Compliance/AUDIT_REPORT_EFFICIENCY_IMPLEMENTATION.md) — Audit evaluating efficiency implementation and performance gains.
- [`audit_report_fixed_29_07_26.md`](./04-Audits-and-Compliance/audit_report_fixed_29_07_26.md) — Verification of fixes applied following the 2026-07-29 audit.
- [`audit_report_v1_02_09_26.md`](./04-Audits-and-Compliance/audit_report_v1_02_09_26.md) — Post-audit implementation review and key findings (v1, 2026-09-02).
- [`audit_report_v2_02_09_26.md`](./04-Audits-and-Compliance/audit_report_v2_02_09_26.md) — Comprehensive implementation audit and review (v2, 2026-09-02).
- [`AUDIT_SUMMARY_ONE_PAGE.md`](./04-Audits-and-Compliance/AUDIT_SUMMARY_ONE_PAGE.md) — One-page executive summary of overall codebase audit results.
- [`CHIEF_ARCHITECT_REVIEW.md`](./04-Audits-and-Compliance/CHIEF_ARCHITECT_REVIEW.md) — Comprehensive review and architectural sign-off by the Chief Architect.
- [`CLIENT_PITCH_AMC.md`](./04-Audits-and-Compliance/CLIENT_PITCH_AMC.md) — Client pitch document outlining AMC platform value, moat, and compliance rigor.
- [`codebase_issues_analysis.md`](./04-Audits-and-Compliance/codebase_issues_analysis.md) — Root cause analysis of architectural bottlenecks, code smells, and technical debt.
- [`COMPLIANCE_CHECKLIST.md`](./04-Audits-and-Compliance/COMPLIANCE_CHECKLIST.md) — Operational checklist for verifying regulatory and security compliance.
- [`COPYRIGHT_HEADER_UPDATE.md`](./04-Audits-and-Compliance/COPYRIGHT_HEADER_UPDATE.md) — Documentation and verification of corporate copyright headers across the codebase.
- [`DELIVERABLES_MANIFEST.md`](./04-Audits-and-Compliance/DELIVERABLES_MANIFEST.md) — Manifest tracking all client and internal deliverables.
- [`DELIVERY_SUMMARY.txt`](./04-Audits-and-Compliance/DELIVERY_SUMMARY.txt) — Text summary of project delivery deliverables.
- [`detailed_audit_plan_17_08_26.md`](./04-Audits-and-Compliance/detailed_audit_plan_17_08_26.md) — Step-by-step audit verification protocol executed on 2026-08-17.
- [`Detailed_Implementation_Audit_V1.md`](./04-Audits-and-Compliance/Detailed_Implementation_Audit_V1.md) — Deep inspection of implementation artifacts against regulatory expectations (v1).
- [`EXECUTIVE_SUMMARY_CHIEF_ARCHITECT.md`](./04-Audits-and-Compliance/EXECUTIVE_SUMMARY_CHIEF_ARCHITECT.md) — Executive summary tailored for Chief Architects and technical directors.
- [`Full Codebase Audit Defect Resolution.md`](./04-Audits-and-Compliance/Full%20Codebase%20Audit%20Defect%20Resolution.md) — Resolution matrix for architectural and operational defects discovered in audits.
- [`Re-Audit Report & Industry-Grade Roadmap.md`](./04-Audits-and-Compliance/Re-Audit%20Report%20%26%20Industry-Grade%20Roadmap.md) — Follow-up re-audit verifying fixes and outlining enterprise readiness roadmap.
- [`Resolution of 59 Audit Defects.md`](./04-Audits-and-Compliance/Resolution%20of%2059%20Audit%20Defects.md) — Itemized tracking and resolution documentation for 59 key audit findings.
- [`Round 4 Audit + Extended IP Defense Guide (45 Pillars).md`](./04-Audits-and-Compliance/Round%204%20Audit%20%2B%20Extended%20IP%20Defense%20Guide%20%2845%20Pillars%29.md) — Round 4 audit findings paired with 45-pillar IP defensibility guide.
- [`UNICODE_ENCODING_FIX_LOG.md`](./04-Audits-and-Compliance/UNICODE_ENCODING_FIX_LOG.md) — Log of UTF-8 encoding fixes applied across source and documentation files.

### 05 Operations and Deployment ([`05-Operations-and-Deployment/`](./05-Operations-and-Deployment/))

- [`APPLOCKER_DIAGNOSIS.md`](./05-Operations-and-Deployment/APPLOCKER_DIAGNOSIS.md) — Diagnosis and resolution guide for Windows AppLocker execution constraints.
- [`COMPLIANCE_PHASE1_RUNBOOK.md`](./05-Operations-and-Deployment/COMPLIANCE_PHASE1_RUNBOOK.md) — SOP for executing Phase 1 compliance checks and audits.
- [`deployment.md`](./05-Operations-and-Deployment/deployment.md) — General deployment guide covering prerequisites and environment setup.
- [`DEPLOYMENT_GUIDE.md`](./05-Operations-and-Deployment/DEPLOYMENT_GUIDE.md) — Production and staging deployment guide for containers and infrastructure.
- [`INCIDENT_RESPONSE_RUNBOOK.md`](./05-Operations-and-Deployment/INCIDENT_RESPONSE_RUNBOOK.md) — Triage matrix, severity definitions, escalation protocols, and recovery steps.
- [`IT_APPLOCKER_EXEMPTION_REQUEST.md`](./05-Operations-and-Deployment/IT_APPLOCKER_EXEMPTION_REQUEST.md) — Formal IT exemption request for developer workstation tooling.
- [`OPERATOR_RUNBOOK.md`](./05-Operations-and-Deployment/OPERATOR_RUNBOOK.md) — Master operations manual: service maintenance, health checks, and runbooks.
- [`PRE_DEPLOYMENT_VERIFICATION.md`](./05-Operations-and-Deployment/PRE_DEPLOYMENT_VERIFICATION.md) — Pre-deployment verification checklist and smoke test procedures.
- [`PRODUCTION_DEPLOYMENT_GUIDE.md`](./05-Operations-and-Deployment/PRODUCTION_DEPLOYMENT_GUIDE.md) — Production release checklist and container orchestration steps.
- [`PRODUCTION_ROLLOUT.md`](./05-Operations-and-Deployment/PRODUCTION_ROLLOUT.md) — Comprehensive production rollout plan, phasing, and verification gates.

### 06 Evaluation and Testing ([`06-Evaluation-and-Testing/`](./06-Evaluation-and-Testing/))

- [`assurance_qualification_report.md`](./06-Evaluation-and-Testing/assurance_qualification_report.md) — Quality assurance evaluation verifying regulatory requirements against responses.
- [`automated_testing_valuation_plan.md`](./06-Evaluation-and-Testing/automated_testing_valuation_plan.md) — Strategy and test harness architecture for automated end-to-end valuation.
- [`BENCHMARK_SUMMARY.md`](./06-Evaluation-and-Testing/BENCHMARK_SUMMARY.md) — Summary of benchmarks comparing retrieval modes, token efficiency, and latencies.
- [`Codebase Performance & Efficiency Comparison Report.md`](./06-Evaluation-and-Testing/Codebase%20Performance%20%26%20Efficiency%20Comparison%20Report.md) — Benchmark comparison of retrieval speed, memory consumption, and index lookup efficiency.
- [`Codebase Performance & Efficiency Comparison Report_v1.md`](./06-Evaluation-and-Testing/Codebase%20Performance%20%26%20Efficiency%20Comparison%20Report_v1.md) — Baseline run of codebase performance benchmarks (v1).
- [`COMPLETE_METRICS_INDEX.md`](./06-Evaluation-and-Testing/COMPLETE_METRICS_INDEX.md) — Master index of all telemetry metrics, query counters, and evaluation scores.
- [`Comprehensive Evaluation Suite Execution.md`](./06-Evaluation-and-Testing/Comprehensive%20Evaluation%20Suite%20Execution.md) — Test harness execution guide for running multi-turn, deterministic, and citation tests.
- [`convergence_report.md`](./06-Evaluation-and-Testing/convergence_report.md) — Validation report confirming functional parity between Python and Neo4j graph stores.
- [`EVALUATION_DOCUMENTATION_INDEX.md`](./06-Evaluation-and-Testing/EVALUATION_DOCUMENTATION_INDEX.md) — Directory and guide to all evaluation documentation and datasets.
- [`evaluation_findings.md`](./06-Evaluation-and-Testing/evaluation_findings.md) — Summary of empirical evaluation results across test queries and ground-truth citations.
- [`evidence_pack.md`](./06-Evaluation-and-Testing/evidence_pack.md) — Specification for generating auditable evidence packs from query execution traces.
- [`FINAL_COMPLETION_REPORT.md`](./06-Evaluation-and-Testing/FINAL_COMPLETION_REPORT.md) — Final milestone completion report validating deliverables across all tracks.
- [`IMPLEMENTATION_VERIFICATION_REPORT.md`](./06-Evaluation-and-Testing/IMPLEMENTATION_VERIFICATION_REPORT.md) — Verification report confirming implementation against architectural acceptance criteria.
- [`independent_parity_report.md`](./06-Evaluation-and-Testing/independent_parity_report.md) — Independent verification of vector search scoring and hybrid fusion rank consistency.
- [`latency_info.md`](./06-Evaluation-and-Testing/latency_info.md) — Sub-component latency profiling: query parsing, embedding, vector search, and graph expansion.
- [`LATENCY_TOKEN_EVALUATION.md`](./06-Evaluation-and-Testing/LATENCY_TOKEN_EVALUATION.md) — Detailed evaluation of token usage and end-to-end query latency.
- [`METRICS_FLOWCHART_README.md`](./06-Evaluation-and-Testing/METRICS_FLOWCHART_README.md) — Guide to reading and interpreting metrics flowcharts.
- [`METRICS_VERIFICATION_REPORT.md`](./06-Evaluation-and-Testing/METRICS_VERIFICATION_REPORT.md) — Verification report confirming accuracy of telemetry and metrics collection.
- [`multi_turn_queries.md`](./06-Evaluation-and-Testing/multi_turn_queries.md) — Test scenarios and ground-truth expectations for multi-turn conversational retrieval.
- [`Open-Source Ecosystem Expansion Report.md`](./06-Evaluation-and-Testing/Open-Source%20Ecosystem%20Expansion%20Report.md) — Comparative performance analysis of open-source embeddings, vector indices, and LLMs.
- [`package_pros_cons_and_performance_impact.md`](./06-Evaluation-and-Testing/package_pros_cons_and_performance_impact.md) — Analysis of third-party dependencies, license compatibility, and performance overhead.
- [`PYTHON_RUST_EVALUATION_FRAMEWORK.md`](./06-Evaluation-and-Testing/PYTHON_RUST_EVALUATION_FRAMEWORK.md) — Framework for evaluating performance parity between Python and Rust graph engines.
- [`query_metrics_report.md`](./06-Evaluation-and-Testing/query_metrics_report.md) — Production telemetry metrics: p50/p95/p99 latency, token counts, and retrieval precision.
- [`README_VERIFICATION.md`](./06-Evaluation-and-Testing/README_VERIFICATION.md) — Overview of the verification harness and instructions for reproducing results.
- [`single_query_op_13_08_20_56.md`](./06-Evaluation-and-Testing/single_query_op_13_08_20_56.md) — Deep-dive trace analysis of a single complex mutual fund query execution.
- [`taxonomy_comparative_evaluation.md`](./06-Evaluation-and-Testing/taxonomy_comparative_evaluation.md) — Comparative accuracy analysis between rigid taxonomies and dynamic auto-crawled taxonomies.
- [`TEST_OUTPUT_SUMMARY.md`](./06-Evaluation-and-Testing/TEST_OUTPUT_SUMMARY.md) — Summary of automated test suite results and code coverage metrics.
- [`test_plan.md`](./06-Evaluation-and-Testing/test_plan.md) — Master integration and unit testing plan covering all backend routes and frontend components.
- [`VERIFICATION_EXECUTIVE_SUMMARY.md`](./06-Evaluation-and-Testing/VERIFICATION_EXECUTIVE_SUMMARY.md) — Executive verification summary for system performance and accuracy.

### 07 Frontend and UI ([`07-Frontend-and-UI/`](./07-Frontend-and-UI/))

- [`frontend_design.md`](./07-Frontend-and-UI/frontend_design.md) — Component architecture, state management patterns, and REST API integration layer.
- [`FRONTEND_FIX_REPORT.md`](./07-Frontend-and-UI/FRONTEND_FIX_REPORT.md) — Report documenting UI bug fixes, layout corrections, and styling improvements.
- [`requirements.md`](./07-Frontend-and-UI/requirements.md) — Functional and non-functional requirements for the Streamlit-to-React migration.
- [`streamlit_migration_diff.md`](./07-Frontend-and-UI/streamlit_migration_diff.md) — Feature-by-feature diff comparison between legacy Streamlit prototype and modern React UI.
- [`styling_guide.md`](./07-Frontend-and-UI/styling_guide.md) — Design system specifications: color tokens, typography scales, spacing, and CSS conventions.
- [`tasks.md`](./07-Frontend-and-UI/tasks.md) — Granular task checklist for frontend components, API clients, and UI polish.
- [`ui-redesign-plan.md`](./07-Frontend-and-UI/ui-redesign-plan.md) — Main application redesign roadmap: navigation, query form, results card, and governance.
- [`wireframe_prototype.html`](./07-Frontend-and-UI/wireframe_prototype.html) — Interactive HTML wireframe prototype showcasing target user interface layout.
- [`wireframe_specifications.md`](./07-Frontend-and-UI/wireframe_specifications.md) — Detailed layout specifications, grid dimensions, and responsive breakpoints.

### 08 Research and Feedback ([`08-Research-and-Feedback/`](./08-Research-and-Feedback/))

- [`AMC_Feedback_Loop_Technical_Design.md`](./08-Research-and-Feedback/AMC_Feedback_Loop_Technical_Design.md) — Technical design document for active/passive feedback mechanisms and ground-truth corrections.
- [`AMC_website_crawl_info 1.md`](./08-Research-and-Feedback/AMC_website_crawl_info%201.md) — Auxiliary crawl logs and schema definitions extracted from AMC public web pages.
- [`AMC_website_crawl_info.md`](./08-Research-and-Feedback/AMC_website_crawl_info.md) — Primary website crawling manifest, URL taxonomy, and document extraction metadata.
- [`Discussion_02_09_26.md`](./08-Research-and-Feedback/Discussion_02_09_26.md) — Engineering alignment meeting notes and architectural consensus recorded on 2026-09-02.
- [`ingestion_temp.txt`](./08-Research-and-Feedback/ingestion_temp.txt) — Raw text dump and scratchpad used during document parsing and entity extraction.
- [`REVISED_SUMMARY.md`](./08-Research-and-Feedback/REVISED_SUMMARY.md) — Revised executive summary detailing human feedback loop mechanics and gap remediations.

### 09 Diagrams and Presentations ([`09-Diagrams-and-Presentations/`](./09-Diagrams-and-Presentations/))

- [`AMC_Active_Passive_Feedback_LLD_v1.3.html`](./09-Diagrams-and-Presentations/AMC_Active_Passive_Feedback_LLD_v1.3.html) — Interactive HTML LLD diagram of active and passive feedback workflows.
- [`AMC_Context_Engineering_Benchmark_Comparison_Report.html`](./09-Diagrams-and-Presentations/AMC_Context_Engineering_Benchmark_Comparison_Report.html) — Visual benchmark comparison dashboard between vanilla RAG and Context Engineering RAG.
- [`AMC_Context_Engineering_System_IP_Showcase.html`](./09-Diagrams-and-Presentations/AMC_Context_Engineering_System_IP_Showcase.html) — Interactive presentation of system intellectual property and innovations.
- [`AMC_Context_Engineering_System_IP_Showcase_45Pillars.html`](./09-Diagrams-and-Presentations/AMC_Context_Engineering_System_IP_Showcase_45Pillars.html) — Interactive 45-pillar architectural defense showcase for stakeholders.
- [`AMC_Feedback_loop_Architecture_v1.2.html`](./09-Diagrams-and-Presentations/AMC_Feedback_loop_Architecture_v1.2.html) — High-level and low-level architecture diagram (v1.2) for automated feedback loop.
- [`AMC_Feedback_Loop_HLD_LLD.html`](./09-Diagrams-and-Presentations/AMC_Feedback_Loop_HLD_LLD.html) — Visual HLD & LLD flowcharts detailing correction patch generation.
- [`AMC_Feedback_Loop_Technical_Design_8.pdf`](./09-Diagrams-and-Presentations/AMC_Feedback_Loop_Technical_Design_8.pdf) — Technical design slide deck (revision 8) detailing system feedback mechanisms.
- [`comprehensive_query_pipeline_flowchart.html`](./09-Diagrams-and-Presentations/comprehensive_query_pipeline_flowchart.html) — Interactive flowchart showing the complete multi-layer query retrieval pipeline.
- [`multi_turn_report.html`](./09-Diagrams-and-Presentations/multi_turn_report.html) — Interactive HTML report presenting multi-turn conversation test execution results.
- [`query_pipeline_metrics_flowchart.html`](./09-Diagrams-and-Presentations/query_pipeline_metrics_flowchart.html) — Interactive flowchart tracing metrics instrumentation through the query pipeline.
- [`system_architecture_flowchart.html`](./09-Diagrams-and-Presentations/system_architecture_flowchart.html) — Interactive flowchart visualizing system architecture components and data flows.
- [`system_valuation_performance_report.html`](./09-Diagrams-and-Presentations/system_valuation_performance_report.html) — Interactive HTML performance report on system valuation and throughput.

### 10 Historical and Phases ([`10-Historical-and-Phases/`](./10-Historical-and-Phases/))

- [`PHASE_0_ANALYSIS.md`](./10-Historical-and-Phases/PHASE_0_ANALYSIS.md) — Historical Phase 0 analysis: initial codebase assessment and feasibility study.
- [`PHASE_0_AUDIT_REPORT.md`](./10-Historical-and-Phases/PHASE_0_AUDIT_REPORT.md) — Historical Phase 0 audit report on baseline system architecture.
- [`PHASE_0_AUDIT_SUMMARY.txt`](./10-Historical-and-Phases/PHASE_0_AUDIT_SUMMARY.txt) — Text summary of Phase 0 audit findings.
- [`PHASE_0_DEPLOYMENT_APPROVAL.md`](./10-Historical-and-Phases/PHASE_0_DEPLOYMENT_APPROVAL.md) — Formal approval record and sign-off for Phase 0 deployment.
- [`PHASE_0_QUICK_REFERENCE.md`](./10-Historical-and-Phases/PHASE_0_QUICK_REFERENCE.md) — Phase 0 quick reference card for architecture and setup.
- [`PHASE_0_READINESS_CHECKLIST.md`](./10-Historical-and-Phases/PHASE_0_READINESS_CHECKLIST.md) — Readiness checklist used to validate Phase 0 graduation.
- [`PHASE_2_ACTION_PLAN.md`](./10-Historical-and-Phases/PHASE_2_ACTION_PLAN.md) — Action plan and execution tasks for Phase 2 implementation.
- [`PHASE_2_ANALYSIS.md`](./10-Historical-and-Phases/PHASE_2_ANALYSIS.md) — Phase 2 architectural analysis and design decision records.
- [`PHASE_2_CONSTRAINT_UPDATE.md`](./10-Historical-and-Phases/PHASE_2_CONSTRAINT_UPDATE.md) — Updates to technical constraints and operational requirements in Phase 2.
- [`PHASE_2_EVALUATION_REPORT.md`](./10-Historical-and-Phases/PHASE_2_EVALUATION_REPORT.md) — Evaluation report assessing Phase 2 retrieval accuracy and latency.
- [`PHASE_2_QUICK_REFERENCE.txt`](./10-Historical-and-Phases/PHASE_2_QUICK_REFERENCE.txt) — Text quick reference for Phase 2 commands.
- [`PHASE_2_SUMMARY.md`](./10-Historical-and-Phases/PHASE_2_SUMMARY.md) — Executive summary of Phase 2 deliverables and outcomes.
- [`PHASE_3_FILES_AND_RECOMMENDATIONS.md`](./10-Historical-and-Phases/PHASE_3_FILES_AND_RECOMMENDATIONS.md) — Phase 3 file deliverables checklist and architectural recommendations.
- [`PHASE_3_INDEX.md`](./10-Historical-and-Phases/PHASE_3_INDEX.md) — Index of all documentation, plans, and reports produced in Phase 3.
- [`PHASE_3_PLAN.md`](./10-Historical-and-Phases/PHASE_3_PLAN.md) — Master plan for Phase 3: Graph RAG integration and taxonomy construction.
- [`PHASE_3_PROGRESS_SUMMARY.md`](./10-Historical-and-Phases/PHASE_3_PROGRESS_SUMMARY.md) — Progress tracking summary of Phase 3 implementation workstreams.
- [`PHASE_3_STATUS.txt`](./10-Historical-and-Phases/PHASE_3_STATUS.txt) — Status update text record for Phase 3.
- [`PHASE_3A_ANALYSIS.md`](./10-Historical-and-Phases/PHASE_3A_ANALYSIS.md) — Deep analysis for Phase 3A: entity extraction and schema linking.
- [`PHASE_3B_IMPLEMENTATION_SUMMARY.md`](./10-Historical-and-Phases/PHASE_3B_IMPLEMENTATION_SUMMARY.md) — Implementation summary of Phase 3B: graph store query optimization.
- [`PHASE_3D_FINAL_REPORT.md`](./10-Historical-and-Phases/PHASE_3D_FINAL_REPORT.md) — Final milestone completion report for Phase 3D.
- [`PHASE_4_DEPLOYMENT_CHECKLIST.md`](./10-Historical-and-Phases/PHASE_4_DEPLOYMENT_CHECKLIST.md) — Deployment checklist and verification criteria for Phase 4.
- [`PHASE_4_EFFICIENCY_METRICS.md`](./10-Historical-and-Phases/PHASE_4_EFFICIENCY_METRICS.md) — Telemetry metrics and benchmark scores achieved in Phase 4.
- [`PHASE_4_EFFICIENCY_SUMMARY.txt`](./10-Historical-and-Phases/PHASE_4_EFFICIENCY_SUMMARY.txt) — Efficiency summary text record for Phase 4.
- [`PHASE_4_EXECUTIVE_SUMMARY.md`](./10-Historical-and-Phases/PHASE_4_EXECUTIVE_SUMMARY.md) — Executive summary of Phase 4 deliverables, performance, and impact.
- [`PHASE_4_SUMMARY.md`](./10-Historical-and-Phases/PHASE_4_SUMMARY.md) — Comprehensive summary of Phase 4 execution and hardening.
- [`QUICK_SUMMARY.txt`](./10-Historical-and-Phases/QUICK_SUMMARY.txt) — Brief text summary of system deliverables.
- [`README_POC_PHASE_0.md`](./10-Historical-and-Phases/README_POC_PHASE_0.md) — Overview of Phase 0 proof of concept and key milestones achieved.
- [`VISUAL_SUMMARY.txt`](./10-Historical-and-Phases/VISUAL_SUMMARY.txt) — Text ASCII visual summary of architecture.
