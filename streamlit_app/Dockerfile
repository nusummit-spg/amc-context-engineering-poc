# Streamlit UI — self-sufficient: runs the full local retrieval engine
# in-process (faiss/gliner/spacy/sentence-transformers), no separate FastAPI
# backend required. See .dockerignore for what's excluded from the build
# context (secrets, raw source corpora already baked into faiss_indexes/).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501
# fileWatcherType=none: no source hot-reload needed in a built image, and the
# torch/gliner C-extension modules crash the default poll-based watcher's
# module introspection on every poll (repeated, harmless but log-spamming
# "ModuleNotFoundError: No module named 'torchvision'" — confirmed live).
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.fileWatcherType=none"]
