#!/usr/bin/env bash
# One-shot deployer for the NuSummit ContextGraph demo (SCP code flow).
# Creates: key pair, security group (22/80/443/8000/8501), S3 corpus bucket,
# IAM role/instance profile, EC2 t3.medium, Elastic IP.
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
# t3.micro (1GB) is NOT enough — proven live: the engine loads torch + GLiNER +
# a sentence-transformer, which OOM-crashes a 1GB box even with the API alone,
# let alone alongside Streamlit. t3.medium (4GB) is the tested minimum.
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
KEY_NAME="$NAME-key"
SG_NAME="$NAME-sg"
ROLE_NAME="$NAME-ec2-role"
PROFILE_NAME="$NAME-ec2-profile"
SECRET_ID="${SECRET_ID:-/dev/microsoft-app-id}"
SECRET_JSON_KEY="${SECRET_JSON_KEY:-ANTHROPIC_API_KEY}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
CORPUS_BUCKET="${CORPUS_BUCKET:-$NAME-corpus-$ACCOUNT_ID}"
LOG_GROUP="/$NAME/app"   # container logs (all services, awslogs driver) — see docker-compose.yml
PEM="$HOME/.ssh/$KEY_NAME.pem"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/.." && pwd)"

echo ">> Region=$REGION  Instance=$INSTANCE_TYPE  Name=$NAME  CorpusBucket=$CORPUS_BUCKET"

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
  # SSH restricted to your IP; HTTP/HTTPS/API/Streamlit open for the demo.
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
    --ip-permissions \
      IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges="[{CidrIp=$MY_IP,Description=ssh}]" \
      IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges="[{CidrIp=0.0.0.0/0}]" \
      IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges="[{CidrIp=0.0.0.0/0}]" \
      IpProtocol=tcp,FromPort=8000,ToPort=8000,IpRanges="[{CidrIp=0.0.0.0/0}]" \
      IpProtocol=tcp,FromPort=8080,ToPort=8080,IpRanges="[{CidrIp=0.0.0.0/0,Description=streamlit}]"
else
  echo ">> Security group $SG_NAME exists ($SG_ID)"
fi

# ---------------- 3. S3 corpus bucket ----------------
if aws s3api head-bucket --bucket "$CORPUS_BUCKET" --region "$REGION" >/dev/null 2>&1; then
  echo ">> S3 bucket $CORPUS_BUCKET exists"
else
  echo ">> Creating S3 bucket $CORPUS_BUCKET"
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$CORPUS_BUCKET" --region "$REGION" >/dev/null
  else
    aws s3api create-bucket --bucket "$CORPUS_BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  fi
  aws s3api put-public-access-block --bucket "$CORPUS_BUCKET" --region "$REGION" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi
CORPUS_BUCKET_ARN="arn:aws:s3:::$CORPUS_BUCKET"

# ---------------- 3b. CloudWatch log group (container logs, awslogs driver) ----------------
if ! aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region "$REGION" \
    --query "logGroups[?logGroupName=='$LOG_GROUP']" --output text | grep -q .; then
  echo ">> Creating CloudWatch log group $LOG_GROUP"
  aws logs create-log-group --log-group-name "$LOG_GROUP" --region "$REGION"
  aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 14 --region "$REGION"
else
  echo ">> CloudWatch log group $LOG_GROUP exists"
fi
LOG_GROUP_ARN="arn:aws:logs:$REGION:$ACCOUNT_ID:log-group:$LOG_GROUP"

# ---------------- 4. IAM role + instance profile ----------------
# Role/profile creation is one-time (skipped if they already exist), but the
# policy attachments below always run — put-role-policy is idempotent, and
# this is what lets a re-run pick up a newly-created corpus bucket even
# against an already-existing role.
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo ">> Creating IAM role $ROLE_NAME"
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME" >/dev/null
  NEW_ROLE=1
else
  echo ">> IAM role $ROLE_NAME exists"
  NEW_ROLE=0
fi

echo ">> Applying IAM policies (secret-read, s3-corpus-read, cloudwatch-logs) ..."
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name secret-read \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"secretsmanager:GetSecretValue\"],\"Resource\":\"$SECRET_ARN\"}]}" >/dev/null
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name s3-corpus-read \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:ListBucket\"],\"Resource\":[\"$CORPUS_BUCKET_ARN\",\"$CORPUS_BUCKET_ARN/*\"]}]}" >/dev/null
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name cloudwatch-logs \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"logs:CreateLogStream\",\"logs:PutLogEvents\",\"logs:DescribeLogStreams\"],\"Resource\":\"$LOG_GROUP_ARN:*\"}]}" >/dev/null

if [ "$NEW_ROLE" = "1" ]; then
  sleep 10  # let the instance profile propagate before EC2 tries to use it
fi

# ---------------- 5. launch EC2 ----------------
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

# ---------------- 6. Elastic IP (stable address across stop/start) ----------------
EXISTING_EIP="$(aws ec2 describe-addresses --filters "Name=instance-id,Values=$INSTANCE_ID" \
  --query 'Addresses[0].PublicIp' --output text --region "$REGION" 2>/dev/null || echo None)"
if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
  echo ">> Allocating + associating an Elastic IP ..."
  ALLOC_ID="$(aws ec2 allocate-address --domain vpc --region "$REGION" --query AllocationId --output text)"
  aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --region "$REGION" >/dev/null
  PUBLIC_IP="$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --region "$REGION" --query 'Addresses[0].PublicIp' --output text)"
else
  echo ">> Elastic IP already associated: $EXISTING_EIP"
  PUBLIC_IP="$EXISTING_EIP"
fi
echo ">> Stable public IP: $PUBLIC_IP"

# ---------------- 7. wait for bootstrap, copy code, start stack ----------------
SSH="ssh -o StrictHostKeyChecking=accept-new -i $PEM ec2-user@$PUBLIC_IP"
echo ">> Waiting for SSH + bootstrap (Docker install + swap)..."
until $SSH 'test -f /home/ec2-user/.bootstrap-done' 2>/dev/null; do sleep 10; done

echo ">> Copying project (tar over SSH; excludes local junk) ..."
$SSH 'mkdir -p /home/ec2-user/app'
tar -C "$PROJECT_ROOT" \
  --exclude='.git' --exclude='node_modules' --exclude='.venv' \
  --exclude='frontend/dist' --exclude='./data' --exclude='./backend/data' \
  --exclude='__pycache__' \
  -czf - . | $SSH 'tar -xzf - -C /home/ec2-user/app'

echo ">> Writing .env and starting the stack ..."
$SSH "cat > /home/ec2-user/app/.env <<EOF
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph
ENVIRONMENT=production
LOG_LEVEL=INFO
AWS_REGION=$REGION
ANTHROPIC_SECRET_ID=$SECRET_ID
ANTHROPIC_SECRET_JSON_KEY=$SECRET_JSON_KEY
CORPUS_BUCKET=$CORPUS_BUCKET
EOF
cd /home/ec2-user/app && docker compose up -d --build"

# ---------------- 8. periodic S3 corpus reindex (cron) ----------------
echo ">> Installing reindex cron (every 15 min, flock-guarded) ..."
$SSH 'sudo dnf install -y cronie >/dev/null 2>&1
sudo systemctl enable --now crond >/dev/null 2>&1
sudo tee /etc/logrotate.d/reindex >/dev/null <<EOF
/home/ec2-user/reindex.log { weekly rotate 4 compress missingok notifempty maxsize 20M }
EOF
(crontab -l 2>/dev/null; echo "*/15 * * * * /usr/bin/flock -n /tmp/reindex.lock -c \"cd /home/ec2-user/app && /usr/bin/docker compose exec -T api python -m app.engine.reindex_from_s3\" >> /home/ec2-user/reindex.log 2>&1") | sort -u | crontab -'

cat <<DONE

============================================================
Stack starting on EC2.
  API:         http://$PUBLIC_IP:8000/docs
  Streamlit:   http://$PUBLIC_IP:8080
  SSH:         ssh -i $PEM ec2-user@$PUBLIC_IP
  Corpus:      s3://$CORPUS_BUCKET/raw/  (drop new files here — reindexed automatically every 15 min)
  Reindex log: /home/ec2-user/reindex.log
Manual reindex (skip waiting for cron):
  $SSH 'cd app && docker compose exec -T api python -m app.engine.reindex_from_s3'
============================================================
DONE
