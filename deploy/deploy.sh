#!/usr/bin/env bash
# One-shot deployer for the NuSummit ContextGraph demo (SCP code flow).
# Creates: key pair, security group, IAM role/instance profile, EC2 t3.micro.
# Then copies the local project to EC2 and brings the stack up.
#
# PREREQUISITES (see deploy/README.md):
#   1. aws CLI authenticated (aws sts get-caller-identity)
#   2. Anthropic key already in AWS Secrets Manager (default /dev/microsoft-app-id,
#      JSON field ANTHROPIC_API_KEY) in the target region.
#
# Re-runnable: skips resources that already exist. Review before running.
set -euo pipefail

# Git Bash / MSYS on Windows rewrites args like "/dev/microsoft-app-id" into
# Windows paths, breaking AWS names/ARNs. Disable that conversion for this run.
export MSYS_NO_PATHCONV=1

# ---------------- config ----------------
REGION="${REGION:-ap-south-1}"
NAME="${NAME:-amc-demo}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
KEY_NAME="$NAME-key"
SG_NAME="$NAME-sg"
ROLE_NAME="$NAME-ec2-role"
PROFILE_NAME="$NAME-ec2-profile"
SECRET_ID="${SECRET_ID:-/dev/microsoft-app-id}"
SECRET_JSON_KEY="${SECRET_JSON_KEY:-ANTHROPIC_API_KEY}"
PEM="$HOME/.ssh/$KEY_NAME.pem"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/.." && pwd)"

echo ">> Region=$REGION  Instance=$INSTANCE_TYPE  Name=$NAME"

# ---------------- 0. guard: secret present ----------------
SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "$SECRET_ID" \
  --region "$REGION" --query ARN --output text 2>/dev/null || echo None)"
if [ "$SECRET_ARN" = "None" ] || [ -z "$SECRET_ARN" ]; then
  echo "!! Secrets Manager secret '$SECRET_ID' not found in $REGION."
  exit 1
fi
echo ">> Secret: $SECRET_ARN (field $SECRET_JSON_KEY)"

# ---------------- 1. key pair ----------------
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" >/dev/null 2>&1; then
  echo ">> Creating key pair -> $PEM"
  mkdir -p "$HOME/.ssh"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --region "$REGION" \
    --query KeyMaterial --output text > "$PEM"
  chmod 600 "$PEM"
else
  echo ">> Key pair $KEY_NAME exists (expecting private key at $PEM)"
fi

# ---------------- 2. security group ----------------
MY_IP="$(curl -fsS https://checkip.amazonaws.com)/32"
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text --region "$REGION")"
SG_ID="$(aws ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text --region "$REGION" 2>/dev/null || echo None)"
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  echo ">> Creating security group $SG_NAME in $VPC_ID"
  SG_ID="$(aws ec2 create-security-group --group-name "$SG_NAME" \
    --description "AMC demo" --vpc-id "$VPC_ID" --region "$REGION" \
    --query GroupId --output text)"
  # SSH restricted to your IP; HTTP/HTTPS/API open for the demo.
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
    --ip-permissions \
      IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges="[{CidrIp=$MY_IP,Description=ssh}]" \
      IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges="[{CidrIp=0.0.0.0/0}]" \
      IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges="[{CidrIp=0.0.0.0/0}]" \
      IpProtocol=tcp,FromPort=8000,ToPort=8000,IpRanges="[{CidrIp=0.0.0.0/0}]"
else
  echo ">> Security group $SG_NAME exists ($SG_ID)"
fi

# ---------------- 3. IAM role + instance profile (SSM read) ----------------
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo ">> Creating IAM role $ROLE_NAME"
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name secret-read \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"secretsmanager:GetSecretValue\"],\"Resource\":\"$SECRET_ARN\"}]}" >/dev/null
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME" >/dev/null
  sleep 10  # let the instance profile propagate
else
  echo ">> IAM role $ROLE_NAME exists"
fi

# ---------------- 4. launch EC2 ----------------
AMI="$(aws ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text --region "$REGION")"
echo ">> Latest AL2023 AMI: $AMI"

INSTANCE_ID="$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values="$NAME" Name=instance-state-name,Values=running,pending \
  --query 'Reservations[0].Instances[0].InstanceId' --output text --region "$REGION" 2>/dev/null || echo None)"
if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
  echo ">> Launching $INSTANCE_TYPE ..."
  INSTANCE_ID="$(aws ec2 run-instances \
    --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" --security-group-ids "$SG_ID" \
    --iam-instance-profile Name="$PROFILE_NAME" \
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}' \
    --user-data "$(cat "$HERE/ec2-bootstrap.sh")" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
    --region "$REGION" --query 'Instances[0].InstanceId' --output text)"
else
  echo ">> Reusing running instance $INSTANCE_ID"
fi

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region "$REGION")"
echo ">> Instance $INSTANCE_ID @ $PUBLIC_IP"

# ---------------- 5. wait for bootstrap, copy code, start stack ----------------
SSH="ssh -o StrictHostKeyChecking=accept-new -i $PEM ec2-user@$PUBLIC_IP"
echo ">> Waiting for SSH + bootstrap (Docker install + swap)..."
until $SSH 'test -f /home/ec2-user/.bootstrap-done' 2>/dev/null; do sleep 10; done

echo ">> Copying project (tar over SSH; excludes local junk) ..."
$SSH 'mkdir -p /home/ec2-user/app'
tar -C "$PROJECT_ROOT" \
  --exclude='.git' --exclude='node_modules' --exclude='.venv' \
  --exclude='frontend/dist' --exclude='data' --exclude='__pycache__' \
  -czf - . | $SSH 'tar -xzf - -C /home/ec2-user/app'

echo ">> Writing .env and starting the stack ..."
$SSH "cat > /home/ec2-user/app/.env <<EOF
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph
QDRANT_URL=http://qdrant:6333
ENVIRONMENT=production
LOG_LEVEL=INFO
AWS_REGION=$REGION
ANTHROPIC_SECRET_ID=$SECRET_ID
ANTHROPIC_SECRET_JSON_KEY=$SECRET_JSON_KEY
EOF
cd /home/ec2-user/app && docker compose up -d"

cat <<DONE

============================================================
Stack starting on EC2.
  API:     http://$PUBLIC_IP:8000/docs
  SSH:     ssh -i $PEM ec2-user@$PUBLIC_IP
Next (after neo4j is healthy):
  $SSH 'cd app && docker compose exec api python -m scripts.seed_neo4j'
  $SSH 'cd app && docker compose exec api python -m scripts.ingest_corpus'
============================================================
DONE
