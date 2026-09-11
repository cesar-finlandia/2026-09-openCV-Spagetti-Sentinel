# PDF wrapper — `src/media/pdf` (DP-C §4.3)

Public surface: `extract()` → one `UnifiedMediaMessage` (`type:"pdf"`).
TypeScript entrypoint is `src/media/pdf.ts`; Python mirror is this package.
Isolated per MED-REU-02: imports only media-message types, media config and
its own providers — never stt/vision/tts.

## Text providers

| Provider id | Credential env | Notes |
| --- | --- | --- |
| `synthetic-fixture` | none | Offline fixture extraction, always available |
| `pypdf` (default, Py) | none — dep only | light born-digital text extraction |
| `pdfjs` (TS) | none — dep only | Node-side text extraction |

## OCR fallback

The pipeline is two-stage: the text layer runs first (fast path for
born-digital PDFs); any page whose extracted char count is below
`DEFAULT_OCR_THRESHOLD_CHARS` (40) is re-run through the configured OCR
provider. OCR ids: `tesseract` (default in `config/media.json`, optional
extra — needs the system `tesseract` binary, availability-probed) or `none`.
A missing/unavailable binary degrades gracefully — pages keep empty text,
the message reports `structured_fields.ocr_provider:"none"` /
`ocr_degraded:true` (GOV-RES-04), it never raises or hangs. Offline CI pairs
the synthetic-fixture text provider with a synthetic-fixture OCR provider so
the fallback path is exercised without any binary.

## Env overrides

- `MED_PDF_PROVIDER`, `MED_PDF_SECONDARY_PROVIDER`, `MED_OCR_PROVIDER`
  (precedence: schema defaults < `config/media.json` < call opts <
  `MED_*` env — DP-C §6.1). Zero code change swap (MED-03).
- No credentials: text/OCR providers are dependency- or binary-based.

## Fixture provenance

Offline tests use `examples/dummy-fixtures/media/pdf/sample.pdf`: a
checked-in 2-page synthetic PDF — page 1 born-digital text, page 2 a scanned
image — exercising both pipeline stages with one fixture. Companion fixture
extract: `extract.json`. The wrapper source never imports fixtures; only
tests do.
