# syntax=docker/dockerfile:1.7
# Spaghetti Sentinel — linux/arm64 image for AWS Graviton (REQ-N06).
# Stage 1 builds the UI; stage 2 is the runtime with OpenCV 5 + COOL on the Arm path.

FROM --platform=$BUILDPLATFORM node:20.18.1-bookworm-slim AS ui
WORKDIR /ui
COPY web/package.json web/pnpm-lock.yaml* ./web/
COPY src ./src
COPY app/contracts/steps.json ./app/contracts/steps.json
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm --dir web install --frozen-lockfile
COPY web ./web
RUN pnpm --dir web build

FROM arm64v8/amazonlinux:2023 AS runtime
ARG COOL_VERSION=""
ARG BUILD_MARKER="dev"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BUILD_MARKER=${BUILD_MARKER}

RUN dnf -y update && dnf -y install python3.11 python3.11-pip tar gzip which \
    mesa-libGL libglvnd-glx && dnf clean all

WORKDIR /srv
COPY requirements.lock.txt ./
RUN python3.11 -m pip install --no-cache-dir -r requirements.lock.txt

# COOL — the Cloud-Optimized OpenCV Library, from the AWS Marketplace artefact mounted at
# build time. The image builds WITHOUT it (cool_available() then returns False and the app
# runs on the baseline backend), so a missing COOL is a degraded deploy, never a failed build.
COPY deploy/cool/ /tmp/cool/
RUN if [ -n "$(ls -A /tmp/cool 2>/dev/null)" ]; then \
      python3.11 -m pip install --no-cache-dir /tmp/cool/*.whl && echo "COOL installed"; \
    else echo "COOL artefact absent — building baseline-only image"; fi \
    && rm -rf /tmp/cool

COPY app ./app
COPY src ./src
COPY contracts ./contracts
COPY fixtures ./fixtures
COPY bench ./bench
COPY eval ./eval
COPY --from=ui /ui/web/dist ./web/dist
RUN echo "${BUILD_MARKER}" > /srv/build-marker.txt

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3.11 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

CMD ["python3.11", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
