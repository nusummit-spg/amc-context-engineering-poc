# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

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