import { useState, useEffect } from "react";
import { getSessionImage } from "../api/client.js";

/**
 * Fetches an ownership-scoped report image (heatmap/scanpath) as an
 * authenticated blob and renders it -- an <img src> can't carry a bearer
 * token, so this bridges that gap. Ported from frontend/src/views/Dashboard.jsx.
 */
export default function ReportImage({ token, sessionId, kind, alt, emptyLabel, natural = false, cover = false }) {
  const [url, setUrl] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    let cancelled = false;
    let objectUrl = null;
    setStatus("loading");
    getSessionImage(token, sessionId, kind)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, sessionId, kind]);

  if (status === "loading") {
    return (
      <div className={`flex w-full items-center justify-center ${natural ? "min-h-[260px]" : "h-full"}`}>
        <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className={`flex w-full items-center justify-center p-6 text-center ${natural ? "min-h-[260px]" : "h-full"}`}>
        <p className="text-[13px] text-text-secondary">{emptyLabel || "Not available for this session."}</p>
      </div>
    );
  }
  // natural: take the image's own height (the report viewer), instead of
  // fitting into a fixed box
  return <img src={url} alt={alt} className={natural ? "block h-auto w-full rounded-[14px]" : cover ? "h-full w-full object-cover object-top" : "h-full w-full object-contain"} />;
}
