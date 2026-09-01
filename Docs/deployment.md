# Deployment Guide: AMC Compliance Engineering Platform

This document outlines the step-by-step instructions for building, deploying, and maintaining the React + FastAPI architecture for the AMC Compliance Engineering Platform.

---

## 1. Environment Configuration

The application uses environment variables for endpoint configuration. Choose or create the relevant `.env` file:

- **Local Development**: `frontend/.env`
  ```env
  VITE_API_BASE=http://localhost:8000
  REACT_APP_API_BASE=http://localhost:8000
  ```
- **Staging**: `frontend/.env.staging`
  ```env
  VITE_API_BASE=https://staging-api.amc-compliance.internal
  ```
- **Production**: `frontend/.env.production`
  ```env
  VITE_API_BASE=https://api.amc-compliance.internal
  ```

---

## 2. Production Build

Run the production build command:
```bash
cd frontend
npm run build
```
This creates the optimized distribution bundle in `frontend/dist/` with:
- Code splitting for each tab and route
- ESBuild minification
- Gzipped asset sizes under 75 kB
- Source maps enabled for production error tracing

---

## 3. Deployment Targets

### Option A: Static Hosting with Proxy (Vercel / Netlify / Cloudflare Pages)
- **Vercel**: Configuration is provided in `frontend/vercel.json` with SPA routing rewrites.
- **Netlify**: Routing redirect rule is provided in `frontend/public/_redirects`.
- **Cloudflare Pages**: Configure build command `npm run build` and output directory `dist`.

### Option B: Docker + Nginx
1. Build the frontend distribution:
   ```bash
   npm run build
   ```
2. Serve with Nginx using the provided `frontend/nginx.conf` template:
   ```bash
   docker build -t amc-frontend .
   docker run -p 80:80 amc-frontend
   ```

---

## 4. Backend Deployment & CORS

Ensure the FastAPI backend allows requests from the frontend origin in `backend/app/main.py`:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 5. Automated CI/CD

GitHub Actions workflow is located at `.github/workflows/ci-cd.yml`:
- Runs Vitest unit & integration test suites
- Runs backend pytest test suites
- Builds frontend production artifact on push to `main` or `master`
