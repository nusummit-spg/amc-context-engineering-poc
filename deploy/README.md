# Deploy — AWS free-tier (single EC2)

Deploys the whole stack (FastAPI + Neo4j + Redis + Streamlit UI via Docker
Compose) to one EC2 instance (t3.medium — the FAISS/GLiNER/sentence-transformer
stack in `backend/app/engine` needs more than t3.micro's 1GB). Code is copied
over SSH (no GitHub creds on the box). Region defaults to **ap-south-1**.

## What gets created
| Resource | Notes | Cost |
|---|---|---|
| Key pair `amc-demo-key` | Private key saved to `~/.ssh/amc-demo-key.pem` | free |
| Security group `amc-demo-sg` | SSH from your IP only; 80/443/8000/8501 open | free |
| IAM role + instance profile | `secretsmanager:GetSecretValue` on the secret + `s3:GetObject`/`ListBucket` on the corpus bucket | free |
| EC2 `t3.medium` + 30 GB gp3 | runs the stack | ~$0.05/hr — stop when idle |
| Secrets Manager secret (already exists) | `/dev/microsoft-app-id`, JSON field `ANTHROPIC_API_KEY` | free-ish |
| Cron on the instance | reindexes the S3 corpus bucket every 15 min (see below) | free |

## Steps

```bash
# 0. Authenticated? (secret already lives in Secrets Manager, ap-south-1)
aws sts get-caller-identity

# 1. Deploy (creates infra, copies code, starts the stack, installs the reindex cron):
CORPUS_BUCKET=amc-demo-corpus-<account-id> bash deploy/deploy.sh
#    Override other defaults if needed:
#    REGION=ap-south-1 SECRET_ID=/dev/microsoft-app-id bash deploy/deploy.sh
```

API docs land at `http://<IP>:8000/docs`, Streamlit UI at `http://<IP>:8501`.

## Corpus / reindexing

Drop new source documents into `s3://<corpus-bucket>/raw/` — a cron job on the
instance (`*/15 * * * *`, `flock`-guarded against overlap) runs
`app.engine.reindex_from_s3` automatically: syncs new/changed files, then
indexes only what isn't already in the FAISS/Neo4j cache (already-indexed
files are skipped for free — no LLM cost). Log: `/home/ec2-user/reindex.log`
(rotated weekly). To reindex immediately instead of waiting for cron:

```bash
ssh -i ~/.ssh/amc-demo-key.pem ec2-user@<IP> \
  'cd app && docker compose exec -T api python -m app.engine.reindex_from_s3'
```

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
- **nginx/TLS** — API (`:8000`) and Streamlit UI (`:8501`) are served over plain HTTP. Add nginx + Let's Encrypt (needs a domain) for HTTPS.
