export type EvidencePanelProps = { uris: string[] };

function playable(u: string): string {
  if (!u) return u;
  if (u.startsWith("/api/evidence/") || u.startsWith("http")) return u;
  const m = u.replace(/\\/g, "/").match(/(runs\/.+)$/);
  if (m) return `/api/evidence/${m[1]}`;
  return u;
}

export function EvidencePanel(props: EvidencePanelProps) {
  const { uris } = props;
  if (!uris.length) {
    return (
      <div className="ss-card ss-muted">Evidence will appear here when the agent saves a clip.</div>
    );
  }
  return (
    <div className="ss-card">
      <h3>Evidence</h3>
      {uris.map((u, i) => {
        const http = playable(u);
        if (u.endsWith(".mp4")) {
          return (
            <div key={i}>
              <video controls src={http} style={{ maxWidth: "100%" }} />
              <div>
                <a href={http} download>
                  download clip
                </a>
              </div>
            </div>
          );
        }
        if (u.endsWith(".png")) {
          return (
            <div key={i}>
              <img src={http} alt="evidence frame" style={{ maxWidth: "100%" }} />
              <div>
                <a href={http} download>
                  download frame
                </a>
              </div>
            </div>
          );
        }
        return (
          <div key={i}>
            <a href={http}>evidence not stored for this alert — open link</a>
          </div>
        );
      })}
    </div>
  );
}
