# Backend Setup Guide

Complete setup instructions for the AMC Context Engineering Backend on Windows and Linux platforms.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
   - [Windows Setup](#windows-setup)
   - [Linux Setup](#linux-setup)
3. [Configuration](#configuration)
4. [Database Setup](#database-setup)
5. [Running the Application](#running-the-application)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)
8. [Development Workflow](#development-workflow)
9. [Testing](#testing)

---

## Prerequisites

### Required Software

**Python Environment:**
- Python 3.10 or higher
- pip (Python package manager)
- virtualenv or venv

**Database:**
- Neo4j 5.24 or higher (Graph database)
- SQLite (comes with Python, used for application data)

**API Keys:**
- Groq API key (required for LLM operations)
- Anthropic API key (optional, for fallback)

**Optional:**
- Redis 5.0+ (for distributed caching in production)
- Docker (for containerized deployment)

### System Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 8 GB
- Storage: 10 GB free space

**Recommended:**
- CPU: 8 cores
- RAM: 16 GB
- Storage: 50 GB free space (for vector indexes and logs)

---

## Installation

### Windows Setup

#### Step 1: Install Python

1. Download Python 3.10+ from [python.org](https://www.python.org/downloads/)
2. Run the installer
3. Check "Add Python to PATH" during installation
4. Verify installation:
```powershell
python --version
pip --version
```

#### Step 2: Install Neo4j

**Option A: Neo4j Desktop (Recommended for Development)**

1. Download Neo4j Desktop from [neo4j.com/download](https://neo4j.com/download/)
2. Install and launch Neo4j Desktop
3. Create a new project
4. Add a local database:
   - Name: amc-context-graph
   - Password: contextgraph (or choose your own)
   - Version: 5.24 or higher
5. Start the database
6. Note the connection details:
   - Bolt URI: bolt://localhost:7687
   - Username: neo4j
   - Password: (your chosen password)

**Option B: Neo4j Server**

1. Download Neo4j Community Edition
2. Extract to a directory (e.g., C:\neo4j)
3. Edit `conf\neo4j.conf`:
```
dbms.default_listen_address=0.0.0.0
dbms.connector.bolt.enabled=true
dbms.connector.bolt.listen_address=:7687
```
4. Start Neo4j:
```powershell
cd C:\neo4j
bin\neo4j.bat console
```
5. Access Neo4j Browser at http://localhost:7474
6. Set initial password when prompted

#### Step 3: Clone Repository and Setup Environment

```powershell
# Navigate to project directory
cd path\to\amc-context-engineering-clean

# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

#### Step 4: Install System Dependencies (if needed)

For PDF processing and OCR capabilities:

```powershell
# Install Visual C++ Redistributable (required for some packages)
# Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
```

---

### Linux Setup

#### Step 1: Install Python

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip
sudo apt install build-essential python3-dev
```

**RHEL/CentOS:**
```bash
sudo yum install python3.10 python3.10-venv python3-pip
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel
```

**Verify installation:**
```bash
python3 --version
pip3 --version
```

#### Step 2: Install Neo4j

**Option A: Using APT (Ubuntu/Debian)**

```bash
# Add Neo4j repository
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
echo 'deb https://debian.neo4j.com stable latest' | sudo tee /etc/apt/sources.list.d/neo4j.list
sudo apt update

# Install Neo4j
sudo apt install neo4j=1:5.24.0

# Configure Neo4j
sudo nano /etc/neo4j/neo4j.conf
# Set: dbms.default_listen_address=0.0.0.0

# Start Neo4j
sudo systemctl start neo4j
sudo systemctl enable neo4j

# Set initial password
cypher-shell
# Run: ALTER USER neo4j SET PASSWORD 'contextgraph';
```

**Option B: Using Docker**

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/contextgraph \
  -v $HOME/neo4j/data:/data \
  neo4j:5.24
```

#### Step 3: Clone Repository and Setup Environment

```bash
# Navigate to project directory
cd /path/to/amc-context-engineering-clean

# Navigate to backend directory
cd backend

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

#### Step 4: Install System Dependencies

**Ubuntu/Debian:**
```bash
# For PDF processing
sudo apt install libpoppler-dev

# For image processing (OCR)
sudo apt install tesseract-ocr libtesseract-dev

# For cryptography
sudo apt install libssl-dev libffi-dev
```

**RHEL/CentOS:**
```bash
sudo yum install poppler-devel
sudo yum install tesseract tesseract-devel
sudo yum install openssl-devel libffi-devel
```

---

## Configuration

### Step 1: Create Environment File

Copy the example environment file and configure it:

**Windows:**
```powershell
cd backend
copy .env.example .env
notepad .env
```

**Linux:**
```bash
cd backend
cp .env.example .env
nano .env
```

### Step 2: Configure Required Settings

Edit the `.env` file with your configuration:

```env
# LLM Configuration (REQUIRED)
GROQ_API_KEY=your_actual_groq_api_key_here
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
LLM_FAST_MODEL=openai/gpt-oss-20b
LLM_MAX_TOKENS=2048

# Neo4j Configuration (REQUIRED)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph
NEO4J_DATABASE=neo4j

# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
LOG_FORMAT=text

# CORS Configuration (adjust for your frontend)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080

# Vector Store
VECTOR_STORE_DIR=./data/vector_store
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=384
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# Microservices Mode (false for monolithic, true for distributed)
MICROSERVICES_MODE=false
FEEDBACK_SERVICE_URL=http://localhost:8001
REPAIR_SERVICE_URL=http://localhost:8002

# Authentication
AUTH_SECRET_KEY=change-this-to-a-secure-random-string-in-production
AUTH_SESSION_TTL_MINUTES=480
AUTH_USE_DATABASE=true

# Query Engine
QUERY_ENGINE=v2
ENABLE_STREAMING=true

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30.0
```

### Step 3: Obtain API Keys

**Groq API Key:**
1. Visit [console.groq.com](https://console.groq.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key (starts with `gsk_`)
6. Add to `.env`: `GROQ_API_KEY=gsk_your_key_here`

**Anthropic API Key (Optional):**
1. Visit [console.anthropic.com](https://console.anthropic.com/)
2. Sign up or log in
3. Generate an API key
4. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-your_key_here`

---

## Database Setup

### Step 1: Verify Neo4j Connection

**Windows:**
```powershell
cd backend
.venv\Scripts\activate
python scripts\test_neo4j_connection.py
```

**Linux:**
```bash
cd backend
source .venv/bin/activate
python scripts/test_neo4j_connection.py
```

Expected output:
```
Connected to Neo4j successfully!
Neo4j version: 5.24.0
Database: neo4j
```

### Step 2: Initialize SQLite Database

The SQLite database is automatically created when the application starts. To verify:

**Windows:**
```powershell
# Check if database file exists
dir data.db
```

**Linux:**
```bash
# Check if database file exists
ls -lh data.db
```

### Step 3: Seed Default Users

Seed the database with default users:

**Windows:**
```powershell
python scripts\seed_users.py
```

**Linux:**
```bash
python scripts/seed_users.py
```

Expected output:
```
Seeding users to database...
Created user: admin (role: admin)
Created user: analyst (role: analyst)
Created user: compliance_officer (role: Compliance & Regulatory Officer)
Successfully seeded 3 users
```

### Step 4: Load Sample Data (Optional)

To load sample SEBI circulars and fund data:

**Windows:**
```powershell
python scripts\ingest_csv.py --file ..\data\sample_circulars.csv
```

**Linux:**
```bash
python scripts/ingest_csv.py --file ../data/sample_circulars.csv
```

---

## Running the Application

### Monolithic Mode (Recommended for Development)

**Windows:**
```powershell
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Linux:**
```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Microservices Mode (Advanced)

For production or when testing distributed architecture:

**Terminal 1 - Main Backend:**
```bash
cd backend
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 - Feedback Loop Service:**
```bash
cd packages/amc-feedback-loop
source ../../backend/.venv/bin/activate
python -m uvicorn src.feedback_loop.server:app --port 8001
```

**Terminal 3 - Repair Engine Service:**
```bash
cd packages/amc-repair-engine
source ../../backend/.venv/bin/activate
python -m uvicorn src.amc_repair.server:app --port 8002
```

**Note:** Set `MICROSERVICES_MODE=true` in `.env` when using this mode.

### Production Mode

For production deployment without auto-reload:

**Windows:**
```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Linux:**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Verification

### Step 1: Health Check

Once the server is running, verify it is healthy:

**Using curl (Linux/Windows with curl installed):**
```bash
curl http://localhost:8000/health
```

**Using PowerShell:**
```powershell
Invoke-WebRequest -Uri http://localhost:8000/health -Method GET
```

**Using browser:**
Visit http://localhost:8000/health

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-10-22T10:30:00.000Z",
  "version": "2.1",
  "services": {
    "database": "connected",
    "neo4j": "connected",
    "vector_store": "ready"
  }
}
```

### Step 2: API Documentation

Access the interactive API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Step 3: Test Authentication

Test login endpoint:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@2026","remember_me":false}'
```

Expected response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "username": "admin",
    "role": "admin",
    "full_name": "System Administrator"
  },
  "expires_at": 1729600000
}
```

### Step 4: Test Query Endpoint

Using the token from login:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is SEBI?"}'
```

### Step 5: Verify Background Services

Check scheduler status:

```bash
curl http://localhost:8000/api/health/scheduler
```

Expected response:
```json
{
  "status": "running",
  "jobs": [
    {
      "id": "sebi_polling",
      "name": "SEBI RSS Feed Polling",
      "next_run_time": "2026-10-23T03:00:00Z"
    },
    ...
  ]
}
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: Python Not Found

**Symptoms:**
```
'python' is not recognized as an internal or external command
```

**Solution (Windows):**
1. Reinstall Python with "Add to PATH" option checked
2. Or add Python to PATH manually:
   - Search for "Environment Variables"
   - Edit System PATH
   - Add: `C:\Users\YourUser\AppData\Local\Programs\Python\Python310`

**Solution (Linux):**
```bash
# Use python3 instead of python
python3 -m venv .venv
```

#### Issue 2: Neo4j Connection Failed

**Symptoms:**
```
Failed to establish connection to Neo4j
neo4j.exceptions.ServiceUnavailable: Unable to connect to bolt://localhost:7687
```

**Solution:**
1. Verify Neo4j is running:
   - Neo4j Desktop: Check database status
   - Linux: `sudo systemctl status neo4j`
   - Docker: `docker ps | grep neo4j`

2. Check connection details in `.env`:
   - URI: `bolt://localhost:7687` (not `neo4j://`)
   - Username: `neo4j`
   - Password: matches Neo4j password

3. Test connection from Neo4j Browser: http://localhost:7474

4. Check firewall rules:
   - Windows: Allow port 7687 in Windows Defender
   - Linux: `sudo ufw allow 7687`

#### Issue 3: Module Not Found Errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution:**
1. Ensure virtual environment is activated:
   - Windows: `.venv\Scripts\activate`
   - Linux: `source .venv/bin/activate`

2. Reinstall dependencies:
```bash
pip install -r requirements.txt
```

3. If specific package fails, install individually:
```bash
pip install fastapi uvicorn
```

#### Issue 4: Port Already in Use

**Symptoms:**
```
ERROR:    [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000): 
only one usage of each socket address is normally permitted
```

**Solution (Windows):**
1. Find process using port 8000:
```powershell
netstat -ano | findstr :8000
```

2. Kill the process:
```powershell
taskkill /PID <PID> /F
```

**Solution (Linux):**
1. Find process using port 8000:
```bash
lsof -i :8000
```

2. Kill the process:
```bash
kill -9 <PID>
```

3. Or use a different port:
```bash
python -m uvicorn app.main:app --port 8001
```

#### Issue 5: Groq API Key Invalid

**Symptoms:**
```
401 Unauthorized: Invalid API key
```

**Solution:**
1. Verify API key in `.env` starts with `gsk_`
2. Regenerate key at https://console.groq.com/
3. Ensure no extra spaces or quotes around the key
4. Restart the server after updating `.env`

#### Issue 6: Permission Denied (Linux)

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: './data'
```

**Solution:**
```bash
# Create directories with proper permissions
mkdir -p data logs faiss_indexes
chmod 755 data logs faiss_indexes

# Or run as root (not recommended for production)
sudo python -m uvicorn app.main:app --port 8000
```

#### Issue 7: SSL Certificate Errors

**Symptoms:**
```
ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

**Solution (Windows):**
1. Install certificates:
```powershell
pip install --upgrade certifi
python -m pip install --upgrade pip
```

2. Or disable SSL verification (development only):
Add to `.env`:
```env
CURL_CA_BUNDLE=
```

**Solution (Linux):**
```bash
sudo apt install ca-certificates
sudo update-ca-certificates
```

#### Issue 8: Database Migration Errors

**Symptoms:**
```
sqlalchemy.exc.OperationalError: table auth_users already exists
```

**Solution:**
1. Check if database is corrupted:
```bash
# Backup existing database
cp data.db data.db.backup

# Remove database
rm data.db

# Restart server to recreate
python -m uvicorn app.main:app --reload
```

2. Or manually run migrations:
```bash
python scripts/migrate_database.py
```

#### Issue 9: Out of Memory Errors

**Symptoms:**
```
MemoryError: Unable to allocate array
```

**Solution:**
1. Reduce batch size in configuration
2. Increase system RAM
3. Use smaller embedding model:
   - Change in `.env`: `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`
   - Dimension: `EMBEDDING_DIM=384`

4. Close other applications

#### Issue 10: Slow Query Performance

**Symptoms:**
- Queries take > 5 seconds
- High CPU usage

**Solution:**
1. Check Neo4j indexes:
```cypher
SHOW INDEXES
```

2. Create missing indexes:
```cypher
CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.document_id);
CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name);
```

3. Verify vector store is loaded:
```bash
ls -lh data/vector_store/
```

4. Enable query caching in `.env`:
```env
ENABLE_QUERY_CACHE=true
CACHE_TTL_SECONDS=3600
```

---

## Development Workflow

### Project Structure

```
backend/
├── app/                        # Main application code
│   ├── main.py                 # FastAPI application entry point
│   ├── api/                    # API routes and endpoints
│   ├── core/                   # Core business logic
│   ├── auth/                   # Authentication and authorization
│   ├── retrieval/              # RAG orchestration
│   ├── graph/                  # Neo4j operations
│   ├── vector/                 # FAISS vector search
│   ├── feedback/               # Feedback loop
│   ├── ingestion/              # Document ingestion
│   ├── models/                 # Data models
│   ├── schemas/                # Pydantic schemas
│   └── services/               # Business services
├── scripts/                    # Utility scripts
├── tests/                      # Test suite
├── config/                     # Configuration files
├── data/                       # Data storage
├── logs/                       # Application logs
├── .env                        # Environment configuration
├── requirements.txt            # Python dependencies
└── pytest.ini                  # Test configuration
```

### Code Style

Follow PEP 8 style guide:
```bash
# Install formatters
pip install black isort flake8

# Format code
black app/
isort app/

# Check style
flake8 app/
```

### Adding New Features

1. Create feature branch:
```bash
git checkout -b feature/your-feature-name
```

2. Implement changes in appropriate module
3. Add tests in `tests/` directory
4. Update documentation
5. Run tests:
```bash
pytest tests/
```

6. Commit and push:
```bash
git add .
git commit -m "Add feature: description"
git push origin feature/your-feature-name
```

### Database Migrations

When modifying database schema:

1. Update SQLAlchemy models in `app/schemas/`
2. Create migration script in `scripts/migrations/`
3. Test migration on development database
4. Document changes in migration notes

### Logging

Access logs:

**Windows:**
```powershell
Get-Content logs\app.log -Tail 50 -Wait
```

**Linux:**
```bash
tail -f logs/app.log
```

Configure log level in `.env`:
```env
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

---

## Testing

### Run All Tests

**Windows:**
```powershell
.venv\Scripts\activate
pytest tests\ -v
```

**Linux:**
```bash
source .venv/bin/activate
pytest tests/ -v
```

### Run Specific Test Module

```bash
pytest tests/test_auth.py -v
```

### Run Tests with Coverage

```bash
pip install pytest-cov
pytest tests/ --cov=app --cov-report=html
```

View coverage report:
```bash
# Windows
start htmlcov\index.html

# Linux
xdg-open htmlcov/index.html
```

### Integration Tests

Run integration tests (requires running Neo4j):

```bash
pytest tests/integration/ -v
```

### Load Testing

Run load tests with Locust:

```bash
pip install locust
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

Access Locust UI at http://localhost:8089

### Test User Credentials

Default test users:

| Username | Password | Role |
|----------|----------|------|
| admin | Admin@2026 | admin |
| analyst | Analyst@2026 | analyst |
| compliance_officer | Compliance@2026 | Compliance & Regulatory Officer |

---

## Performance Optimization

### Database Tuning

**Neo4j Configuration (`neo4j.conf`):**
```
# Memory allocation
dbms.memory.heap.initial_size=2G
dbms.memory.heap.max_size=4G
dbms.memory.pagecache.size=2G

# Query timeout
dbms.transaction.timeout=30s

# Bolt threading
dbms.connector.bolt.thread_pool_min_size=5
dbms.connector.bolt.thread_pool_max_size=400
```

### Caching

Enable application-level caching:

```env
ENABLE_QUERY_CACHE=true
CACHE_TTL_SECONDS=3600
CACHE_MAX_SIZE=1000
```

### Vector Store Optimization

Pre-warm vector store on startup:

```env
PRELOAD_VECTOR_STORE=true
VECTOR_INDEX_TYPE=IVF_FLAT
VECTOR_NPROBE=10
```

### Monitoring

Enable Prometheus metrics:

```env
ENABLE_METRICS=true
METRICS_PORT=9090
```

Access metrics at http://localhost:9090/metrics

---

## Security Hardening

### Production Configuration

1. Change default passwords:
```env
AUTH_SECRET_KEY=<generate-strong-random-key>
NEO4J_PASSWORD=<strong-password>
```

2. Restrict CORS:
```env
CORS_ORIGINS=https://your-production-domain.com
```

3. Enable HTTPS:
```bash
uvicorn app.main:app --ssl-keyfile=key.pem --ssl-certfile=cert.pem
```

4. Set secure session timeout:
```env
AUTH_SESSION_TTL_MINUTES=60
```

5. Enable rate limiting:
```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### Secrets Management

Use environment variables or secret managers:

**AWS SSM:**
```bash
export GROQ_API_KEY=$(aws ssm get-parameter --name /app/groq-api-key --with-decryption --query Parameter.Value --output text)
```

**Azure Key Vault:**
```bash
export GROQ_API_KEY=$(az keyvault secret show --vault-name your-vault --name groq-api-key --query value -o tsv)
```

---

## Additional Resources

### Documentation
- FastAPI Documentation: https://fastapi.tiangolo.com/
- Neo4j Documentation: https://neo4j.com/docs/
- Groq API Documentation: https://console.groq.com/docs

### Support
- GitHub Issues: Create an issue in the repository
- Internal Documentation: See `docs/` directory
- Email: support@nusummit.com

### Version Information
- Backend Version: 2.1
- Python Version: 3.10+
- Neo4j Version: 5.24+
- FastAPI Version: 0.115+

---

**Last Updated:** October 22, 2026  
**Document Version:** 1.0  
**Maintainer:** NuSummit Technologies Pvt Ltd
