# Evaluation — Spaghetti Sentinel

Scores the real agent loop (`run_agent`, in-process) against ground-truth
labels. Behaviour, not speed (latency/throughput/cost live in `bench/`).

## Command

```bash
S3_BUCKET= python eval/run_eval.py --out eval/results
python eval/run_eval.py --only failure-pauses-and-asks --out /tmp/eval-one
python eval/run_eval.py --strict   # exit 1 when any non-skipped case fails
```

## Axes → rubric

| Axis | Rubric |
|---|---|
| `task_effectiveness` (4 cases) | Agentic Vision 20% "Task effectiveness" |
| `failure_handling` (3 cases) | Agentic 15% "Failure handling, observability, security, human control" |
| `observability` (3 derived checks) | same 15% axis |
| `human_control` (1 case) | same 15% axis |

## Injections

| name | patches | proves |
|---|---|---|
| `degrade_every_frame` | `app.vision.pipeline.analyze_frame` → degraded scores | silence, not guessing |
| `raise_at_frame_30` | same symbol → raises once at frame 30 | crash ≠ run death |
| `evidence_write_fails` | `EvidenceStore._put_bytes` → degraded result | alert survives vault loss |
| `approver_never_answers` | `APPROVAL_TIMEOUT_S` → 1.0 s | timeout recorded, run ends |

Patch-target note: injections patch `app.vision.pipeline.analyze_frame` — the
*defining* module. `app/agent/tools.py` calls it through the module
(`from app.vision import pipeline; pipeline.analyze_frame(...)`), so the patch
takes effect regardless of import style. If a refactor changes this, the
`evidence-store-unavailable` case (which asserts `evidence_uris == 0`) fails
first, proving the patch missed.

## Case changes

_None. No `expect` block has been weakened to make a case pass._
