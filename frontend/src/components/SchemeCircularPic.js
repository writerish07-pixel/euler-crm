import React from "react";

/** OEM circular image for the billed / scheme as-of month. Missing months show nothing. */
export default function SchemeCircularPic({ circular }) {
  if (!circular?.imageUrl) return null;
  const href = circular.pdfUrl || circular.imageUrl;
  const label = [circular.title, circular.ref].filter(Boolean).join(" · ");
  return (
    <div className="mb-4" data-testid="scheme-circular-pic">
      <div className="text-[11px] uppercase tracking-wide text-ink-faint mb-1">{label || "Scheme circular"}</div>
      <a href={href} target="_blank" rel="noreferrer">
        <img
          src={circular.imageUrl}
          alt={circular.title || "Scheme circular"}
          className="w-full max-w-lg rounded-lg ring-1 ring-line bg-white"
        />
      </a>
    </div>
  );
}
