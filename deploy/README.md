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
| S3 bucket `amc-demo-corpus-<account-id>` | corpus documents (created if missing) | free (< 5 GB) |
| IAM role + instance profile | `secretsmanager:GetSecretValue` on the secret + `s3:GetObject`/`ListBucket` on the corpus bucket + `logs:PutLogEvents`/`CreateLogStream`/`DescribeLogStreams` on the log group | free |
| CloudWatch log group `/amc-demo/app` | all 4 containers ship logs here via the `awslogs` Docker driver (one stream per service), 14-day retention | free-ish (< 5 GB/mo) |
| EC2 `t3.medium` + 30 GB gp3 | runs the stack (t3.micro's 1GB OOMs under the ML stack — tested) | ~$0.05/hr — stop when idle |
| Elastic IP | stable address across stop/start | free while attached |
| Secrets Manager secret (already exists) | `/dev/microsoft-app-id`, JSON field `ANTHROPIC_API_KEY` | free-ish |
| Cron on the instance | reindexes the S3 corpus bucket every 15 min (see below) | free |

## Steps

```bash
# 0. Authenticated? (secret already lives in Secrets Manager, ap-south-1)
aws sts get-caller-identity

# 1. Deploy (creates all of the above, copies code, starts the stack, installs the reindex cron):
bash deploy/deploy.sh
#    Override defaults if needed:
#    REGION=ap-south-1 SECRET_ID=/dev/microsoft-app-id CORPUS_BUCKET=my-bucket bash deploy/deploy.sh
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

## Logs

All 4 services (`api`, `streamlit`, `neo4j`, `redis`) ship stdout/stderr to
CloudWatch Logs via the `awslogs` Docker logging driver — see the `logging:`
block on each service in `docker-compose.yml`. Tail a service live:

```bash
aws logs tail /amc-demo/app --log-stream-names api --follow --region ap-south-1
# or: streamlit / neo4j / redis
```

## Requirements on your machine
- `aws` CLI v2, authenticated
- `ssh` + `tar` (Git Bash on Windows has both; rsync often isn't present, so the script uses tar-over-SSH instead)

## Teardown (avoid charges)
```bash
# Stop (keeps EBS + data + Elastic IP association, ~$2.40/mo after free tier):
aws ec2 stop-instances --instance-ids <id> --region ap-south-1

# OR fully delete everything (an unattached Elastic IP is billed, so release it):
aws ec2 terminate-instances --instance-ids <id> --region ap-south-1
aws ec2 wait instance-terminated --instance-ids <id> --region ap-south-1
aws ec2 release-address --allocation-id <alloc-id> --region ap-south-1  # find via: aws ec2 describe-addresses
aws ec2 delete-security-group --group-id <sg-id> --region ap-south-1
aws iam remove-role-from-instance-profile --instance-profile-name amc-demo-ec2-profile --role-name amc-demo-ec2-role
aws iam delete-instance-profile --instance-profile-name amc-demo-ec2-profile
aws iam delete-role-policy --role-name amc-demo-ec2-role --policy-name secret-read
aws iam delete-role-policy --role-name amc-demo-ec2-role --policy-name s3-corpus-read
aws iam delete-role-policy --role-name amc-demo-ec2-role --policy-name cloudwatch-logs
aws iam delete-role --role-name amc-demo-ec2-role
aws logs delete-log-group --log-group-name /amc-demo/app --region ap-south-1
# S3 bucket is NOT deleted automatically — empty + remove it yourself if truly done:
# aws s3 rb s3://amc-demo-corpus-<account-id> --force
```

## Not included yet (demo scope)
- **nginx/TLS** — API (`:8000`) and Streamlit UI (`:8501`) are served over plain HTTP. Add nginx + Let's Encrypt (needs a domain) for HTTPS.
