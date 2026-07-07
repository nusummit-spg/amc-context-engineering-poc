# Deploy — AWS free-tier (single EC2)

Deploys the whole stack (nginx-less for now: FastAPI + Neo4j + Qdrant + Redis via
Docker Compose) to one EC2 t3.micro. Code is copied over SSH (no GitHub creds on
the box). Region defaults to **ap-south-1**.

## What gets created
| Resource | Notes | Cost |
|---|---|---|
| Key pair `amc-demo-key` | Private key saved to `~/.ssh/amc-demo-key.pem` | free |
| Security group `amc-demo-sg` | SSH from your IP only; 80/443/8000 open | free |
| IAM role + instance profile | grants `secretsmanager:GetSecretValue` on the secret | free |
| EC2 `t3.micro` + 30 GB gp3 | runs the stack | free tier |
| Secrets Manager secret (already exists) | `/dev/microsoft-app-id`, JSON field `ANTHROPIC_API_KEY` | free-ish |

## Steps

```bash
# 0. Authenticated? (secret already lives in Secrets Manager, ap-south-1)
aws sts get-caller-identity

# 1. Deploy (creates infra, copies code, starts the stack):
bash deploy/deploy.sh
#    Override defaults if needed:
#    REGION=ap-south-1 SECRET_ID=/dev/microsoft-app-id bash deploy/deploy.sh

# 2. When the script finishes, seed + ingest:
ssh -i ~/.ssh/amc-demo-key.pem ec2-user@<IP> 'cd app && docker compose exec api python -m scripts.seed_neo4j'
ssh -i ~/.ssh/amc-demo-key.pem ec2-user@<IP> 'cd app && docker compose exec api python -m scripts.ingest_corpus'
```

API docs land at `http://<IP>:8000/docs`.

## Requirements on your machine
- `aws` CLI v2, authenticated
- `ssh` + `rsync` (Git Bash on Windows has both)

## Teardown (avoid charges)
```bash
# Stop (keeps EBS + data, ~$2.40/mo after free tier):
aws ec2 stop-instances --instance-ids <id> --region ap-south-1
# OR fully delete everything:
aws ec2 terminate-instances --instance-ids <id> --region ap-south-1
aws ec2 delete-security-group --group-id <sg-id> --region ap-south-1
aws iam remove-role-from-instance-profile --instance-profile-name amc-demo-ec2-profile --role-name amc-demo-ec2-role
aws iam delete-instance-profile --instance-profile-name amc-demo-ec2-profile
aws iam delete-role-policy --role-name amc-demo-ec2-role --policy-name secret-read
aws iam delete-role --role-name amc-demo-ec2-role
```

## Not included yet (demo scope)
- **nginx/TLS** — API is served on `:8000` over HTTP. Add nginx + Let's Encrypt (needs a domain) for HTTPS.
- **S3 + CloudFront frontend** — build `frontend/` and `aws s3 sync` to a bucket, then front with CloudFront. Set the frontend's API base to `http://<IP>:8000`.
