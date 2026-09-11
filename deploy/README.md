# Deploy — Spaghetti Sentinel on AWS Graviton

## Prerequisites

- AWS account with the compute grant and/or Free Tier credits.
- AWS CLI v2 installed and authenticated (`aws sts get-caller-identity` works).
- `docker` with `buildx` on the operator machine.
- Region: `us-east-1` unless `--region` is passed everywhere.
- Track the grant's second-half check-in window (2026-09-21 → 2026-10-02).

## Get COOL

1. Subscribe to Cloud-Optimized OpenCV Library on AWS Marketplace
   (`https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs`).
2. Obtain the `aarch64` Python wheel for the subscribed version.
3. Place it in `deploy/cool/` (a gitignored directory; see
   `deploy/cool/README.md`).
4. Re-run `deploy/build_and_push.sh`.
5. Confirm with `curl -s <url>/healthz | python3 -m json.tool` that
   `cool_version` is non-null.

Without the wheel the image builds baseline-only (`cool_installed: false`)
and the COOL track cannot be evidenced (blueprint risk R1).

## One-command deploy

```bash
bash deploy/deploy_ec2.sh
```

It creates: an ECR repo, an S3 evidence bucket (7-day `runs/` lifecycle,
public access blocked), a least-privilege IAM role (`deploy/iam-policy.json`),
a security group (TCP 80 world, TCP 22 operator `/32` only), and a
`c7g.xlarge` instance that pulls and runs the image.

## Verify

```bash
bash deploy/healthcheck.sh --url <url> --marker "$(head -1 build-marker.txt)"
```

## Re-deploy

Re-run the same command; pass `--reuse-instance <id>` to keep the host.
Never re-deploy between recording the video and submission without
re-checking the marker.

## Cost control

- `aws ec2 stop-instances --instance-ids <id>` between sessions; start again
  and re-run `healthcheck.sh`.
- S3 `runs/` objects expire after 7 days by lifecycle rule.
- The demo run writes at most a handful of objects.
- Watch the grant's second-half check-in (2026-09-21 → 2026-10-02).

## Local, no-AWS path

```bash
docker compose up
```

Then open `http://localhost:8000` — replay mode on the baseline backend, no
AWS account needed.

## Deviation note

The chassis `src/platform/deploy/**` adapters target Vercel/Replit/Streamlit
and Docker-for-web. They cannot place a `linux/arm64` OpenCV+COOL image on a
Graviton EC2 instance, which the COOL track requires — so this plan ships its
own `Dockerfile` and scripts and does not use them.

## Teardown

```bash
aws ec2 terminate-instances --instance-ids <id>
aws ecr batch-delete-image --repository-name spaghetti-sentinel --image-ids imageTag=<marker>
aws s3 rb s3://<bucket> --force
aws ec2 delete-security-group --group-name spaghetti-sentinel
```
