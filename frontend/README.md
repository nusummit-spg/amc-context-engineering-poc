# ContextGraph — Frontend

React UI for the NuSummit ContextGraph proof of concept: taxonomy tree,
knowledge graph explorer, a 4-step query walkthrough, entity resolution,
raw corpus browser, and document upload — all wired to the FastAPI backend
in `../backend`.

If the backend (or Neo4j/Qdrant behind it) isn't reachable, every panel
falls back automatically to bundled fixture data shaped exactly like the
real API responses, so the UI is fully reviewable on its own. A badge in
the sidebar and a banner on each panel make it obvious when you're looking
at demo data versus a live answer.

## What's here

| Requirement | Where |
|---|---|
| Taxonomy tree (4-level, badges, query highlighting) | `src/components/taxonomy/` |
| Knowledge graph (all node types, labelled edges, click-to-trace) | `src/components/graph/` |
| Query walkthrough (4 steps × 2 demo queries, synced panels) | `src/components/walkthrough/` |
| API integration (`/query /taxonomy /graph /docs /ingest /status`) | `src/api/client.js` |
| Loading states + error handling (skeletons, error banners) | `src/components/common/` |
| Entity resolution (alias list → resolved node, CSS transition) | `src/components/entity/` |
| Base layout + design system (tokens, typography, palette) | `src/styles/` |
| Raw corpus panel (file list + snippet modal) | `src/components/corpus/` |
| Document upload (drag-and-drop → `/ingest/file`) | `src/components/upload/` |

Design system: warm paper background, a single clay-red accent, a serif
display face for headings paired with a plain sans body face and a
monospace utility face for data/labels — see `src/styles/tokens.css` for
every color, spacing, and type value as CSS custom properties.

## Prerequisites

- Node.js 20+ and npm 10+
- The backend running somewhere reachable (see `../backend` and the repo
  root README) — or nothing at all, since the UI runs in demo mode
  without it.

## 1. Local development

```bash
cd frontend
npm install
cp .env.example .env        # edit VITE_API_BASE_URL if your API isn't on :8000
npm run dev
```

Open http://localhost:5173. The backend's default CORS config
(`backend/app/config.py: cors_origins`) already allows this origin.

To point at a real backend:

```bash
# .env
VITE_API_BASE_URL=http://localhost:8000/api
```

Then, in another terminal, bring up the backend per its own README, e.g.:

```bash
cd ../backend
export ANTHROPIC_API_KEY=sk-ant-...
cd .. && docker compose up -d neo4j qdrant
cd backend && python -m scripts.seed_neo4j && python -m scripts.ingest_corpus
uvicorn app.main:app --reload
```

### Scripts

```bash
npm run dev        # start the Vite dev server (hot reload)
npm run build       # production build → dist/
npm run preview     # serve the production build locally, for a final check
npm run lint         # oxlint
```

## 2. Full stack with Docker Compose (recommended for a demo)

The repo's root `docker-compose.yml` now includes a `frontend` service
alongside `neo4j`, `qdrant`, `redis`, and `api`. From the repo root:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000/docs
- Neo4j browser: http://localhost:7474 (neo4j / contextgraph)
- Qdrant dashboard: http://localhost:6333/dashboard

The frontend image is built from `frontend/Dockerfile` (a static Vite
build served by nginx) with `VITE_API_BASE_URL` baked in as a build arg —
see that file's comments if you need to change it. Remember to seed the
graph and ingest the demo corpus once (see step 1 above, or
`POST /api/ingest/batch`) — an empty backend is still "live", it'll just
show empty lists instead of demo fixtures.

## 3. Deploying to AWS

Vite environment variables are compiled into the JS bundle at **build**
time, not read at runtime — so `VITE_API_BASE_URL` has to be correct
*before* you build the image or run `npm run build`, not set later as a
container environment variable.

### Option A — S3 + CloudFront (simplest, static hosting)

Good fit if the backend already has its own public HTTPS endpoint (API
Gateway, ALB, etc.) with CORS configured for your CloudFront domain.

```bash
cd frontend
echo "VITE_API_BASE_URL=https://api.your-domain.com/api" > .env.production
npm install
npm run build                     # outputs dist/

aws s3 mb s3://contextgraph-ui-your-bucket
aws s3 sync dist/ s3://contextgraph-ui-your-bucket --delete

# Create a CloudFront distribution with:
#  - Origin: the S3 bucket (use an Origin Access Control, not a public bucket)
#  - Default root object: index.html
#  - Custom error response: 403 and 404 -> /index.html, HTTP 200
#    (required for client-side routing — without this, refreshing on
#    e.g. /graph gives a CloudFront 403 instead of the app)
```

Then on the backend, add your CloudFront domain to `cors_origins` in
`backend/app/config.py` (or the `CORS_ORIGINS` env var) and redeploy the API.

### Option B — ECS Fargate (containerized, alongside a containerized backend)

Good fit if the backend is also running on ECS/Fargate or EC2 inside a VPC,
and you want the frontend served the same way, behind an ALB.

```bash
# 1. Build with the real API URL baked in
cd frontend
docker build -t contextgraph-frontend \
  --build-arg VITE_API_BASE_URL=https://api.your-domain.com/api .

# 2. Push to ECR
aws ecr create-repository --repository-name contextgraph-frontend
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker tag contextgraph-frontend:latest \
  <account-id>.dkr.ecr.<region>.amazonaws.com/contextgraph-frontend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/contextgraph-frontend:latest

# 3. Create an ECS Fargate service from that image
#    - Container port: 80
#    - Attach to an ALB target group with a health check on "/"
#    - Put it in the same VPC as the backend service (or reachable via
#      a public/internal ALB for the API)
```

If you'd rather not bake an absolute API URL into the image, build with
`--build-arg VITE_API_BASE_URL=/api`, uncomment the `location /api/ { proxy_pass ... }`
block in `frontend/nginx.conf`, and put the frontend and backend behind
the same ALB/domain with `/api/*` routed to the backend target group and
everything else routed to the frontend target group.

### Option C — Single EC2 instance (smallest footprint, matches local Docker Compose)

Run the exact same `docker-compose.yml` from the repo root on an EC2
instance with Docker installed:

```bash
# on the EC2 instance
git clone <your-repo-url> && cd amc-context-engineering-poc
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build -d
```

Open port 3000 (frontend) and 8000 (API, if you want direct API access)
in the instance's security group. Put an ALB or nginx in front with a TLS
cert if this needs to be reachable over HTTPS from outside the VPC.

### Checklist for any AWS option

- [ ] `VITE_API_BASE_URL` is set to the **public** URL of the API before building
- [ ] The backend's `cors_origins` includes the frontend's exact origin (scheme + host, no trailing slash)
- [ ] HTTPS is terminated somewhere (CloudFront, ALB, or nginx + ACM/Let's Encrypt) — mixed content will block API calls from an HTTPS frontend to an HTTP API
- [ ] SPA fallback routing is configured (CloudFront custom error response, or nginx `try_files ... /index.html`) so deep links and refreshes work
- [ ] The backend has been seeded (`scripts/seed_neo4j.py`) and has a corpus ingested, or the demo will show live-but-empty panels instead of the bundled fixtures

## Project structure

```
frontend/
  src/
    api/client.js              fetch wrappers for every backend endpoint
    hooks/useResource.js       loading/error/data state + demo-mode fallback
    data/mockData.js           fixtures mirroring the Pydantic response schemas
    styles/                    design tokens (tokens.css) + global base styles
    components/
      layout/                  Sidebar, Header, AppShell
      common/                  Skeleton loaders, error/demo banners, Modal
      overview/                landing page / architecture explainer
      taxonomy/                TaxonomyTree, TaxonomyPage
      graph/                   KnowledgeGraph (SVG), graphLayout, GraphPage
      walkthrough/              QueryWalkthrough stepper
      entity/                   EntityResolutionPanel
      corpus/                   RawCorpusPanel, DocumentModal
      upload/                   UploadPanel (drag-and-drop ingest)
  Dockerfile                    multi-stage build → nginx static serve
  nginx.conf                    SPA fallback + optional /api reverse proxy
  .env.example
```

## Troubleshooting

**Sidebar says "Demo data (backend offline)" even though the backend is running.**
Check `VITE_API_BASE_URL` in `.env` — it needs the `/api` prefix
(`http://localhost:8000/api`, not just `http://localhost:8000`). Also check
the browser console for a CORS error; if so, add your frontend's origin to
the backend's `cors_origins`.

**Upload panel shows a simulated progress bar instead of real ingest status.**
That happens automatically when `POST /ingest/file` can't be reached — same
fallback behavior as everywhere else, so the flow is still reviewable.
Once the API responds, real job IDs and polling take over.

**Blank page after `npm run build` + `nginx`/S3 deploy, but `npm run dev` works.**
Almost always missing SPA fallback routing — see the AWS checklist above.
