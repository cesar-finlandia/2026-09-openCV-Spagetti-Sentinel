# STT wrapper — `src/media/stt` (DP-C §4.1)

Public surface: `transcribe()` → one `UnifiedMediaMessage` (`type:"stt"`).
TypeScript entrypoint is `src/media/stt.ts`; Python mirror is this package
(`from src.media.stt import transcribe`). Isolated per MED-REU-02: imports
only media-message types, media config and its own providers — never
vision/pdf/tts.

## Providers

| Provider id | Credential env | Model default | Notes |
| --- | --- | --- | --- |
| `synthetic-fixture` | none | — | Offline fixture transcript, always available |
| `openai-whisper` (default) | `OPENAI_API_KEY` | `whisper-1` | openai SDK audio transcription |
| `deepgram` | `DEEPGRAM_API_KEY` | `nova-2` | optional dep |

## Env overrides

- `MED_STT_PROVIDER`, `MED_STT_SECONDARY_PROVIDER`, `MED_STT_PROMPT`
  (precedence: schema defaults < `config/media.json` < call opts <
  `MED_*` env — DP-C §6.1). Zero code change swap (MED-03).
- Credentials resolve at call time from the env var *named* by
  `credentials_env`; no key is ever stored in config or code (GOV-RES-02).

## Fixture provenance

Offline tests use `examples/dummy-fixtures/media/stt/sample.wav` (+ `.mp3`
alt) via the `synthetic-fixture` provider: checked-in synthetic RIFF/WAV
audio generated once from `Acme Corp` placeholder text — no real user voice,
no PII. Companion fixture transcript: `transcript.json`. The wrapper source
never imports fixtures; only tests do.
