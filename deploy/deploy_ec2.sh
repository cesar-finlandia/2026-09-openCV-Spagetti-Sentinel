#!/bin/bash
# One-command deploy to AWS Graviton. Writes deploy/deployment-record.json.
# Usage: bash deploy/deploy_ec2.sh [--instance-type c7g.xlarge] [--region <r>]
#                                  [--bucket <name>] [--key-name <kp>]
#                                  [--reuse-instance <id>] [--dry-run] [--allow-non-graviton]
#                                  [--skip-build] [--marker <m>] [--image-uri <u>] [--image-digest <d>]
set -euo pipefail
# Git Bash (MINGW/MSYS2) rewrites `/aws/...` args to `C:/Program Files/Git/aws/...`,
# which breaks the SSM public-parameter AMI lookup. Disable path conversion.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"

TYPE="c7g.xlarge"
REGION="${AWS_REGION:-us-east-1}"
BUCKET=""
KEY_NAME=""
REUSE=""
DRY_RUN="0"
ALLOW_NON_GRAVITON="0"
SKIP_BUILD="0"
FLAG_MARKER=""
FLAG_IMAGE_URI=""
FLAG_IMAGE_DIGEST=""
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
    --skip-build) SKIP_BUILD="1"; shift ;;
    --marker) FLAG_MARKER="$2"; shift 2 ;;
    --image-uri) FLAG_IMAGE_URI="$2"; shift 2 ;;
    --image-digest) FLAG_IMAGE_DIGEST="$2"; shift 2 ;;
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
  echo "  skip-build: ${SKIP_BUILD} marker=${FLAG_MARKER:-<from build-marker.txt>} image=${FLAG_IMAGE_URI:-<from ECR>}"
  echo "  image: built by deploy/build_and_push.sh (skipped when --skip-build), run on port 80 -> 8000"
  echo "  record: deploy/deployment-record.json (written only when healthy)"
  exit 0
fi

if [ "$SKIP_BUILD" = "1" ]; then
  echo "deploy: skipping build, reusing existing image..." >&2
  BUILD_MARKER="${FLAG_MARKER:-$(head -1 build-marker.txt 2>/dev/null || echo "")}"
  ACCOUNT="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
  IMAGE_URI="${FLAG_IMAGE_URI:-${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/spaghetti-sentinel:${BUILD_MARKER}}"
  if [ -n "${FLAG_IMAGE_DIGEST:-}" ]; then
    IMAGE_DIGEST="$FLAG_IMAGE_DIGEST"
  else
    IMAGE_DIGEST="$(aws ecr describe-images --repository-name spaghetti-sentinel \
      --image-ids imageTag="$BUILD_MARKER" --region "$REGION" \
      --query 'imageDetails[0].imageDigest' --output text 2>/dev/null || echo "")"
  fi
else
  echo "deploy: building image (this takes ~10min)..." >&2
  BUILD_OUT="$(bash deploy/build_and_push.sh --region "$REGION")"
  echo "$BUILD_OUT" >&2
  # NOTE: grep returns 1 on no-match; with `set -o pipefail` that would abort
  # silently. Temporarily disable pipefail for parsing.
  set +o pipefail
  # buildx progress wraps the VAR= echo lines with \r redraws and ANSI escapes
  # (the terminal renders them invisibly, so the lines *look* clean while
  # ^-anchored grep misses them — observed: marker empty while uri/digest
  # parsed). Sanitize, then match unanchored and take the first hit.
  BUILD_OUT_CLEAN="$(echo "$BUILD_OUT" | tr -d '\r' | sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g')"
  BUILD_MARKER="$(echo "$BUILD_OUT_CLEAN" | grep -o 'BUILD_MARKER=[A-Za-z0-9._-]*' | head -1 | cut -d= -f2 || true)"
  IMAGE_URI="$(echo "$BUILD_OUT_CLEAN" | grep -o 'IMAGE_URI=[^[:space:]]*' | head -1 | cut -d= -f2 || true)"
  IMAGE_DIGEST="$(echo "$BUILD_OUT_CLEAN" | grep -o 'IMAGE_DIGEST=[^[:space:]]*' | head -1 | cut -d= -f2 || true)"
  set -o pipefail
fi
if [ -z "${BUILD_MARKER:-}" ] || [ -z "${IMAGE_URI:-}" ] || [ -z "${IMAGE_DIGEST:-}" ] || [ "$IMAGE_DIGEST" = "None" ]; then
  echo "deploy: build output missing marker/uri/digest (marker='${BUILD_MARKER:-}' uri='${IMAGE_URI:-}' digest='${IMAGE_DIGEST:-}')" >&2
  DUMP="${TMPDIR:-/tmp}/spaghetti-build-out-failed.log"
  printf '%s' "$BUILD_OUT" > "$DUMP"
  echo "deploy: raw build output saved to $DUMP (inspect the BUILD_MARKER= line bytes)" >&2
  exit 1
fi
echo "deploy: marker=${BUILD_MARKER} image=${IMAGE_URI} digest=${IMAGE_DIGEST}" >&2

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
if [ -z "$AMI" ] || [ "$AMI" = "None" ] || [ "$AMI" = "null" ]; then
  echo "deploy: AMI lookup returned '$AMI' — if running under Git Bash, retry with MSYS_NO_PATHCONV=1" >&2
  exit 1
fi

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

# AWS CLI v2 shorthand `--parameters commands="..."` chokes on embedded double
# quotes (ParamValidation: Expected ',' received '"'). Always send JSON instead.
ssm_send() {
  local _iid="$1"; shift
  local _cmd="$1"; shift
  local _payload
  _payload="$(python3 -c "import json,sys; print(json.dumps({'commands':[sys.argv[1]]}))" "$_cmd")"
  aws ssm send-command --instance-ids "$_iid" --document-name AWS-RunShellScript \
    --parameters "$_payload" --region "$REGION" "$@"
}

REMOTE="aws ecr get-login-password --region \"$REGION\" | docker login --username AWS --password-stdin \"${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com\"; docker pull \"$IMAGE_URI\"; docker rm -f spaghetti-sentinel || true; docker run -d --name spaghetti-sentinel --restart unless-stopped -p 80:8000 -e AWS_REGION=\"$REGION\" -e S3_BUCKET=\"$BUCKET\" -e BUILD_MARKER=\"$BUILD_MARKER\" -e SS_BACKEND=cool -e BEDROCK_MODEL_ID=\"$MODEL\" \"$IMAGE_URI\""
echo "deploy: waiting for SSM PingStatus=Online on ${INSTANCE_ID} (up to 5min)..." >&2
for _i in $(seq 1 10); do
  PING="$(aws ssm describe-instance-information --filters Key=InstanceIds,Values="$INSTANCE_ID" \
    --region "$REGION" --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || echo "")"
  echo "deploy: SSM ping=${PING:-unknown} (${_i}/10)" >&2
  if [ "$PING" = "Online" ]; then break; fi
  sleep 30
done
echo "deploy: sending container start over SSM..." >&2
SSM_OK="0"
for _i in $(seq 1 5); do
  if ssm_send "$INSTANCE_ID" "$REMOTE"; then
    SSM_OK="1"
    break
  fi
  echo "deploy: SSM send failed (${_i}/5), retrying in 30s..." >&2
  sleep 30
done
if [ "$SSM_OK" = "1" ]; then
  echo "deploy: container started over SSM"
else
  echo "deploy: SSM unavailable after 10 retries — last error above; run over SSH:" >&2
  # shellcheck disable=SC2001
  echo "$REMOTE" | sed 's/^/  /' >&2
  exit 1
fi

if ! bash deploy/healthcheck.sh --url "$URL" --marker "$BUILD_MARKER" --retries 20 --interval 10; then
  echo "deploy: unhealthy — last 50 container log lines:" >&2
  ssm_send "$INSTANCE_ID" "docker logs --tail 50 spaghetti-sentinel" >/dev/null || true
  exit 1
fi

VERSIONS="$(ssm_send "$INSTANCE_ID" \
  "docker exec spaghetti-sentinel python3.11 -c \"import cv2, json; from app.vision.backend import cool_version; print(json.dumps({'opencv': cv2.__version__, 'cool': cool_version()}))\"" \
  --query 'Command.CommandId' --output text)"
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
url, marker, now, region, iid, itype, ami, ami_name, uri, digest, ocv, cool, cool_inst, bucket = sys.argv[1:15]
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
