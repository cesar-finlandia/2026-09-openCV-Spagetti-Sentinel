# COOL build artefact (gitignored, never committed)

The Cloud-Optimized OpenCV Library wheel for `aarch64` goes in this directory
before running `deploy/build_and_push.sh`. The Dockerfile installs any
`*.whl` found here; when the directory only holds this README and `.gitkeep`,
the image builds baseline-only and the app reports `cool_available: false`.

1. Subscribe to Cloud-Optimized OpenCV Library on AWS Marketplace
   (`https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs`).
2. Obtain the `aarch64` Python wheel for the subscribed version.
3. Place it in `deploy/cool/` (this folder; `*.whl` is gitignored).
4. Re-run `deploy/build_and_push.sh`.
5. Confirm with `curl -s <url>/healthz | python3 -m json.tool` that
   `cool_version` is non-null.
