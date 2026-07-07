#!/usr/bin/env bash
# Build + push the parser Lambda image, create/update the function, and wire the
# S3 ObjectCreated trigger on the corpus bucket. Run from the repo root:
#   bash deploy/lambda/deploy-lambda.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash: stop mangling ARNs / AWS names

REGION="${REGION:-ap-south-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
FUNC="${FUNC:-amc-demo-parser}"
REPO="amc-demo-parser"
ECR="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO"
TAG="$(date +%Y%m%d%H%M%S)"
BUCKET="$(aws ssm get-parameter --name /amc-demo/corpus-bucket --query Parameter.Value --output text --region "$REGION")"
ROLE_NAME="$FUNC-role"

echo ">> Account=$ACCOUNT Region=$REGION Bucket=$BUCKET"

# 1. Build + push image (linux/amd64 for Lambda)
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker build --platform linux/amd64 -f deploy/lambda/Dockerfile -t "$ECR:$TAG" .
docker push "$ECR:$TAG"

# 2. Execution role (S3 read/write on the corpus bucket + logs)
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole >/dev/null
  aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name s3-corpus \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::$BUCKET/*\"}]}" >/dev/null
  sleep 10
fi
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)"

# 3. Create or update the function
if aws lambda get-function --function-name "$FUNC" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNC" --image-uri "$ECR:$TAG" --region "$REGION" >/dev/null
else
  aws lambda create-function --function-name "$FUNC" \
    --package-type Image --code ImageUri="$ECR:$TAG" \
    --role "$ROLE_ARN" --timeout 120 --memory-size 1024 \
    --region "$REGION" >/dev/null
fi
aws lambda wait function-updated --function-name "$FUNC" --region "$REGION"

# 4. Allow S3 to invoke, then wire the ObjectCreated trigger (raw/ prefix)
aws lambda add-permission --function-name "$FUNC" --statement-id s3invoke \
  --action lambda:InvokeFunction --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::$BUCKET" --source-account "$ACCOUNT" \
  --region "$REGION" >/dev/null 2>&1 || true
FUNC_ARN="$(aws lambda get-function --function-name "$FUNC" --query Configuration.FunctionArn --output text --region "$REGION")"
aws s3api put-bucket-notification-configuration --bucket "$BUCKET" --region "$REGION" \
  --notification-configuration "{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"$FUNC_ARN\",\"Events\":[\"s3:ObjectCreated:*\"],\"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"raw/\"}]}}}]}"

echo ">> Done. Upload a file to s3://$BUCKET/raw/ to trigger parsing; output lands in processed/."
