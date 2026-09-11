# COOL vs baseline — Spaghetti Sentinel

**NON-AUTHORITATIVE: non-Graviton host (AMD64); report is non-authoritative; COOL build not present on this host; both columns are stock OpenCV 5 and no COOL claim is supported**

## How to reproduce

Command: `bench/run_bench.py --clips good-first-layer,spaghetti --repeats 2 --warmup 1 --allow-non-graviton --out bench/results`
Image digest: `None`
Instance type: `None`
Clips: `good-first-layer, spaghetti` with sha256s:
- good-first-layer: `4d00fe4e57c5a1179bc9570ecc0143a08049c6950e3b2a51f47eac65060f6ed8`
- spaghetti: `95c20105e628fac8b27fa86c9243aaa146114b0b10351cc6ddb80abf3947f1da`
Repeats: 2, warmup: 1. Backends alternate per repeat so thermal drift hits both equally.

## Host and versions

| fact | value |
|---|---|
| label | Windows-10-10.0.19045-SP0 |
| arch | AMD64 |
| cpu_count | 12 |
| instance_type | None |
| ami_id | None |
| image_digest | None |
| region | None |
| opencv | 5.0.0 |
| cool | None |
| python | 3.12.13 |

## Headline

| metric | baseline | cool | ratio |
|---|---|---|---|
| p50 ms | 24.233 | 24.324 | — |
| p95 ms | 29.018 | 29.576 | 0.981 |
| fps | 41.01 | 40.53 | 0.988 |
| CPU % | 193.8 | 195.9 | — |
| USD / 1000 frames | 0.00098 | 0.00099 | -1.0% less |

## Per-operation

| op | baseline p50 | cool p50 | speedup | accelerated |
|---|---|---|---|---|
| resize | 1.256 | 1.254 | 1.002 |  |
| cvt_gray | 0.13 | 0.13 | 1.0 |  |
| gaussian_blur | 0.087 | 0.102 | 0.853 |  |
| bg_subtract | 1.849 | 1.879 | 0.984 |  |
| threshold | 0.072 | 0.073 | 0.986 |  |
| morphology | 0.275 | 0.272 | 1.011 |  |
| warp_affine | 0.29 | 0.295 | 0.983 |  |
| sobel | 0.292 | 0.295 | 0.99 |  |
| find_contours | 0.166 | 0.165 | 1.006 |  |

## Does COOL execute the core workload?

accelerated_ops: `(none)`
0.0% of per-frame pipeline time is spent inside COOL-accelerated operations.

## Equivalence check

scores_identical: True

## Cost note

USD figures are MODELLED from the published us-east-1 on-demand rate of $0.145/hour for None, not from a measured bill.

## Notes

- non-Graviton host (AMD64); report is non-authoritative
- COOL build not present on this host; both columns are stock OpenCV 5 and no COOL claim is supported
- deployment record not found; instance facts unavailable
