# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Parser Lambda (container image). Build context = repo root:
#   docker build -f deploy/lambda/Dockerfile -t amc-demo-parser .
FROM public.ecr.aws/lambda/python:3.12

# Deps
COPY deploy/lambda/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared ingestion package (parsers + chunker + pii). Importable as `ingestion`.
COPY backend/app/ingestion ${LAMBDA_TASK_ROOT}/ingestion

# Handler
COPY deploy/lambda/handler.py ${LAMBDA_TASK_ROOT}/handler.py

# Fail the build early if imports are broken.
RUN python -c "import handler"

CMD ["handler.lambda_handler"]
