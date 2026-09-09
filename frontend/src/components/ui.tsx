// Shared small components

export function Badge({ label, color }: { label: string; color?: string }) {
  const colors: Record<string, string> = {
    NEW: "bg-[#26262F] text-[#E8A33D]",
    DRAFT: "bg-[#1A2A1A] text-[#4CAF7D]",
    IN_REVIEW: "bg-[#2A2A1A] text-[#E8A33D]",
    PUBLISHED: "bg-[#1A2A1A] text-[#4CAF7D]",
    SPIKED: "bg-[#2A1A1A] text-[#E05252]",
    SUPERSEDED: "bg-[#26262F] text-[#6B6B80]",
    CORRECTED: "bg-[#2A2A1A] text-[#E8A33D]",
    LIVE: "bg-[#1A2A1A] text-[#4CAF7D]",
    WIRE: "bg-[#1A1A2A] text-[#7B9FE8]",
    PRESS_RELEASE: "bg-[#26262F] text-[#B8B0A4]",
    BLOG: "bg-[#26262F] text-[#B8B0A4]",
    SOCIAL: "bg-[#26262F] text-[#B8B0A4]",
  };
  const cls = color || colors[label] || "bg-[#26262F] text-[#B8B0A4]";
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider ${cls}`}>
      {label}
    </span>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-8">
      <div className="w-5 h-5 border-2 border-[#E8A33D] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

export function ErrorMsg({ msg }: { msg: string }) {
  return <div className="text-[#E05252] text-xs p-3 bg-[#2A1A1A] rounded border border-[#E05252]/30">{msg}</div>;
}

export function Kbd({ k }: { k: string }) {
  return (
    <kbd className="inline-block px-1 py-0.5 text-[10px] bg-[#26262F] border border-[#3A3A4A] rounded text-[#B8B0A4]">
      {k}
    </kbd>
  );
}

export function ts(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function TierDot({ tier }: { tier: number }) {
  const colors = ["", "bg-[#E8A33D]", "bg-[#7B9FE8]", "bg-[#6B6B80]"];
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[tier] || colors[3]}`} title={`Trust tier ${tier}`} />;
}
