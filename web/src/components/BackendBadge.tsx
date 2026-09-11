import type { Health } from "../api";
import type { RunHeader } from "../selectors";

export type BackendBadgeProps = { header: RunHeader; health: Health | null };

export function BackendBadge(props: BackendBadgeProps) {
  const { header, health } = props;
  const cool = header?.coolVersion ?? health?.cool_version ?? null;
  const arch = health?.arch ?? "";
  const ocv = header?.opencvVersion ?? health?.opencv_version ?? "";
  const marker = health?.build_marker ?? "";
  if (cool) {
    return (
      <span data-beat="backend-badge">
        <span className="ss-chip ss-chip--cool">COOL on {arch || "arm64"}</span>{" "}
        {marker ? <span className="ss-chip">{marker}</span> : null}
      </span>
    );
  }
  return (
    <span data-beat="backend-badge">
      <span className="ss-chip ss-chip--base">baseline OpenCV {ocv || "5"}</span>{" "}
      {marker ? <span className="ss-chip">{marker}</span> : null}
    </span>
  );
}
