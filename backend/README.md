# Backend - AMC Context Engineering Platform

FastAPI-based backend for the AMC Context Engineering Platform providing RAG, Graph Knowledge, and SEBI compliance capabilities.

---

## Quick Links

- **[Complete Setup Guide](./SETUP_GUIDE.md)** - Comprehensive installation and configuration instructions for Windows and Linux
- **[API Documentation](http://localhost:8000/docs)** - Interactive API documentation (when server is running)
- **[Health Check](http://localhost:8000/health)** - Service health status

---

## Quick Start

### Prerequisites
- Python 3.10 or higher
- Neo4j 5.24 or higher
- Groq API key

### Installation

1. Create virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run the server:
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Access API documentation:
```
http://localhost:8000/docs
```

---

## Documentation

For detailed setup instructions including:
- Platform-specific installation steps (Windows/Linux)
- Neo4j database configuration
- Troubleshooting common issues
- Development workflow
- Testing procedures
- Performance optimization

**See:** [SETUP_GUIDE.md](./SETUP_GUIDE.md)

---

## Project Structure

```
backend/
├── app/                        # Application code
│   ├── main.py                 # FastAPI entry point
│   ├── api/                    # API routes
│   ├── auth/                   # Authentication
│   ├── core/                   # Core business logic
│   ├── retrieval/              # RAG orchestration
│   ├── graph/                  # Neo4j operations
│   ├── vector/                 # FAISS vector search
│   ├── feedback/               # Feedback loop
│   ├── ingestion/              # Document ingestion
│   └── services/               # Business services
├── scripts/                    # Utility scripts
├── tests/                      # Test suite
├── config/                     # Configuration files
├── data/                       # Data storage
├── logs/                       # Application logs
├── .env                        # Environment config (create from .env.example)
├── requirements.txt            # Python dependencies
└── SETUP_GUIDE.md             # Complete setup instructions
```

---

## Key Features

- Hybrid RAG (Graph + Vector Retrieval)
- Multi-turn conversations with context
- Semantic caching (sub-30ms response)
- Passive feedback learning
- SEBI compliance validation
- Real-time streaming responses
- Token revocation and rate limiting
- Circuit breakers for resilience
- Distributed tracing
- Prometheus metrics

---

## API Endpoints

### Authentication
- `POST /api/auth/login` - User authentication
- `POST /api/auth/logout` - Token revocation
- `GET /api/auth/me` - Current user info

### Query & Chat
- `POST /api/query` - Single query execution
- `POST /api/chat` - Multi-turn conversation
- `GET /api/chat/history` - Conversation history

### Feedback
- `POST /api/feedback` - Submit feedback
- `GET /api/feedback/issues` - List feedback issues
- `POST /api/feedback/resolve` - Resolve feedback

### Administration
- `GET /api/admin/users` - List users
- `POST /api/admin/users` - Create user
- `GET /api/health` - Health check
- `GET /api/health/scheduler` - Scheduler status

**Full API Reference:** http://localhost:8000/docs (when server is running)

---

## Environment Variables

Key configuration options (see `.env.example` for complete list):

```env
# LLM Configuration
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=openai/gpt-oss-120b

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph

# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Authentication
AUTH_SECRET_KEY=change-in-production
AUTH_SESSION_TTL_MINUTES=480
```

---

## Testing

Run all tests:
```bash
pytest tests/ -v
```

Run with coverage:
```bash
pytest tests/ --cov=app --cov-report=html
```

Run specific test module:
```bash
pytest tests/test_auth.py -v
```

---

## Default Test Users

| Username | Password | Role |
|----------|----------|------|
| admin | Admin@2026 | admin |
| analyst | Analyst@2026 | analyst |
| compliance_officer | Compliance@2026 | Compliance & Regulatory Officer |

---

## Troubleshooting

For common issues and solutions, see the [Troubleshooting](./SETUP_GUIDE.md#troubleshooting) section in the Setup Guide.

Quick checks:
1. Verify Neo4j is running: `curl http://localhost:7474`
2. Check Python version: `python --version` (should be 3.10+)
3. Verify virtual environment is activated
4. Check logs: `tail -f logs/app.log`

---

## Production Deployment

For production deployment:
1. Use production-grade WSGI server (Gunicorn/Uvicorn with workers)
2. Configure HTTPS/TLS certificates
3. Set secure environment variables
4. Enable monitoring and alerting
5. Configure database backups
6. Set up log aggregation

See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for detailed production configuration.

---

## Support

- Documentation: [SETUP_GUIDE.md](./SETUP_GUIDE.md)
- API Docs: http://localhost:8000/docs
- Issues: Create an issue in the repository
- Email: support@nusummit.com

---

**Version:** 2.1  
**Python:** 3.10+  
**Status:** Production Ready
