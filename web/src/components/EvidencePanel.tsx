import { useState, type JSX } from "react";
import { DownloadGlyph } from "./Glyphs";

export type EvidencePanelProps = { uris: string[] };

function keyOf(uri: string): string {
  const noProto = uri.replace(/^[a-z]+:\/\//, "");
  const parts = noProto.split("/");
  return parts.slice(-2).join("/");
}

function Item({ uri }: { uri: string }): JSX.Element {
  const [failed, setFailed] = useState(false);
  const key = keyOf(uri);
  const lower = uri.toLowerCase();
  const isVideo = lower.endsWith(".mp4") || lower.endsWith(".webm");
  const isImage = lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg");
  // s3:// URIs have no fetchable form in this backend version (the API answers
  // 501 "use the presigned URL", and the payload carries no presigned URL), so
  // they render as a link to the key itself rather than a broken embed.
  const playable = (isVideo || isImage) && !uri.startsWith("s3://") && !uri.startsWith("file://");
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
        <a href={uri} target="_blank" rel="noreferrer" aria-label={`open evidence ${key}`}>
          {key}
        </a>
      </div>
    );
  }
  return (
    <figure className="evidence-item" style={{ margin: 0 }}>
      {isVideo ? (
        <video controls src={uri} aria-label={`evidence clip ${key}`} onError={() => setFailed(true)} />
      ) : (
        <img src={uri} alt={`evidence still ${key}`} onError={() => setFailed(true)} />
      )}
      <figcaption className="key">
        <span className="mono small muted">{key}</span>
        <a href={uri} download aria-label={`download evidence ${key}`}>
          <DownloadGlyph />
        </a>
      </figcaption>
    </figure>
  );
}

export function EvidencePanel({ uris }: EvidencePanelProps): JSX.Element {
  return (
    <section aria-label="Evidence" className="card">
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
