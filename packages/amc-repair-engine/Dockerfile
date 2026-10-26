# ===========================================================================
# Repair Engine Microservice Dockerfile
# ===========================================================================

FROM python:3.11-slim

LABEL maintainer="NuSummit Technologies"
LABEL description="AMC Repair Engine - Standalone Microservice"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install uvicorn and other production dependencies
RUN pip install --no-cache-dir \
    uvicorn[standard]>=0.30 \
    python-dotenv>=1.0 \
    tenacity>=9.0

# Copy source code
COPY . .

# Install amc-repair-engine from source
RUN pip install -e .

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

# Set environment variables (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=info
ENV HOST=0.0.0.0
ENV PORT=8002

# Start server
CMD ["python", "-m", "uvicorn", "src.amc_repair.server:app", \
     "--host", "0.0.0.0", "--port", "8002", "--log-level", "info"]

