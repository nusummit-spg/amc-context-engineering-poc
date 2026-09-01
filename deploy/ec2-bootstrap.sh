#!/usr/bin/env bash
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# EC2 user-data for the SCP deploy flow: prepares the host (swap + Docker) but
# does NOT fetch code — deploy.sh copies the project over SSH afterward.
# Amazon Linux 2023. Runs once at first boot as root.
set -euxo pipefail

# --- Swap: safety net even on t3.medium (4GB) — the engine loads torch +
#     GLiNER + a sentence-transformer, and headroom is still tight under load. ---
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- Docker + Compose v2 plugin ---
dnf update -y
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL \
  https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# buildx — required by `docker compose build` (>=0.17). AL2023's docker pkg omits it.
curl -fsSL \
  https://github.com/docker/buildx/releases/download/v0.17.1/buildx-v0.17.1.linux-amd64 \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx

# Marker so deploy.sh can poll for bootstrap completion.
touch /home/ec2-user/.bootstrap-done
chown ec2-user:ec2-user /home/ec2-user/.bootstrap-done
