#!/bin/bash
# One-command deploy to AWS Graviton. Writes deploy/deployment-record.json.
# Usage: bash deploy/deploy_ec2.sh [--instance-type c7g.xlarge] [--region <r>]
#                                  [--bucket <name>] [--key-name <kp>]
#                                  [--reuse-instance <id>] [--dry-run] [--allow-non-graviton]
set -euo pipefail

TYPE="c7g.xlarge"
REGION="${AWS_REGION:-us-east-1}"
BUCKET=""
KEY_NAME=""
REUSE=""
DRY_RUN="0"
ALLOW_NON_GRAVITON="0"
MODEL="${BEDROCK_MODEL_ID:-anthropic.claude-3-5-haiku-20241022-v1:0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --instance-type) TYPE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --bucket) BUCKET="$2"; shift 2 ;;
    --key-name) KEY_NAME="$2"; shift 2 ;;
    --reuse-instance) REUSE="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --allow-non-graviton) ALLOW_NON_GRAVITON="1"; shift ;;
    *) echo "unknown flag $1" >&2; exit 2 ;;
  esac
done

case "$TYPE" in
  c7g*|m7g*|r7g*|c8g*|t4g*) ;;   # Graviton/Arm families (t4g is burstable Graviton)
  *)
    if [ "$ALLOW_NON_GRAVITON" != "1" ]; then
      echo "deploy: ${TYPE} is not a Graviton family — the COOL award requires the Arm path" >&2
      exit 2
    fi
    ;;
esac

if [ "$DRY_RUN" = "1" ]; then
  echo "dry-run plan:"
  echo "  instance-type: ${TYPE} (region ${REGION})"
  echo "  bucket: ${BUCKET:-spaghetti-sentinel-evidence-<account>}"
  echo "  reuse-instance: ${REUSE:-<new instance>}"
  echo "  image: built by deploy/build_and_push.sh, run on port 80 -> 8000"
  echo "  record: deploy/deployment-record.json (written only when healthy)"
  exit 0
fi

BUILD_OUT="$(bash deploy/build_and_push.sh --region "$REGION")"
BUILD_MARKER="$(echo "$BUILD_OUT" | grep '^BUILD_MARKER=' | cut -d= -f2)"
IMAGE_URI="$(echo "$BUILD_OUT" | grep '^IMAGE_URI=' | cut -d= -f2)"
IMAGE_DIGEST="$(echo "$BUILD_OUT" | grep '^IMAGE_DIGEST=' | cut -d= -f2)"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
if [ -z "$BUCKET" ]; then
  BUCKET="spaghetti-sentinel-evidence-${ACCOUNT}"
fi
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
fi
# 7-day lifecycle on runs/ (blueprint risk R6) + block public access.
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration '{
  "Rules": [{"ID": "expire-runs", "Status": "Enabled",
             "Filter": {"Prefix": "runs/"},
             "Expiration": {"Days": 7}}]}' --region "$REGION" || true
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --region "$REGION" || true

AMI="$(aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --query 'Parameters[0].Value' --output text --region "$REGION")"
AMI_NAME="al2023-arm64 (SSM-resolved)"

SG_ID="$(aws ec2 describe-security-groups --region "$REGION" \
  --filters Name=group-name,Values=spaghetti-sentinel \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"
if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  VPC_ID="$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' --output text)"
  SG_ID="$(aws ec2 create-security-group --group-name spaghetti-sentinel \
    --description "Spaghetti Sentinel judge access" --vpc-id "$VPC_ID" \
    --region "$REGION" --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp \
    --port 80 --cidr 0.0.0.0/0 --region "$REGION"
  MY_IP="$(curl -fsS --max-time 8 https://checkip.amazonaws.com || echo "")"
  if [ -n "$MY_IP" ]; then
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp \
      --port 22 --cidr "${MY_IP}/32" --region "$REGION" || true
  fi
  aws ec2 authorize-security-group-egress --group-id "$SG_ID" --protocol -1 \
    --port -1 --cidr 0.0.0.0/0 --region "$REGION" || true
fi

# Host identity: the instance needs an IAM role or SSM, ECR pull, the
# awslogs driver and evidence/rationale calls all fail. (IAM is global.)
ROLE_NAME="spaghetti-sentinel-host"
PROFILE_NEW="0"
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  PROFILE_NEW="1"
fi
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name spaghetti-sentinel-host \
  --policy-document file://deploy/iam-policy.json
if ! aws iam get-instance-profile --instance-profile-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$ROLE_NAME" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE_NAME" \
    --role-name "$ROLE_NAME"
  PROFILE_NEW="1"
fi
if [ "$PROFILE_NEW" = "1" ]; then
  echo "deploy: waiting for the new instance profile to propagate..." >&2
  sleep 15
fi

if [ -n "$REUSE" ]; then
  INSTANCE_ID="$REUSE"
  aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null || true
else
  KEY_ARGS=""
  if [ -n "$KEY_NAME" ]; then KEY_ARGS="--key-name $KEY_NAME"; fi
  INSTANCE_ID="$(aws ec2 run-instances --instance-type "$TYPE" --image-id "$AMI" \
    --security-group-ids "$SG_ID" --iam-instance-profile Name="$ROLE_NAME" \
    --user-data file://deploy/user-data.sh \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=spaghetti-sentinel}]' \
    $KEY_ARGS --region "$REGION" --query 'Instances[0].InstanceId' --output text)"
fi
aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID" --region "$REGION"
DNS="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)"
URL="http://${DNS}"

REMOTE="docker pull \"$IMAGE_URI\"; docker rm -f spaghetti-sentinel || true; docker run -d --name spaghetti-sentinel --restart unless-stopped -p 80:8000 -e AWS_REGION=\"$REGION\" -e S3_BUCKET=\"$BUCKET\" -e BUILD_MARKER=\"$BUILD_MARKER\" -e SS_BACKEND=cool -e BEDROCK_MODEL_ID=\"$MODEL\" --log-driver=awslogs --log-opt awslogs-region=\"$REGION\" --log-opt awslogs-group=/spaghetti-sentinel \"$IMAGE_URI\""
if aws ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
    --parameters commands="$REMOTE" --region "$REGION" >/dev/null 2>&1; then
  echo "deploy: container started over SSM"
else
  echo "deploy: SSM unavailable — run over SSH:" >&2
  # shellcheck disable=SC2001
  echo "$REMOTE" | sed 's/^/  /' >&2
  exit 1
fi

if ! bash deploy/healthcheck.sh --url "$URL" --marker "$BUILD_MARKER" --retries 20 --interval 10; then
  echo "deploy: unhealthy — last 50 container log lines:" >&2
  aws ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
    --parameters commands="docker logs --tail 50 spaghetti-sentinel" \
    --region "$REGION" >/dev/null || true
  exit 1
fi

VERSIONS="$(aws ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
  --parameters commands="docker exec spaghetti-sentinel python3.11 -c \"import cv2, json; from app.vision.backend import cool_version; print(json.dumps({'opencv': cv2.__version__, 'cool': cool_version()}))\"" \
  --region "$REGION" --query 'Command.CommandId' --output text)"
sleep 10
VERSIONS_OUT="$(aws ssm get-command-invocation --command-id "$VERSIONS" --instance-id "$INSTANCE_ID" \
  --region "$REGION" --query StandardOutputContent --output text)"
OPENCV_VER="$(echo "$VERSIONS_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('opencv',''))")"
COOL_VER="$(echo "$VERSIONS_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cool') or '')")"
COOL_INSTALLED="false"
if [ -n "$COOL_VER" ] && [ "$COOL_VER" != "None" ]; then COOL_INSTALLED="true"; fi

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - "$URL" "$BUILD_MARKER" "$NOW" "$REGION" "$INSTANCE_ID" "$TYPE" "$AMI" "$AMI_NAME" \
  "$IMAGE_URI" "$IMAGE_DIGEST" "$OPENCV_VER" "$COOL_VER" "$COOL_INSTALLED" "$BUCKET" <<'PY'
import json, sys
url, marker, now, region, iid, itype, ami, ami_name, uri, digest, ocv, cool, cool_inst, bucket = sys.argv[1:13]
record = {
  "schema": "spaghetti-sentinel-deployment/1.0.0",
  "url": url, "health_url": url + "/healthz",
  "build_marker": marker, "deployed_at": now, "region": region,
  "instance_id": iid, "instance_type": itype, "arch": "aarch64",
  "ami_id": ami, "ami_name": ami_name,
  "image_uri": uri, "image_digest": digest,
  "opencv_version": ocv, "cool_version": cool or None,
  "cool_installed": cool_inst == "true",
  "s3_bucket": bucket,
  "probe": {"status": 200, "marker_matched": True, "probed_at": now},
  "deploy_owner": "DP-DEPLOY",
  "redeploy_command": "bash deploy/deploy_ec2.sh",
}
open("deploy/deployment-record.json", "w").write(json.dumps(record, indent=2) + "\n")
PY

echo "$URL"
