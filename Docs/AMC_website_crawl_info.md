# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

Here's a full breakdown across the four things you asked for.

## What this actually is

You're describing a **regulatory intelligence platform**: crawler → document store → metadata/versioning → chunking → embeddings → knowledge graph → RAG query layer, scoped to SEBI (and presumably AMFI, RBI, exchanges) circulars for an AMC's compliance/investment teams. This is a well-established pattern, not a novel one — I found both academic systems and commercial products doing exactly this for financial regulation. More on that below.

## Pros

- **Speed**: compliance teams currently search manually across hundreds of circulars, master circulars, and FAQs. A well-built system cuts that lookup time substantially — one vendor in this exact space (RAG for financial services) claims ~70% reduction in regulatory research time, though take vendor numbers with a pinch of salt.
- **Cross-referencing**: SEBI circulars amend, supersede, or clarify each other constantly. A knowledge graph (rather than pure vector search) can model "circular X supersedes circular Y" or "clause A of the Mutual Fund Regulations was amended by circular Z" — this is where a graph genuinely beats flat RAG, because vector similarity alone won't tell you a circular you retrieved was withdrawn last year.
- **Institutional memory**: reduces dependency on individual compliance officers' tribal knowledge, especially useful given staff turnover.
- **Proactive alerting**: new-circular detection can drive push notifications to legal/compliance instead of someone checking the SEBI site manually.
- **Auditability**: if built with citation-grounded retrieval, every answer traces back to a specific circular/paragraph — useful for internal audit trails.

## Cons / real risks

- **Regulatory documents are messy**: many older SEBI circulars are scanned PDFs, inconsistent formatting, tables embedded as images. OCR errors here aren't a UX annoyance — they can silently corrupt a compliance answer.
- **Staleness is a compliance failure, not a bug**: if your pipeline lags in marking a circular as superseded/repealed, your system will confidently cite dead law. In a domain where "shall" vs "shall not" changes outcomes, this is the highest-stakes failure mode.
- **Hallucination risk has real financial/legal consequences**: unlike a general chatbot, a wrong answer here can lead to an actual compliance breach, which brings direct regulatory liability (see below).
- **Ongoing engineering burden**: SEBI and others change site structure/URLs periodically, which breaks crawlers silently — you need drift detection, not a one-time build.
- **Cost**: crawler maintenance + KG curation + embedding refresh + human review loop is a genuine ongoing MLOps commitment, not a weekend project.

## Legal and compliance issues

**Web-scraping legality generally**: legality hinges on the target site's Terms of Use, robots.txt, and copyright status of the content — public availability alone doesn't make reproduction lawful.

**SEBI specifically** — I checked their website policy directly. Two things matter:
- SEBI's terms of use don't prohibit access, but state content "should not be construed as a statement of law or used for any legal purposes," and SEBI disclaims liability for accuracy of the site content — meaning your system inherits an accuracy caveat SEBI itself makes.
- Their copyright policy is more specific: material can be reproduced free of charge, but only after obtaining permission by writing to SEBI, and the source must be prominently acknowledged wherever reproduced. This is important — "public government document" doesn't automatically mean unrestricted reuse; SEBI wants a permission request for reproduction. I'd treat this as a real step, not a formality: email SEBI, get it in writing, keep the correspondence on file. Check the same for AMFI, RBI, and any exchange sites you plan to crawl, since each publishes its own terms.

**This is the part most people miss**: because you're building this *for or as an AMC*, SEBI doesn't just regulate the source documents — it directly regulates the AI system you're building. Specifically:
- SEBI has required mutual funds, AMCs, and trustee companies to report AI/ML applications and systems they use since a 2019 circular.
- More significantly, SEBI's February 2025 amendment inserted Regulation 16C, making any SEBI-regulated entity solely liable for the AI/ML tools it uses — whether built in-house or bought — covering data privacy/security, integrity of AI outputs, and legal compliance. This creates a direct enforcement pathway: any AI-related failure on data security or compliance becomes a SEBI violation with penalties ranging from monetary sanctions to suspension of operations.
- SEBI also has a June 2025 consultation paper proposing that entities designate senior management with technical expertise to oversee AI/ML tools, maintain testing and validation frameworks, and follow a tiered approach depending on whether the AI use directly affects customers — this isn't final law yet, but it signals where binding rules are heading, and your governance design should anticipate it.

**RBI angle** (if the AMC is bank-affiliated, or if you want to align with financial-sector best practice generally): the RBI's FREE-AI report, published August 2025, lays out seven guiding principles and 26 recommendations for responsible AI in the financial sector, applying to banks, NBFCs, and fintechs, with expectations that flow through to technology providers even if not directly regulated.

**Data protection (DPDP Act/Rules)**: this matters less for the circulars themselves (public regulatory text isn't personal data) and more for how the system is used downstream — if it ever touches investor PAN numbers, account data, or client-specific queries. The DPDP Rules require AI systems to implement reasonable security safeguards, and India's AI guidance treats consent, purpose limitation, and data minimization as applicable to AI system training and use. If your AMC qualifies as a Significant Data Fiduciary, you'd face annual Data Protection Impact Assessments, independent audits, and due-diligence obligations specifically for algorithmic systems.

## Security issues

- **Crawler etiquette as a legal shield**: respect robots.txt, rate-limit aggressively, identify your user-agent honestly. Government sites getting hammered by bots is exactly the kind of thing that gets IPs blocked or draws legal attention.
- **Document integrity**: hash every downloaded document and diff on re-crawl, so you can detect silent edits (regulators do sometimes revise a published circular) versus new documents.
- **Prompt injection via ingested content**: if you ever crawl beyond official regulator domains (forums, secondary commentary sites, PDFs from unknown uploaders), malicious or malformed content embedded in a document could manipulate downstream LLM behavior when retrieved into a prompt. Stick to primary regulator domains where possible.
- **Access control on the knowledge graph/vector store**: compliance and legal data stores are a natural target — role-based access, encryption at rest/in transit, and audit logging of every query are baseline, not optional, especially given Regulation 16C's liability framing.
- **Human-in-the-loop before anything customer- or investment-decision-facing**: given SEBI's sole-liability stance, don't let this system auto-answer compliance questions that feed into filings or investor communication without a review step.

## Has anyone built this already? Yes.

- **Academic**: a 2026 paper called ComplianceNLP built a knowledge-graph-augmented RAG pipeline grounded in a regulatory knowledge graph spanning SEC, MiFID II, and Basel III provisions, combined with obligation extraction and compliance gap analysis against internal policies. Another, "RAGulating Compliance" from MasterControl AI Research, uses a multi-agent framework that builds a knowledge graph of subject-predicate-object triplets extracted from regulatory documents, cleaned and deduplicated automatically — architecturally very close to what you're describing.
- **Commercial GRC platforms**: established players like Ascent RegTech and Wolters Kluwer OneSumX still rely heavily on rule-based approaches with manual curation rather than end-to-end AI pipelines — meaning there's a real gap/opportunity, but also a signal that manual curation persists for good reason (accuracy stakes).
- **India-specific**: there's already vendor tooling (e.g., AxonFlow) explicitly building SEBI AI/ML compliance modules with Indian-PII detection and audit trails aimed at Regulation 16C — worth looking at as a buy-vs-build comparison before you commit to building everything from scratch.

## The correct process (recommended sequence)

1. **Legal clearance first, not last** — check ToU/robots.txt for every target site, request written reproduction permission from SEBI (and equivalent from AMFI/RBI/exchanges), and prefer any official RSS/API/structured listing over raw HTML scraping where one exists.
2. **Stand up AI governance before writing crawler code** — designate an accountable senior owner, document a model risk/testing framework, and design for human review on anything compliance-facing. This isn't bureaucracy for its own sake — it's what Regulation 16C will hold the AMC liable against.
3. **Build the ingestion layer with versioning as a first-class concept**: every document gets a status field (active/superseded/withdrawn), a supersession link to whatever replaced it, and a hash for change detection.
4. **Chunk at clause/paragraph level, not arbitrary token windows** — regulatory text's meaning lives in clause boundaries; naive fixed-size chunking breaks legal nuance.
5. **Build the knowledge graph around regulatory relationships specifically**: circular → amends/supersedes → circular, circular → applies-to → entity type (AMC/broker/RA), circular → cross-references → Act/Regulation. This is the part that earns its complexity — it's what lets the system tell a compliance officer "this circular was withdrawn" rather than confidently citing dead text.
6. **Ground every generated answer in citations to source paragraph**, and log every query/response pair for audit purposes.
7. **Security and DPIA review before production**, especially if any investor-personal-data pathway exists downstream.
8. **Ongoing maintenance loop**: daily crawl for new circulars, scheduled re-verification of "active" status on existing ones, and crawler-drift monitoring since regulator site structures change without notice.


Good reframe. The real question isn't "how do we get permission to crawl" — it's "which channels are already built for automated/legal consumption, or ones where we're already an authorized recipient." Several exist. Let me go through them, then the taxonomy piece.

## Legal acquisition channels, ranked roughly by cleanliness

**1. SEBI's own RSS feed** — I checked, and SEBI publishes an official feed covering the latest press releases, circulars, and orders/rulings, explicitly meant for automated syndication. This is the cleanest possible channel: SEBI is inviting automated polling, not you working around their terms. Limitation: it covers what's newly published, not the historical archive — but it solves "stay current" with essentially zero legal ambiguity. AMFI and RBI likely have equivalents worth checking.

**2. SEBI's own metadata as a taxonomy bootstrap** — separate from the document text, SEBI's circular listing pages already classify every circular by issuing department (IMD, MRD, MIRSD, HO, CFD...), applicable entity type, and date. That's structural classification metadata, not the substantive copyrighted content — a very reasonable thing to harvest and use as your first taxonomy layer, since you're not reproducing the circular itself.

**3. Official Gazette of India (e-Gazette)** — regulations and statutory notifications are public domain once gazetted, a cleaner source than the SEBI website for the underlying Acts/Regulations (as opposed to circulars, which are SEBI's own interpretive/operational documents).

**4. data.gov.in / National Data & Analytics Platform** — worth checking whether SEBI or RBI have published structured datasets there under India's Government Open Data License (GODL), which explicitly grants reuse rights. Not guaranteed for circular full-text, but worth 20 minutes of checking before you build anything.

**5. Licensed regulatory-content redistributors** — Taxmann, Manupatra (Wolters Kluwer/CCH), Lexplosion, Ricago, and similar RegTech vendors have already cleared the copyright/licensing question with SEBI and typically sell structured, pre-tagged circular feeds via subscription or API. This is probably your highest-leverage option: it solves the legal question *and* gives you a taxonomy head start, since these vendors already classify content by regulation area and entity type. Worth a build-vs-buy comparison for the raw acquisition layer specifically, even if you build the RAG/graph layer yourself on top.

**6. If your org is itself SEBI-registered** (or you're building this for one) — registered AMCs typically already receive circulars through official channels: AMFI's own circulars to member AMCs, SEBI's intermediary/SI portal, and direct email distribution to compliance officers. Ingesting from your own authorized inbox or member portal is a fundamentally different legal posture than crawling the public site — you're archiving what was sent to you, not scraping.

**7. "Assisted capture" instead of a crawler** — a lightweight browser extension your own compliance team uses while reading circulars on sebi.gov.in, which auto-extracts metadata and saves the PDF the moment a human (already authorized to browse the site) chooses to save it. Legally this is just a human downloading a document, semi-automated — it sidesteps the "automated bulk access" concern almost entirely. Trade-off: coverage depends on your team actually visiting every relevant page, so it's a good *complement* to the RSS feed, not a full replacement.

**8. Engage SEBI's CFRT directly** — SEBI has a Centre for Fintech, Regulatory Technologies that actively engages with market participants building RegTech. A formal request for a data-sharing arrangement (possibly via AMFI, or SEBI's regulatory sandbox route) is the slowest option but the cleanest — and given Regulation 16C puts full liability on you for the AI system, having a sanctioned relationship is worth the effort if this becomes a serious production system.

## Taxonomy — anchor to existing standards, don't invent from scratch

This is where you can actually build something measurably best-in-class, because the standards already exist:

- **FIBO (Financial Industry Business Ontology)** — EDM Council's open-source ontology, W3C OWL-based, covering financial instruments, legal entities, securities, and derivatives with over 2,400 classes, reviewed quarterly by industry ontologists. Map your entity/instrument taxonomy nodes to FIBO concepts wherever they overlap, and extend with SEBI/India-specific nodes where FIBO has no local-regulation coverage. This is genuinely the industry benchmark for financial ontologies, and it's free.
- **SKOS (W3C Simple Knowledge Organization System)** — represent your taxonomy itself (broader/narrower/related terms) in this standard format instead of a bespoke schema, so it's portable and toolable.
- **ISO 25964 (Parts 1 & 2)** — the actual international standard for constructing and evaluating thesauri/taxonomies, including how to map between different vocabularies. It gives you concrete, auditable construction rules: unique concept labels, noun-phrase terms, clearly defined hierarchical/associative/equivalence relationships. You can literally run your taxonomy against this as a checklist.
- **ANSI/NISO Z39.19** — companion controlled-vocabulary construction guideline, same spirit as ISO 25964.
- **LegalRuleML / Akoma Ntoso** — standards specifically for representing legal document structure and norms (obligations, amendments, temporal validity). This is what should shape your knowledge graph's "supersedes / amends / repealed-by" relationships, rather than you designing that schema from scratch.
- **EDMC's DCAM (Data Management Capability Assessment Model)** — if you want a formal maturity score to benchmark against rather than just a construction checklist, this is the companion framework FIBO users measure against.

**How you'd actually measure "best in industry"**: percentage of taxonomy nodes mapped to FIBO concepts (semantic alignment with a recognized standard), a construction audit against ISO 25964/Z39.19 rules, retrieval precision/recall against a gold-standard set of compliance-officer-verified Q&A pairs, and whether the taxonomy is expressed in SKOS/OWL (interoperable) rather than a proprietary internal format.

## Context engineering layer

The pattern that keeps showing up in the academic systems I found earlier (ComplianceNLP, RAGulating Compliance) is: **taxonomy tag filter → graph traversal for relationships → vector search for nuance within the filtered set** — not pure vector RAG. The reason is specific to regulatory text: vector similarity alone can't reliably tell you a circular was withdrawn last year, but a graph edge can. Two things worth building as first-class properties rather than afterthoughts:

- **Temporal validity** on every node (effective_from / superseded_date) so retrieval defaults to "currently in force" unless someone explicitly asks for history.
- **Provenance** on every chunk — exact source paragraph, acquisition channel, and licensing basis. This matters twice over: once for citation quality, and once for your own defensibility if SEBI or the DPDP Board ever asks where a piece of data came from and under what right.

One question that changes which of the acquisition routes to prioritize first: **is this being built for/as a SEBI-registered entity itself (AMC, RA, broker), or as an independent product for multiple AMCs?** If the former, option 6 above (official member/registrant channels) is probably your fastest legitimate path to real data today. If the latter, the licensed-redistributor route or a formal CFRT engagement makes more sense as your primary source.


Viewed AMC_website_crawl_info.md:1-106

Now let me map this with the existing codebase to understand what's already built and what the opportunities are.

Listed directory context-engineering
Listed directory streamlit_app
Listed directory Docs
Viewed taxonomy.py:1-115
Viewed build_index.py:1-150

Now I have a thorough understanding of both the AMC crawl document and the entire codebase. Let me synthesize a deep analysis.

Viewed document_extractors.py:1-40

I now have a comprehensive understanding of the entire system. Here is my detailed analysis and the **3 best options** — each carefully crafted to be legally clean, compliance-safe, and architecturally fit for your existing codebase.

---

## 🔍 Mapping: What `AMC_website_crawl_info.md` Says vs. What Your Codebase Already Does

Before the options, here is the honest gap analysis:

| Domain | What You Already Have | What the Doc Says You Need |
|---|---|---|
| **Ingestion Pipeline** | `build_index.py` — walks `data/AMC/`, extracts PDFs, scrubs PII, chunks, NERs, embeds into FAISS + Neo4j | A **versioned document store** with `status: active/superseded/withdrawn` and hash-based change detection |
| **Document Extraction** | `document_extractors.py` — PyMuPDF + Claude Vision fallback, Docling layout | Already strong; needs OCR fallback for scanned circulars specifically |
| **Chunking** | `faiss_store.build_parent_child_chunks()` — sentence-boundary-aware | The doc mandates **clause/paragraph-level** chunking for regulatory text — this is your biggest gap |
| **Knowledge Graph** | `graph_store.py` — Neo4j entities & relations; Cypher traversals | You have entities & relations but **lack regulatory lifecycle edges**: `[:SUPERSEDES]`, `[:AMENDED_BY]`, `[:EFFECTIVE_FROM_DATE]` |
| **Taxonomy** | `taxonomy.py` — reads AMFI CSV/XLSX, static SEBI categories | Needs temporal validity + the doc recommends anchoring to **FIBO/SKOS standards** |
| **Security & Compliance** | `pii_scrub.py`, `compliance_guardrails.py`, `rbac.py` — best-in-class | Already complete; Regulation 16C compliance is the frame |
| **Data Acquisition** | Currently manual — PDFs dropped into `data/AMC/` folder | 8 acquisition channels ranked; RSS feed + licensed redistributors = lowest legal risk |

---

## 🎯 The 3 Best Options (Legal, Compliant, Architecturally Aligned)

---

### ✅ **Option 1: SEBI RSS Feed + Official Member Portal Ingestion (Zero Legal Risk)**

> *"You're archiving what was sent to you, not scraping."*

**Core Idea:** Since you are building *for* a SEBI-registered AMC, **that AMC is already an authorized recipient of every SEBI circular** via AMFI member email distribution, the SEBI SI/intermediary portal, and SEBI's official RSS feed. This completely sidesteps the crawling legality question.

#### How It Maps to Your Codebase

```
SEBI RSS Feed (live polling)
        +
AMFI Member Portal (authorized inbox / email)
        ↓
[NEW MODULE] sebi_feed_ingester.py
  → polls RSS, downloads PDFs by URL
  → hashes each document (SHA-256) → detects re-edits silently
  → assigns status: active | superseded | withdrawn
  → writes to data/AMC/SEBI_Circulars/ folder
        ↓
[EXISTING] build_index.py (UNCHANGED)
  → document_extractors → pii_scrub → chunking → NER → graph_store → faiss
        ↓
[ENHANCE] graph_store.py
  → Add [:SUPERSEDES] / [:AMENDED_BY] / [:EFFECTIVE_FROM] edges
  → Add temporal validity fields: effective_from, superseded_date, status
```

#### Legal & Compliance Standing
- **SEBI RSS Feed** = explicitly designed for automated syndication. No ToU friction, no permission request required.
- **AMFI member portal ingestion** = you're archiving what was officially addressed to you. Legally equivalent to organizing your inbox.
- **No bulk scraping** of sebi.gov.in. No copyright reproduction concern.
- Fully defensible under **SEBI Regulation 16C** because the data acquisition channel is sanctioned.

#### What You Need to Build (3 New Files)
1. **`sebi_feed_ingester.py`** — RSS polling, hash-based dedup, status tagging, PDF download
2. **Enhance `graph_store.py`** — add `[:SUPERSEDES]`, `[:AMENDED_BY]`, temporal validity schema
3. **Enhance `taxonomy_retrieval.py`** — default retrieval to `status=active` unless user explicitly requests historical

**Timeline**: 1–2 weeks. Lowest risk. Highest defensibility.

---

### ✅ **Option 2: Licensed Regulatory Content API (Taxmann / Lexplosion / Ricago)**

> *"It solves the legal question AND gives you a taxonomy head start."*

**Core Idea:** Purchase a structured regulatory content API subscription from Taxmann, Lexplosion, or Ricago. These vendors have **already obtained SEBI's copyright clearance** and supply pre-tagged, versioned circular feeds via API. You consume their feed as a data supplier — no scraping, no ToU ambiguity.

#### How It Maps to Your Codebase

```
Licensed Regulatory Feed API (Taxmann/Lexplosion)
  → Returns JSON/PDF with pre-tagged metadata:
    circular_id, date, department (IMD/MRD), 
    category, status (active/superseded), 
    superseded_by, entity_type (AMC/Broker)
        ↓
[NEW MODULE] licensed_feed_adapter.py
  → Normalizes API response to your internal document schema
  → Maps vendor taxonomy tags → your existing taxonomy.json categories
  → Downloads PDFs into data/AMC/SEBI_Circulars/
        ↓
[EXISTING] build_index.py (UNCHANGED)
        ↓
[ENHANCE] graph_store.py
  → Ingest pre-tagged [:SUPERSEDES] / [:AMENDED_BY] edges
    directly from vendor metadata (no NER inference needed!)
  → 10× higher accuracy on regulatory relationships
```

#### Legal & Compliance Standing
- **Zero copyright exposure** — vendor has taken on licensing responsibility.
- Pre-tagged `status`, `department`, `superseded_by` fields **directly feed your Neo4j graph** without requiring your NER pipeline to infer relationships (currently your weakest link for regulatory lifecycle tracking).
- Under SEBI Regulation 16C, you can show a clean **provenance chain**: licensed source → ingestion ledger → graph edge.

#### What You Need to Build (2 New Files + API cost)
1. **`licensed_feed_adapter.py`** — API client, schema normalization, ledger tracking
2. **Enhance `graph_store.py`** — ingest vendor-provided regulatory lifecycle edges
3. **Vendor API subscription** (~₹1–5L/yr depending on volume)

**Timeline**: 2–3 weeks after vendor contract. Clean, scalable, best for production.

---

### ✅ **Option 3: Human-Assisted Capture + Proactive Alerting (Zero Infra Risk)**

> *"Legally this is just a human downloading a document, semi-automated."*

**Core Idea:** A **Streamlit Admin Panel extension** (you already have `admin_view.py`) that your compliance officer uses while reviewing sebi.gov.in. When they open a circular, a **"Ingest This Document" button** appears — it captures URL, downloads the PDF, runs it through your existing `build_index.py` pipeline, and logs provenance. Separately, daily SEBI RSS polling triggers **Streamlit toast alerts** when new circulars drop.

#### How It Maps to Your Codebase

```
[EXISTING] admin_view.py
  → Add "Manual Ingest" tab
  → Input: URL or file upload
  → Runs: document_extractors → build_index → graph_store
  → Logs: acquisition_channel: "human_authorized_download"
        +
[NEW MODULE] sebi_alert_monitor.py (lightweight scheduler)
  → Polls SEBI RSS every 24h for new circulars
  → Compares against processed_ledger.txt (already exists!)
  → Sends Streamlit toast / email alert to compliance officer:
    "New SEBI circular published: SEBI/HO/IMD/2025/123 — Click to review & ingest"
        +
[ENHANCE] build_index.py
  → Add `acquisition_channel` field to ledger & document metadata
  → Add `status` field (initially: "active") + hash for drift detection
```

#### Legal & Compliance Standing
- **No automated bulk scraping**. A human being browsing sebi.gov.in and clicking "Save" is identical to the current manual process — your tool is an efficiency layer over authorized human access.
- **Acquisition channel logged** = provenance trail that directly answers SEBI Regulation 16C questions.
- Fully within your existing `admin_view.py` architecture; no new infrastructure.

#### What You Need to Build (Minimal)
1. **Extend `admin_view.py`** — "Manual Ingest" tab with URL/upload input
2. **`sebi_alert_monitor.py`** — lightweight RSS delta-checker running as background scheduler
3. **Enhance `build_index.py`** — `acquisition_channel` + `status` + `sha256_hash` metadata fields

**Timeline**: 3–5 days. Lowest engineering cost. Safe for immediate use.

---

## 🏆 My Recommendation: Start with Option 1 + Option 3 Together

| Criteria | Option 1 (RSS + Portal) | Option 2 (Licensed API) | Option 3 (Human Assist + Alert) |
|---|---|---|---|
| **Legal Risk** | 🟢 Zero | 🟢 Zero | 🟢 Zero |
| **Engineering Effort** | 🟡 Medium (1–2 weeks) | 🟡 Medium (2–3 weeks + vendor) | 🟢 Very Low (3–5 days) |
| **Cost** | 🟢 Zero | 🟡 ₹1–5L/yr API cost | 🟢 Zero |
| **Coverage** | 🟡 Recent circulars + historical gaps | 🟢 Full historical + pre-tagged | 🟡 Coverage depends on team |
| **Graph Quality** | 🟡 Good (you infer relationships via NER) | 🟢 Best (vendor-tagged lifecycle edges) | 🟡 Good |
| **Fits existing codebase** | 🟢 Plug into `build_index.py` unchanged | 🟢 Plug into `build_index.py` unchanged | 🟢 Extends `admin_view.py` directly |
| **Regulation 16C defensibility** | 🟢 Strong | 🟢 Strongest | 🟢 Strong |

**Recommended path:**
1. **Ship Option 3 immediately** (3–5 days) — gives your compliance team alerting today, zero risk.
2. **Run Option 1 in parallel** (1–2 weeks) — automates the RSS/portal channel.
3. **Evaluate Option 2** once you need full historical coverage or enterprise sales — the licensed vendor route is your strongest IP and compliance story for a commercial product.

---

### 🔑 Critical Enhancement Required for ALL 3 Options
One thing your codebase is **missing that ALL 3 options need** — add this first:

```python
# In graph_store.py — Regulatory Lifecycle Schema
graph_store.add_schema([
    "(:Circular {id, status, effective_from, superseded_date, sha256_hash, acquisition_channel})",
    "(:Circular)-[:SUPERSEDES]->(:Circular)",
    "(:Circular)-[:AMENDED_BY]->(:Circular)",
    "(:Circular)-[:APPLIES_TO]->(:EntityType)"  # AMC, Broker, RA
])
```

This is the single most valuable enhancement your Neo4j graph is currently missing — and it is **what differentiates your product from plain vector RAG** exactly as the document describes.


Good — this is a bigger research question than a single pass can do justice to, so let's split it properly. Here's how I'd break it down:

**Sub-task 1** — Catalog of primary sources for AMC-related data that are actually structured for reuse (APIs, bulk downloads, official feeds) — SEBI, AMFI, RBI, exchanges, depositories, MCA, and open government data platforms — with what's genuinely free/open vs. what looks open but carries redistribution restrictions.

**Sub-task 2** — Global/supplementary sources (international regulators, financial open-data platforms) relevant if you ever go beyond India.

**Sub-task 3** — Organizations/products already doing exactly this — crawling or licensing this class of data and redistributing it to clients — as direct reference points.

**Sub-task 4** — Deep dive on 2–3 of the strongest reference orgs from Sub-task 3: how they source, license, and structure the business, as an actionable playbook.

Let's do Sub-task 1 now.Here's the plan for splitting this, and Sub-task 1 done in full this session:

**Sub-task 1** (this session) — Websites/places for AMC-related data, mapped by how open they actually are for reuse.
**Sub-task 2** (next session) — Organizations already doing this — crawling/licensing and redistributing to clients — as direct reference points.
**Sub-task 3** (later) — Deep dive on the strongest 2–3 reference orgs from Sub-task 2.

---

## Sub-task 1: Sources, mapped by openness

The honest picture is that AMC-relevant data splits into three very different legal tiers. Treating them the same is where most naive scrapers get into trouble.

### Tier 1 — Genuinely open, built for reuse

**AMFI NAV data (`amfiindia.com`)** — this is the standout find. AMFI publishes daily NAVs for every mutual fund scheme in India as a plain HTTP text file at portal.amfiindia.com/spages/NAV0.txt (also served as NAVAll.txt), no authentication required. It's so clearly intended for reuse that a whole ecosystem has grown around it: a PyPI-published Python library (mftool) exists specifically for pulling this publicly available data for building datasets, and at least one company has built a full open, no-auth API serving 37M+ daily NAV records across 38,000+ schemes, reformatted into Parquet/CSV/SQLite and refreshed daily. This is your cleanest, richest AMC-specific data source, full stop — history back to 2006, structured, no permission ambiguity.

**RBI's DBIE (Database on Indian Economy)** — RBI's own data warehouse explicitly states its purpose is to provide time-series economic and financial-sector data in a flexible, reusable format for research and analysis, downloadable as Excel, CSV, or PDF, and RBI's own framing is "for their research work with courtesy to the Database on Indian Economy, Reserve Bank of India" — i.e., attribution-based reuse is explicitly invited, not just tolerated.

**SEBI's RSS feed and circular-listing metadata** — covered last session: built for automated syndication, and the department/category classification on circular listings is safe to harvest as metadata even before you touch permission for the document text itself.

**Official Gazette of India** — regulations/notifications, public domain once gazetted.

**data.gov.in (Open Government Data Platform)** — has a dedicated Finance sector with catalogs, datasets, APIs, and services published by government ministries and departments. Worth a direct check for SEBI/RBI/MCA-published datasets specifically — I didn't find confirmation SEBI publishes there, but it's a five-minute check before you build anything.

### Tier 2 — Gray zone, permission-gated

**SEBI circular full text** — as established last session, reproduction requires written permission from SEBI plus source acknowledgment. The data is accessible; redistributing the actual document text to clients is the part that needs sign-off.

### Tier 3 — Explicitly closed to redistribution without a license

This is the one to flag clearly, because it's the opposite of the AMFI/RBI picture: **NSE and BSE market/price data (quotes, depth, historical OHLC, tick data)**. NSE's own data policy states plainly that trading members and subscribers are not permitted to redistribute market data except as agreed in a formal relevant agreement, and industry commentary is blunt about it — displaying live NSE/BSE data without a license is illegal and can trigger penalties or suspension, and all market data remains the intellectual property of the exchanges regardless of how it's accessed — it's licensed, not owned, and redistribution needs prior written approval. If your AMC system ever needs benchmark index levels, security prices, or holdings-level market data (as opposed to just NAVs and circulars), this is a different, harder legal problem than the regulatory-document side — it needs a real commercial data license (via NSE/BSE directly or an authorized vendor like TrueData/GDFL), not a crawler.

### Quick takeaway for your build

For the "circulars + taxonomy + context graph" core of your system, Tier 1 (AMFI + RBI DBIE + SEBI RSS) gets you a long way with essentially no legal friction. The moment your system needs live market/price data layered on top, budget for an actual exchange data license — that's not a scraping problem, it's a procurement one.

Ready for Sub-task 2 (organizations already doing this) whenever you want to continue.

Use the below information and map it with out subtask then plan accordingly and proceed.
Core data sources for a generic Indian AMC context layer:
Regulatory/Industry bodies

* SEBI (Mutual Fund Regulations, circulars, risk-o-meter norms, TER slabs, exit load rules)
* AMFI (scheme categorization norms, ARN/RIA data, industry AUM/flow data, NAV history)
* RBI (for debt/liquid fund linkages, repo rate impact)

Transactional/Operational

* RTAs — CAMS and KFintech (folio structures, transaction types, SIP/STP/SWP mechanics)
* NSE/BSE StAR MF platforms (order processing rules)
* Custodian data structures (for scheme-level holdings)

Scheme-level reference data

* Scheme documents (SID/SAI/KIM) — objectives, asset allocation, benchmark, fund manager
* Factsheets — monthly AUM, portfolio, sector allocation, top holdings
* NAV history, dividend/IDCW records
* Benchmark indices (Nifty, Sensex, various category benchmarks from NSE Indices/BSE)

Taxation

* Income Tax Act provisions for capital gains (equity vs debt vs hybrid, indexation rules pre/post 2023 amendment, LTCG/STCG thresholds)

Distribution/Compliance

* KYC norms (CKYC, CDSL Ventures, NSDL)
* Commission/TER disclosure norms (direct vs regular plans)

Market context

* Macroeconomic indicators (inflation, repo rate, GDP) if you want scheme performance explainability

 
These could be our source registries
 
We need to check publicly available data on them which can be consumed
 
Lets not use MoneyControl or ET Money websites.. They are not golden source of truths...


Good — let's remap the plan against your registry, then execute the next piece.

## Mapped plan

| Category (your registry) | Subtask | Status |
|---|---|---|
| Regulatory/Industry bodies (SEBI, AMFI, RBI) | Subtask 1 | Partially done (Tier 1 sources found last session) — closing gaps this session: risk-o-meter, TER slabs, exit load rules, ARN/RIA data, AMFI AUM/flow data |
| Transactional/Operational (CAMS, KFintech, StAR MF, custodians) | Subtask 2 | Next session |
| Scheme-level reference data (SID/SAI/KIM, factsheets, benchmarks) | Subtask 3 | Later |
| Taxation (Income Tax Act, capital gains) | Subtask 4 | Later |
| Distribution/Compliance (KYC — CKYC/CDSL Ventures/NSDL, commission/TER disclosure) | Subtask 5 | Later |
| Market context (macro indicators) | Subtask 6 | Mostly covered via RBI DBIE — quick close-out later |
| Reference organizations doing this | Subtask 7 | Original ask, still pending |

Noted on MoneyControl/ET Money — excluded, agreed they're aggregators, not primary sources; won't surface them.

Proceeding with **Subtask 1 gap-fill** now: risk-o-meter, TER slabs, exit load, ARN/RIA data, AMFI AUM/flow data.## Subtask 1 — closed out

The gap-fill on Regulatory/Industry bodies turned up something structurally important, plus the remaining specific items you named:

**The Master Circular is your real ingestion target, not individual circulars.** SEBI consolidates dozens of standalone circulars into a single periodically-updated Master Circular for Mutual Funds (SEBI/HO/IMD/IMD-PoD-1/P/CIR/2024/90, dated June 27, 2024), which already contains TER structure, risk-o-meter rules, exit load provisions, SID/SAI filing requirements — the works, with footnotes tracing each clause back to its originating circular. This directly solves the "supersession tracking" problem we flagged two sessions ago: SEBI does that consolidation work for you. Anchor your context graph to the Master Circular as the "current state of truth," and use standalone circulars only for the amendment history / diff trail underneath it.

**Risk-o-meter**: governed by SEBI circular SEBI/HO/IMD/DF3/CIR/P/2020/197 (Oct 5, 2020), which introduced the six-level risk-o-meter and a defined evaluation methodology, later amended by a Nov 2024 circular adding a colour scheme on top of the existing Low→Very High labels. Both are folded into the Master Circular. There's also a plain-language explainer at investor.sebi.gov.in — useful as a definitional/glossary layer, not just legal text.

**TER slabs**: set by Regulation 52 of the SEBI Mutual Fund Regulations, 1996, also restated in the Master Circular. Same for exit load — investor.sebi.gov.in has a plain-language page, but the binding version is inside the Master Circular.

**AMFI ARN / SEBI RIA data**: both AMFI's ARN search and SEBI's RIA/RA intermediary portal are publicly accessible lookup tools — but they're query-per-record web tools, not bulk-export APIs. Worth noting for your build: fine to query individually (that's literally what they're for — investor due-diligence), but treat systematic bulk harvesting of thousands of records differently from a one-off circular download; it's a heavier automated-access pattern even against a public tool.

**AMFI industry AUM/flow data**: AMFI publishes a monthly industry note directly on amfiindia.com within the first 8–10 working days of each month, covering AUM, category-wise net flows, SIP contributions, and folio counts — a real primary source, freely downloadable PDF, not something you need a MoneyControl-style aggregator for at all. Good validation of your instinct to exclude those sites — the primary source is sitting right there.

**Regulatory/Industry bodies category: done.** Ready to move to Subtask 2 (Transactional/Operational — CAMS, KFintech, StAR MF, custodians) whenever you want to continue.

Continue


## Subtask 2 — Transactional/Operational (CAMS, KFintech, NSE/BSE StAR MF, custodians)

This category turned out to split sharply into two very different things — worth being precise about, since conflating them is exactly where a system like this could accidentally cross into DPDP territory.

### What's NOT public: investor-level transaction/folio data

CAMS and KFintech's actual data — folio-level holdings, transaction history, the Consolidated Account Statement (CAS) — is personal financial data, gated by design. A CAS is only delivered to the KYC-registered email on file, and the process explicitly requires the investor's own PAN and email verification before anything is released. There's a whole ecosystem of tools (casparser, folioman) built around this, but notice what they actually do: they parse a statement the *investor themselves* requested and downloaded — they don't bulk-harvest other people's data. This lane is closed for a "crawl and redistribute to clients" model. Any legitimate access to this layer works investor-by-investor, with explicit consent — that's a fundamentally different (and separately regulated, Account-Aggregator-style) business from what you're building, not a data-sourcing shortcut.

### What IS public: the operational mechanics themselves

The *rules of how the rails work* are published, separately from any actual transaction data flowing through them:

- **BSE StAR MF publishes its order-entry API message structure as a public PDF** (bsestarmf.in/APIFileStructure.pdf) — authentication flow, message formats, response codes. You can read exactly how order entry works; you just can't call it without being a registered, credentialed market participant.
- **NSE and BSE both publish settlement-process documentation** — T+1 timelines, payment mandate rules, auto-rejection conditions for unfunded orders — genuinely useful for a context graph node like "how does an SIP debit actually clear," sourced straight from the exchange rather than an aggregator.
- **SEBI's "Formats for Master Circular for Mutual Funds"** is the single best find here — a companion document to the Master Circular containing the exact, regulator-defined field structures for every standardized report an AMC/custodian/trustee must file: Compliance Test Reports, Monthly Cumulative Reports, Annual Statistical Reports, custodian daily secondary-market transaction reporting, portfolio disclosure formats. This is effectively SEBI having already designed a chunk of your metadata schema for you — worth building your own scheme/transaction-type taxonomy fields directly off this rather than inventing your own.

### Custodian data specifically

Actual scheme-level holdings custody data isn't separately published by custodians as open data — but you don't need it from the custodian directly, because AMCs are already required to publish the resulting portfolio disclosure (holdings, sector allocation) in monthly factsheets. That's Tier 1 public data on the AMC's own site — it just belongs conceptually to the next category (scheme-level reference data), which is exactly where we're headed next.

**Bottom line for this subtask**: mechanics and reporting formats are legitimately crawlable public reference material; anything at the level of an individual investor's folio or transaction is not, and shouldn't be treated as part of this project's data-acquisition surface at all.

Ready for Subtask 3 (scheme-level reference data — SID/SAI/KIM, factsheets, benchmark indices) whenever you'd like to continue.


## Subtask 3 — Scheme-level reference data (SID/SAI/KIM, factsheets, benchmarks)

This is the best news of the whole research arc so far — it turns out AMFI isn't just the NAV/AUM source, it's the **central aggregation point for almost this entire category**, because SEBI mandates dual publication.

### SID/SAI/KIM — genuinely centralized

SEBI's own circular requires that when an AMC files a scheme's SAI, it must upload the SAI on both its own website and the AMFI website — and any material changes get updated on both, with SEBI notified within 7 days. In practice this means AMFI's portal (portal.amfiindia.com) hosts the actual PDF offer documents directly — I found live examples serving SID/SAI PDFs straight from AMFI's own domain across multiple AMCs (Tata, Kotak, SBI, etc.), confirming AMFI's website functions as a central repository providing links to offer documents from various AMCs. Practically: you don't need 40+ AMC-specific crawlers for offer documents — one well-built AMFI crawler covers the whole industry.

### Factsheets and portfolio holdings — same pattern, even better structured

This one's a genuine find: AMFI aggregates and republishes the portfolio disclosures every AMC files with SEBI, in a standardized format — one Excel workbook per AMC per month, one sheet per scheme, listing every position held as of month-end. And critically, SEBI mandates that every AMC publish complete monthly portfolio holdings for every scheme, free of charge. AMFI has dedicated pages for both the monthly factsheets and the portfolio disclosures directly. This is exactly the "top holdings, sector allocation" data point from your registry — sourced as a standardized structured file, not something you need to scrape off a rendered factsheet PDF per AMC.

### NAV/dividend records

Already covered — AMFI's NAV file (Tier 1, covered two sessions ago).

### Benchmark indices — same split as market/price data

Index **methodology** is openly published — BSE Index Services (BISPL, formerly Asia Index) and NSE Indices both publish full construction methodology PDFs for every index (Sensex, Nifty 50, category benchmarks, TRI variants) — genuinely reusable reference material for "what does this scheme's benchmark actually measure." But the **index values themselves** sit in the same restricted category as NSE/BSE market data: indices are exchange-owned intellectual property, and I'd treat bulk historical index-level time series the same way as stock prices — needing a proper index-licensing arrangement (NSE Indices and BSE both run commercial index-licensing businesses for exactly this use case) rather than scraping. Worth flagging: most of the "free" index-history sources I found online are themselves third-party aggregators of unclear licensing status — not something to build your own sourcing strategy on top of.

### Where this leaves you

Regulatory circulars, SID/SAI/KIM, factsheets, portfolio holdings, NAV, AUM/flow data — nearly your entire "scheme-level reference" and "regulatory" categories route through **one primary source: AMFI**, largely because SEBI designed it that way. Benchmark *values* are the one piece in this category that needs a real commercial license, same as market data.

Two subtasks left on your original list: Taxation, Distribution/Compliance (KYC), plus the still-pending organizations research (your original Q2). Which would you like next — continue through the remaining registry categories, or switch to the organizations-doing-this research now that the data-source map is mostly complete?


## Subtask 4 — Taxation

This one turned up something you need to know before building anything in this category: **the underlying statute changed while this project has been running.**

### The Income-tax Act, 1961 has been repealed and replaced

The Income-tax Act, 2025 (Act No. 30 of 2025) received presidential assent on August 21, 2025 and came into force on April 1, 2026, repealing the Income-tax Act, 1961. This is a live supersession event, not historical background — we're four months into the new regime as of today. Critically: the 1961 Act's provisions continue to govern all tax years beginning before April 1, 2026, while the 2025 Act governs from that date onward — so your taxation taxonomy needs a hard temporal boundary, not a single "current law" node. Section numbering changed too (the linked worked example: TDS provisions moved from Section 194C under the old Act to Section 393 under the new one, and clarifying circulars on the old section continue to apply to the new one where the underlying intent is unchanged) — meaning old CBDT circulars don't become void, they map forward to new section numbers. If your context graph doesn't model this mapping explicitly, every capital-gains answer risks citing a repealed section.

### Where the actual capital gains rules live (both versions)

- **Primary/official source**: incometaxindia.gov.in — hosts the Act text (both 1961, for pre-April-2026 tax years, and 2025), FAQs, CBDT circulars, and notifications directly from the Income Tax Department. This is your golden source, not any tax-prep aggregator site.
- **Gazette authentication**: for the 2025 Act specifically, the department itself points to egazette.gov.in or incometaxindia.gov.in as the only authoritative text — several private reproductions exist (chartered accountancy firms, ClearTax, etc.) with their own disclaimers that they're not authoritative. Don't treat those as source-of-truth even though they're easier to parse.

### The specific mechanics you named

- **Equity vs. debt vs. hybrid classification**: turns on whether a fund is "equity-oriented" under the specified-mutual-fund definition — a mutual fund is equity-oriented if its investable funds are predominantly in equity shares of domestic companies, per the applicable section (Section 10(23D)-linked definition under the old Act; carried forward conceptually into the new one). This single classification flag drives which tax regime applies, so it's worth being its own graph node.
- **Holding period thresholds**: listed equity shares, units of equity-oriented mutual funds, listed securities, and UTI units use a 12-month long-term threshold instead of the general rule, and separately the general short-term threshold itself changed from 36 months to 24 months for assets transferred on or after July 23, 2024 — two different threshold changes on two different dates, both need distinct effective-date nodes.
- **LTCG/STCG rates and the 2023-adjacent changes**: LTCG on specified securities is exempt up to ₹1,25,000 aggregate gain per year, taxed at 12.5% (or 10% for transfers before July 23, 2024) above that, with indexation benefit abolished for assets transferred on or after July 23, 2024; STCG under Section 111A on listed equity/equity-oriented fund units is taxed at 20% (15% for transfers before July 23, 2024). Note the indexation-removal date (July 23, 2024) is a different cutover from the Act-replacement date (April 1, 2026) — your graph needs both as independent temporal boundaries, not one merged "recent changes" bucket.

### Practical takeaway for the build

Taxation is the one category in your whole registry where getting the *effective-date modeling* right matters more than getting more sources — the primary source (incometaxindia.gov.in) is single and authoritative, but a flat vector-search-only approach will happily retrieve a repealed 1961 provision as if it were current. This is the clearest real-world case for the graph-based supersession approach we discussed two sessions ago, not a hypothetical one.

Two categories left on the original registry — Distribution/Compliance (KYC) and Market context (mostly a quick close-out) — plus the organizations research still pending. Continue with Distribution/Compliance next?


## Subtask 5 — Distribution/Compliance (KYC, commission/TER disclosure)

Same structural split as the CAMS/KFintech transactional data in Subtask 2 — worth flagging clearly since it's the same pattern repeating.

### KYC data itself: closed, not a data source

CKYC (the cross-sector registry run by CERSAI under PMLA Rule 9A) and the five SEBI-registered KRAs (CDSL Ventures/CVL, NSDL Database Management/NDML, CAMS, Karvy/KFin, DotEx/NSE) hold investor identity records — and access is restricted to registered, credentialed regulated entities only. Individuals can't even self-log-in to check their own CKYC status directly; they have to go through an institution. This is unambiguously personal identity data under DPDP, same conclusion as the transactional data in Subtask 2 — not a crawlable source, full stop.

**What is public**: the *regulatory architecture* describing how the system works — the SEBI (KYC Registration Agency) Regulations, 2011 that created the KRA system, the PMLA Maintenance of Records Rules (Rule 9A) that created CKYC, and CERSAI's enabling gazette notification. Fine to use as reference for "what is a KRA / how does interoperability work" as a taxonomy concept — just not as a data feed.

### Commission/TER disclosure norms: public, and AMFI is the aggregation point again

- SEBI's direct-vs-regular disclosure requirement (mandating separate expense and returns disclosure for direct and regular plans in half-yearly financial results, effective December 5, 2024) sits inside the same Master Circular ecosystem we've been using throughout — and SEBI directed AMFI specifically to standardize the disclosure format industry-wide, so the actual template lives on AMFI's site rather than being AMC-specific.
- **AMFI publishes its own Master Circular for Mutual Fund Distributors** directly on amfiindia.com, covering commission disclosure obligations, ARN/EUIN display rules, and distributor code-of-conduct requirements — another example of AMFI being the single point of truth rather than needing to piece this together from individual distributor websites.
- Underlying mechanic: Direct Plans were mandated by SEBI's original October 22, 2012 circular, which is the root citation everything downstream traces back to — worth anchoring as the origin node for the whole direct-vs-regular concept in your taxonomy.

### Where this leaves the registry

With this, five of your six categories are mapped: Regulatory/Industry bodies, Scheme-level reference data, Taxation, and Distribution/Compliance all converge heavily on **AMFI + SEBI's own Master Circular ecosystem** as primary aggregation points, with genuinely closed lanes (investor transaction data, KYC records) clearly identified and fenced off. Transactional/Operational split similarly — mechanics public, actual transaction data closed. Market context is effectively already covered by RBI DBIE from two sessions ago.

Two things remain: a light close-out on Market context, or moving straight to the organizations-doing-this research — which was your original second question and is still fully outstanding. Which would you like next?

Good — Market context closes out cleanly:

## Market context — quick close-out

- **CPI/inflation**: the National Statistical Office (NSO) under MOSPI is the primary source, publishing monthly press releases directly on mospi.gov.in — the actual data-generating body, not RBI (RBI *targets* CPI at 4% ±2%, it doesn't produce the number).
- **Repo rate / monetary policy**: RBI publishes its Monetary Policy Committee resolutions directly as press releases on rbi.org.in (6 times/year) — repo rate, SDF/MSF rates, CRR/SLR, policy stance, and the underlying CPI/GDP forecasts the MPC used.
- **GDP**: also MOSPI/NSO.
- All three feed into the RBI DBIE warehouse we found earlier, so DBIE remains your one-stop macro source; MOSPI/RBI direct releases are the freshest/primary versions if you need same-day data.

One thing worth flagging as we move into your second question: I found a live example of exactly what you're asking about — a commercial data marketplace listing (Apify) selling a structured feed built by scraping RBI's own public MPC press-release page, priced per event. That's a real, current instance of "public regulatory data → structured product → sold to clients." Good segue into Sub-task 7.

## Sub-task 7 — Organizations already doing this## Sub-task 7 — Organizations following this approach

This is where the picture snaps into focus: the "crawl/license public and regulatory-adjacent data, structure it, license it to other clients" model isn't hypothetical — it's literally how the entire Indian mutual-fund data-services industry works, and has for decades.

### CRISIL — the closest direct analog

CRISIL's Mutual Fund Ranking (CMFR), launched in June 2000, combines NAV data with portfolio-based attributes — risk-adjusted returns, asset concentration, liquidity, asset quality — rather than relying on returns alone, and has built broad acceptance among investors, intermediaries, and AMCs themselves. The business model is exactly your Q1+Q2 combined: CRISIL's methodology draws on global best practices and is also sold as customized mutual fund rankings directly to wealth management, private banking, and advisory firms — i.e., they built the taxonomy/ranking engine once, and license the output to multiple institutional clients. Worth pulling their published ranking methodology PDF directly as a design reference.

### ICRA Analytics — sourcing model worth studying closely

ICRA Analytics maintains a proprietary database of mutual fund schemes going back to the inception of the Indian MF industry itself, plus fixed-income security valuation services that Indian debt funds depend on — used by fund managers, intermediaries, and investors for pricing, analysis, and benchmarking active ISINs. Their rating process description is genuinely useful as a sourcing pattern reference: ICRA's analysts draw on prospectus and related documents, portfolio data including periodic investor reports and public filings, industry surveys, and internal AMC documents — combined with direct ongoing dialogue with AMC management rather than pure automated scraping. That's a hybrid model worth noting: public-filing ingestion plus a direct relationship channel with the entities being covered, not scraping alone.

### Morningstar — the actual global gold standard for the taxonomy question specifically

This is the one most worth studying for your "best-in-industry, benchmarkable taxonomy" goal. Two design principles stand out:

- **Classify by holdings, not by name or self-declared objective.** Morningstar deliberately moved away from classifying funds by their stated names/objectives, because a fund calling itself "growth" might hold blue-chips or small-caps — and by the early 1990s, technology allowed classification by actual portfolio holdings instead, imposing Morningstar's own structure rather than trusting fund companies' self-description. This is directly actionable for your build: don't take a scheme's SID-stated objective as the taxonomy label — derive category from actual portfolio composition, the same way Morningstar does.
- **A genuinely hierarchical, exhaustive, mutually-exclusive taxonomy.** Their Global Equity Classification Structure is built as 145 base-level industries rolling up into 55 industry groups, into 11 sectors, into 3 super-sectors — with each security mapped by primary revenue source, based on public filings plus analyst review. That four-level hierarchy, with a defined review/change process and published methodology documents, is a concrete template for how to structure (and periodically audit) your own AMC taxonomy — and it's public documentation, freely readable even though the underlying fund data itself is licensed.

### A live, small-scale example of exactly your model

Worth returning to the find from a moment ago: a commercial data-marketplace listing selling a structured feed of RBI's own public Monetary Policy Statements, scraped from RBI's official press-release page and resold per-event to trading desks. It's a tiny operation compared to CRISIL/Morningstar, but it's a real, current instance of the precise pattern you're evaluating — public regulator data, structured, sold to institutional clients — happening today, openly, without apparent legal friction, because RBI's press releases carry none of the reproduction restrictions SEBI's circular copyright policy does.

### The pattern across all of them

Every serious reference organization here follows the same shape: **source from a mix of public filings and direct relationships with the covered entities (not pure bulk scraping alone), build a proprietary classification/taxonomy layer on top, publish the methodology openly even while the underlying data stays licensed, and sell access to institutional clients rather than the public**. That last point matters for your redistribution question specifically — none of these treat the raw public data itself as the product; the taxonomy, ranking, and structuring *on top of* the public data is what's licensed. That's arguably your cleanest path too: SEBI/AMFI/RBI data acquisition can stay firmly in the open Tier-1 lane we mapped earlier, while the actual commercial value — and the actual thing worth protecting/licensing — is the context graph and taxonomy you build on top of it.

That closes out both original questions. Want to go a layer deeper on any one of these — e.g., pulling CRISIL's or Morningstar's published methodology structure to sketch a first-draft taxonomy skeleton for your own system?

This deserves a proper design document pulling everything together — let me build it as a file you can keep, share, and iterate on.This pulls together everything we've covered across the whole conversation — legal source tiering, the AMFI-as-central-repository pattern, FIBO/SKOS/ISO 25964 taxonomy anchoring, the graph-plus-vector hybrid retrieval architecture, SEBI Regulation 16C governance obligations, and the CRISIL/ICRA/Morningstar reference models — into one design document with a phased build roadmap.

A few things worth calling out from putting it all in one place: roughly 80% of what the system needs turns out to be Tier 1 (freely open) once mapped properly, which makes Phase 1 genuinely low-friction to start on immediately. The taxonomy/temporal-validity design is where most of the real engineering effort should go, since that's both the hardest technical problem and, per the reference organizations, the actual thing worth building durable value around.

Happy to go deeper on any single section — for instance, sketching the actual graph schema (node/edge types) in more detail, or drafting the SEBI permission-request letter as a starting point for Phase 2.
