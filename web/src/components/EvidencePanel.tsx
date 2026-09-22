import { useState, type JSX } from "react";
import { DownloadGlyph } from "./Glyphs";

export type EvidencePanelProps = { uris: string[] };

function keyOf(uri: string): string {
  const norm = uri
    .replace(/^[a-z]+:\/\//, "")
    .replace(/\\/g, "/");
  const parts = norm.split("/").filter((p) => p.length > 0);
  // Prefer runs/<run-id>/<file> when present (local file:// URIs carry a
  // machine-specific prefix before it); otherwise the last two segments.
  const ri = parts.lastIndexOf("runs");
  if (ri >= 0 && parts.length - ri >= 3) return parts.slice(ri, ri + 3).join("/");
  return parts.slice(-2).join("/");
}

/** Browser-openable URL for an evidence URI. Local file:// URIs are served
 * back by the API at /api/evidence/<key>; s3:// and http(s) URIs pass
 * through untouched. */
export function httpUrlFor(uri: string): string {
  if (!uri.startsWith("file://")) return uri;
  const norm = uri.replace(/\\/g, "/");
  const i = norm.indexOf("runs/");
  if (i >= 0) return `/api/evidence/${norm.slice(i)}`;
  return uri;
}

function Item({ uri }: { uri: string }): JSX.Element {
  const [failed, setFailed] = useState(false);
  const key = keyOf(uri);
  const src = httpUrlFor(uri);
  const lower = src.toLowerCase();
  const isVideo = lower.endsWith(".mp4") || lower.endsWith(".webm");
  const isImage = lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg");
  // s3:// URIs have no fetchable form in this backend version (the API answers
  // 501 "use the presigned URL", and the payload carries no presigned URL), so
  // they render as a link to the key itself rather than a broken embed.
  const playable = (isVideo || isImage) && !src.startsWith("s3://") && !src.startsWith("file://");
  if (!playable || failed) {
    if (playable && failed) {
      return (
        <div className="evidence-missing" role="status">
          this clip could not be loaded — {key}
        </div>
      );
    }
    return (
      <div className="evidence-item">
        <a href={src} target="_blank" rel="noreferrer" aria-label={`open evidence ${key}`}>
          {key}
        </a>
      </div>
    );
  }
  return (
    <figure className="evidence-item" style={{ margin: 0 }}>
      {isVideo ? (
        <video controls src={src} aria-label={`evidence clip ${key}`} onError={() => setFailed(true)} />
      ) : (
        <img src={src} alt={`evidence still ${key}`} onError={() => setFailed(true)} />
      )}
      <figcaption className="key">
        <span className="mono small muted">{key}</span>
        <a href={src} download aria-label={`download evidence ${key}`}>
          <DownloadGlyph />
        </a>
      </figcaption>
    </figure>
  );
}

export function EvidencePanel({ uris }: EvidencePanelProps): JSX.Element {
  return (
    <section aria-label="Evidence" className="card" data-demo-focus="evidence">
      <span className="caption">Evidence</span>
      {uris.length === 0 ? (
        <p className="small muted" role="status">
          No evidence clips yet — stills and clips saved during the run appear here.
        </p>
      ) : (
        <div className="evidence-grid">
          {uris.map((u) => (
            <Item key={u} uri={u} />
          ))}
        </div>
      )}
    </section>
  );
}
