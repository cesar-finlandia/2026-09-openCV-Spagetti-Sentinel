# COOL vs baseline benchmark

Reproducible apples-to-apples comparison of the DP-VISION pipeline over the
same fixture clips on the same host, once with COOL and once with stock
OpenCV 5.

## Reproduce

Authoritative (on the DP-DEPLOY `c7g.xlarge` instance, inside the container):

```bash
python bench/run_bench.py --clips good-first-layer,stringing,spaghetti,lighting-shift \
    --repeats 5 --warmup 2 --backends cool,baseline \
    --deployment-record deploy/deployment-record.json --out bench/results
```

Local, non-authoritative (any machine):

```bash
python bench/run_bench.py --clips good-first-layer,spaghetti \
    --repeats 2 --warmup 1 --allow-non-graviton --out bench/results
```

## Why the backends alternate

Measured passes run `cool, baseline, cool, baseline, …` per repeat — never all
of one then all of the other — so thermal drift and CPU frequency scaling hit
both backends equally.

## What `authoritative` means

`true` only when the host is `aarch64` AND a COOL build was detected. Anything
else is `false` with a note explaining why; a non-authoritative report must
never be quoted in `docs/addendum-cool.md`.

## What `core_workload_share_pct` measures

The share of per-frame pipeline time spent inside COOL-accelerated
operations — the rubric's "Evidence that COOL executes the claimed core
workload". It is measured (from `accelerated_ops` × per-op timings), not
asserted.

## Cost

The USD column is MODELLED from published us-east-1 on-demand list prices,
not from a measured bill. Every rendering carries the word MODELLED.

## Do not commit a local report as the submission artefact

WU-04 overwrites `bench/results/` with the authoritative Graviton run. A local
`--allow-non-graviton` report is provisional.

## Result on record

_Pending the authoritative Graviton run (DP-COOL-BENCH WU-04). This section is
filled in when `bench/results/cool-vs-baseline.json` reports
`"authoritative": true`._
