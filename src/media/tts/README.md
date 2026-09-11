# TTS wrapper — `src/media/tts` (DP-C §4.4, §5)

Public surface: `synthesize()` → one `UnifiedMediaMessage` (`type:"tts"`),
`synthesizeStream()` → incremental `TtsChunk`s (MED-TTS-01), and
`BargeInController` / `barge_in.BargeInController` for cancellation
(MED-TTS-02). TypeScript entrypoint is `src/media/tts.ts` +
`src/media/tts/bargeIn.ts`; Python mirrors it as this package
(`from src.media.tts import ...`, `barge_in.py`).

**NONGOAL-04:** mechanics only. `voice` is a provider voice-id passthrough
(`"alloy"`, …); no persona, tone, or dialogue-policy code exists here.

## Streaming & barge-in contract

```ts
const barge = new BargeInController();
for await (const chunk of synthesizeStream(text, { signal: barge.signal })) {
  sink.write(Buffer.from(chunk.audio_chunk, "base64"));
  // abort between chunks throws DOMException("Aborted", "AbortError")
}
```

- The signal/event is checked **before every yield** and **before the provider
  fetch**; after an abort no further `audio_chunk` is produced.
- Native-streaming providers (elevenlabs) delegate verbatim; request/response
  providers (openai-tts, synthetic-fixture) are polyfilled by slicing the
  synthesized bytes into 4KB base64 chunks — same caller surface.
- `BargeInController` cancels *generation*; playback of already-emitted bytes
  must be cleared by the audio sink (`stopAndClear()`).

## Interruption → final envelope mapping

An interrupted stream surfaces as `AbortError` (TS) /
`asyncio.CancelledError` (Py) from the iterator. Callers map it to a final
`UnifiedMediaMessage` with `error:"tts_interrupted"`, e.g.:

```json
{ "type": "tts", "raw_ref": "hash:9f3a2c1e:text:Hello...",
  "text": "Hello...", "structured_fields": { "interrupted": true,
  "chunks_yielded": 3 }, "confidence": 0, "synthetic": false,
  "timestamp": "...", "provider": "openai-tts",
  "error": "tts_interrupted", "version": "1.0.0" }
```

Downstream may render a `degraded`-style treatment for interrupted TTS; that
mapping is not required by the wrapper.

## Failure behavior (§4.4 table)

| Input | Behavior |
| --- | --- |
| `""` / null text | message with `error:"empty_input"` — before any provider call |
| >5000 chars | message with `error:"unsupported_format"`, `text:"input_exceeds_limit"` — never silent truncation |
| unsupported `format` | `error:"unsupported_format"` |
| provider throw | rethrown normalized `MediaError("provider_error")` for RES-01 |
| interrupted stream | `AbortError`/`CancelledError`; caller maps to `error:"tts_interrupted"` |

For streaming, bad input has no envelope channel mid-flight, so
`synthesizeStream` throws `TtsInputError(empty_input|unsupported_format)`
before the first yield; use `synthesize()` when you need message-shaped errors.

## Providers & config swap

`synthetic-fixture` (offline fixture bytes — always available),
`openai-tts` (default live provider, `audio/speech`),
`elevenlabs` (native streaming). Swap via `MED_TTS_PROVIDER=…` or per-call
`opts.provider` — zero code change (MED-03). Credentials are read at call time
via the env var NAME in `credentials_env` only (GOV-RES-02).

## Latency budget (MED-TTS-03 / MED-TTS-AC-01)

Budget: capture→audio-start p50 ≤ 800 ms, p95 ≤ 1500 ms; wrapper-only
(synthetic-fixture, offline) p50 ≤ 60 ms, p95 ≤ 120 ms. Why latency+clean
barge-in over voice quality: dead air and un-interruptible audio read as
failure to users; naturalness is not scored. Measurement harness:
`scripts/bench-media-tts-latency.ts` / `bench_media_tts_latency.py` (owner M05,
re-used by BENCH-03); checked-in reports: [`reports/bench/media-tts-latency.json`](../../../reports/bench/media-tts-latency.json)
and [`reports/bench/media-tts-latency.md`](../../../reports/bench/media-tts-latency.md).
