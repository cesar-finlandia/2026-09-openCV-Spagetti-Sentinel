# Spaghetti Sentinel

Spaghetti Sentinel watches a 3D print over video and asks a human to pause it
when the print is failing.

## Who it is for

Maya is a solo desktop tinkerer running multi-hour prints in her apartment.
She needs a 60-second setup, a phone-visible status, and a pause
recommendation she can trust — not another dashboard to babysit.

## What it does

- OpenCV 5 analysis of the print bed (resize, gradients, background
  subtraction, morphology, contours) producing a deterministic spaghetti-risk
  score per sampled frame.
- A deterministic policy: the same vision JSON always yields the same action.
- An agent loop (perception → decision → action) that changes its action on
  the vision result, exposed as four MCP-style tools.
- Human approval before any pause recommendation; the system never touches
  the printer.
- Evidence (clip, still frame, measurement JSON) saved to Amazon S3 with a
  local-disk fallback.

## Live demo

Public URL (after `bash deploy/deploy_ec2.sh`): see
`deploy/deployment-record.json`, field `url`.

Pick the `spaghetti` fixture and press Start.

Local demo with no AWS account:

```bash
docker compose up            # then open http://localhost:8000
```

## Tracks

Best Use of COOL Award (primary) and Agentic Vision Award (secondary).

## Stack

OpenCV 5, COOL on AWS Graviton (`c7g.xlarge`, `aarch64`), Amazon S3, Amazon
Bedrock (rationale text only), FastAPI, React.

## Run it locally (no AWS account needed)

```bash
docker compose up            # then open http://localhost:8000
```

From source:

```bash
pip install -r requirements.lock.txt
python -c "from app.fixtures import generate_fixtures, seed; generate_fixtures(); seed()"
pnpm --dir web build
uvicorn app.api.main:app --port 8000
```

## Run the tests

```bash
python -m pytest -q
pnpm --dir web test
```

## Reproduce the measurements

Benchmark (needs the Graviton host for authoritative numbers):

```bash
python bench/run_bench.py --clips good-first-layer,stringing,spaghetti,lighting-shift \
    --repeats 5 --warmup 2 --backends cool,baseline \
    --deployment-record deploy/deployment-record.json --out bench/results
```

Evaluation (runs anywhere, no AWS credentials):

```bash
S3_BUCKET= python eval/run_eval.py --out eval/results
```

Latest committed results: evaluation 9/9 cases passed (1 skipped — no real
footage present); threshold-flip property `capture_evidence ->
request_pause_approval` on a 0.02 score delta; failure-clip detection latency
18 frames (0.6 s). Full tables: `eval/results/eval-report.md`,
`bench/results/cool-vs-baseline.md` (currently a non-authoritative local
report; the authoritative Graviton run overwrites it).

## Deploy it yourself

One line: `bash deploy/deploy_ec2.sh`. Details in `deploy/README.md`.

## Responsible use

This system recommends; it never controls the printer. It cannot pause, stop
or modify a print. A pause recommendation is shown to a person, who decides.

## Licence

MIT — see `LICENSE`.

## Documents

- `docs/technical-report.md`
- `docs/architecture.png`
- `docs/addendum-agentic.md`
- `docs/addendum-cool.md` (written after the authoritative Graviton run;
  not present until `cool_installed` is true)
- `disclosure.md`
- `eval/results/eval-report.md`
- `bench/results/cool-vs-baseline.md`
