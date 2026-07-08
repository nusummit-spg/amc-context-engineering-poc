# Streamlit context-engineering demo UI.
# Heavy ML deps (torch via sentence-transformers / gliner / easyocr) — build on
# an instance with >= 4GB RAM (t3.medium).
FROM python:3.12-slim

WORKDIR /app

# System libs: libGL/glib for opencv (easyocr), fonts for pymupdf rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501
# HF model cache persists via the /root/.cache mount (see compose) so GLiNER +
# the sentence-transformer aren't re-downloaded on every restart.
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
