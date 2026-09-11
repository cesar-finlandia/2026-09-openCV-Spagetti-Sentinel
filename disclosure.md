# Provenance & Disclosure

> Generated from the assembly manifest — do not hand-edit accuracy; polish wording only if needed.

## Reused prior code

For this hackathon I reused **6** pre-existing block(s) of code that handle infrastructure-level functionality, none of them specific to this project:

- a wrapper that retries a slow or failed provider call and falls back to a cached response, so a live demo never dead-ends on a blank screen
- a typed event-streaming bus for pushing step-by-step progress to the browser, plus a one-command deploy helper and a small themed UI shell
- thin wrappers around speech-to-text, image and PDF extraction services
- a message buffer that keeps a conversation inside a model's context window, with a pluggable token counter
- a generator for synthetic demo records that stamps every row as synthetic
- code that counts token and request usage and warns before a configured budget is exceeded, to prevent overspending

Thus all application-level code, and most other low-level code, was designed and implemented only for this hackathon.

The repository also contains a small amount of pre-existing developer tooling used to prepare this submission's documents. The application does not call it at runtime and it is not part of the product.

## How this entry was built

The workflow was: design plans authored with Claude AI from my project idea, then implemented using cheaper AI models. Testing was done with Claude as well.

_Generated at 2026-09-11T14:44:31.545Z from manifest hash a2f57dfee9d5b55f1a347cf5c115cfacdd64597ec80f907b89933e252e461acd._

## AI assistance in building this entry

> The design plans for this entry were authored with Claude AI. The implementation was carried out by
> cheaper models following those plans, and the result was tested with Claude. Every design decision,
> every threshold and every claim in this repository was reviewed by the author before it shipped.

## Data provenance

> The four demo clips under `fixtures/clips/` are synthetic: they are drawn procedurally by
> `app/fixtures/generate.py` from fixed seeds, and every frame carries a visible "SYNTHETIC"
> watermark. `fixtures/manifest.json` is stamped `"synthetic": true`. No third-party footage, dataset,
> model weight or trademark is included in this repository. `fixtures/real/` is empty on purpose; any
> real footage an evaluator adds there is theirs, not ours.

## Runtime proofs

> The measurements quoted in this repository were produced by two commands whose outputs are committed
> alongside them: `bench/run_bench.py` wrote `bench/results/cool-vs-baseline.json` on the deployed
> Graviton instance recorded in `deploy/deployment-record.json`, and `eval/run_eval.py` wrote
> `eval/results/eval-report.json`. Cost figures are modelled from published on-demand list prices,
> not from a measured bill, and are labelled as such wherever they appear.
