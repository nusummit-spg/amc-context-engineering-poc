#!/usr/bin/env bash
# EC2 user-data bootstrap for the NuSummit ContextGraph demo (Amazon Linux 2023).
# Paste into "Advanced details → User data" when launching the t3.micro, or run
# manually after SSH. Idempotent-ish; safe to re-run.
set -euxo pipefail

# --- 1. Swap: safety net for the 1GB t3.micro (fastembed loads an ONNX model) ---
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048   # 2 GB swap
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- 2. Docker + Compose v2 ---
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL \
  https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# --- 3. Clone + start the stack ---
# Replace REPO_URL with your repository. The .env below carries non-secret config;
# the Anthropic key is pulled from SSM at startup (see config.py / IAM role).
cd /home/ec2-user
sudo -u ec2-user git clone REPO_URL app || true
cd app

cat > .env <<'EOF'
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph
QDRANT_URL=http://qdrant:6333
ENVIRONMENT=production
LOG_LEVEL=INFO
AWS_REGION=ap-south-1
ANTHROPIC_SECRET_ID=/dev/microsoft-app-id
ANTHROPIC_SECRET_JSON_KEY=ANTHROPIC_API_KEY
EOF

docker compose up -d

# After neo4j is healthy, seed + ingest (run manually or uncomment):
# docker compose exec api python -m scripts.seed_neo4j
# docker compose exec api python -m scripts.ingest_corpus
