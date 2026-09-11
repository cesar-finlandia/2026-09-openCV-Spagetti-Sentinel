# Vision wrapper — `src/media/vision` (DP-C §4.2)

Public surface: `caption()` → one `UnifiedMediaMessage` (`type:"vision"`).
TypeScript entrypoint is `src/media/vision.ts`; Python mirror is this
package. Isolated per MED-REU-02: imports only media-message types, media
config and its own providers — never stt/pdf/tts.

## Providers

| Provider id | Credential env | Model default | Notes |
| --- | --- | --- | --- |
| `synthetic-fixture` | none | — | Offline fixture caption, always available |
| `openai-gpt4o-vision` (default) | `OPENAI_API_KEY` | `gpt-4o` | openai SDK vision input |
| `anthropic-claude-vision` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022` | optional dep |

## Prompt configurability (MED-REU-01)

The default prompt in [`default-prompt.txt`](default-prompt.txt) is generic
("Describe the contents of this image"). It is overridable per call
(`opts.prompt`), via `config/media.json`, or via env — the wrapper never
pre-fills a vertical or domain vocabulary.

## Env overrides

- `MED_VISION_PROVIDER`, `MED_VISION_SECONDARY_PROVIDER`,
  `MED_VISION_PROMPT` (precedence: schema defaults < `config/media.json` <
  call opts < `MED_*` env — DP-C §6.1). Zero code change swap (MED-03).
- Credentials resolve at call time from the env var *named* by
  `credentials_env`; no key is stored (GOV-RES-02).

## Fixture provenance

Offline tests use `examples/dummy-fixtures/media/vision/sample.png`
(+ `.jpeg` alt) via `synthetic-fixture`: a checked-in synthetic 640×480
widget silhouette with a Lorem-ipsum text box — no photos, no PII, no brand.
Companion fixture caption: `caption.json`. The wrapper source never imports
fixtures; only tests do.
