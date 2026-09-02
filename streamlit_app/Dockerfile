# Streamlit UI — thin client over the FastAPI backend for querying (no torch/
# faiss/gliner). config.py + graph_store.py are lightweight (Neo4j driver
# only) and power the Analytics tab's direct graph browsing.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py compare_view.py chat_view.py analytics_view.py config.py graph_store.py ./
COPY .streamlit ./.streamlit

EXPOSE 8501
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
