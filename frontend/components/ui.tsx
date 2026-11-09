"use client";

import { useState } from "react";
import { portraitSlug } from "@/lib/format";

export function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`pixel-panel p-3 ${className}`} aria-label={title}>
      <h2 className="mb-2 font-[family-name:var(--font-title)] text-[11px] tracking-wider text-amber uppercase">{title}</h2>
      {children}
    </section>
  );
}

/** Status is always spelled out in text, never colour alone (PRD 11 accessibility). */
export function Stamp({ status }: { status: string }) {
  const tone =
    status === "REFUTED" || status === "DISPUTED"
      ? "border-stamp-red text-stamp-red"
      : status === "ESTABLISHED" || status === "VERIFIED"
        ? "border-stamp-green text-stamp-green"
        : "border-dim text-dim";
  return <span className={`ml-2 inline-block -rotate-3 border-2 px-1 text-sm uppercase ${tone}`}>{status}</span>;
}

/** Portrait from /portraits/<slug>.png (docs/art/portraits.csv); a pixel monogram until the art exists. */
export function Portrait({ name, size = 72 }: { name: string; size?: number }) {
  const [missing, setMissing] = useState(false);
  const initials = name.replace(/^(Dr|Inspector|Sergeant|Professor|Father|Count|Lady)\s+/, "").split(/\s+/).map((w) => w[0]).slice(0, 2).join("");
  if (missing) {
    return (
      <div
        aria-label={`Portrait of ${name} (placeholder)`}
        className="flex items-center justify-center border-3 border-paper-ink bg-dim font-[family-name:var(--font-title)] text-desk"
        style={{ width: size, height: size, fontSize: size / 4 }}
      >
        {initials}
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static pixel art, no optimisation wanted
    <img
      src={`/portraits/${portraitSlug(name)}.png`}
      alt={`Portrait of ${name}`}
      width={size}
      height={size}
      className="pixelated border-3 border-paper-ink object-cover"
      onError={() => setMissing(true)}
    />
  );
}
