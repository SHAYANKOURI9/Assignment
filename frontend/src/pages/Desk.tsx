import { useEffect, useState } from "react";
import { analyticsApi, DashboardData } from "../lib/api";
import { Spinner, ErrorMsg } from "../components/ui";

function Bar({ value, max, color = "#E8A33D" }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-[#26262F] rounded-full h-1.5">
        <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[10px] text-[#6B6B80] w-8 text-right">{value}</span>
    </div>
  );
}

function Stat({ label, value, unit = "" }: { label: string; value: string | number | null; unit?: string }) {
  return (
    <div className="bg-[#1A1A20] border border-[#26262F] rounded p-4">
      <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-1">{label}</div>
      <div className="text-2xl text-[#E8A33D] font-mono">
        {value ?? "—"}{unit && value != null ? <span className="text-sm text-[#6B6B80] ml-1">{unit}</span> : null}
      </div>
    </div>
  );
}

export default function Desk() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [date, setDate] = useState("");

  const load = (d?: string) => {
    setLoading(true);
    analyticsApi.dashboard(d)
      .then(setData)
      .catch(() => setError("Failed to load dashboard."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Spinner />;
  if (error || !data) return <ErrorMsg msg={error || "No data"} />;

  const maxSubject = Math.max(...Object.values(data.by_subject), 1);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <h1 className="text-[#E8A33D] font-mono text-lg uppercase tracking-widest">Desk Dashboard</h1>
        <input
          type="date"
          value={date}
          onChange={(e) => { setDate(e.target.value); load(e.target.value || undefined); }}
          className="bg-[#1A1A20] border border-[#26262F] rounded px-2 py-1 text-xs text-[#F2EDE4] focus:outline-none focus:border-[#E8A33D]"
        />
        <span className="text-[#6B6B80] text-xs">{data.date}</span>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <Stat label="Published" value={data.published_count} />
        <Stat label="Median dwell" value={data.dwell.median_minutes} unit="min" />
        <Stat label="P90 dwell" value={data.dwell.p90_minutes} unit="min" />
        <Stat label="Rewrite rate" value={data.rewrite_rate_pct} unit="%" />
      </div>

      {/* Dedup savings */}
      <div className="bg-[#1A1A20] border border-[#26262F] rounded p-4 mb-6">
        <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-3">Dedup savings</div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-[#F2EDE4]">{data.dedup.items_in} items in</span>
          <span className="text-[#26262F]">→</span>
          <span className="text-[#E8A33D] font-bold">{data.dedup.briefs_out} briefs out</span>
          <span className="text-[#4CAF7D] text-xs ml-auto">
            saved {data.dedup.saved} reads
          </span>
        </div>
        <div className="mt-2 bg-[#26262F] rounded-full h-2">
          <div
            className="h-2 rounded-full bg-[#E8A33D]"
            style={{ width: `${data.dedup.items_in > 0 ? (data.dedup.briefs_out / data.dedup.items_in) * 100 : 0}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Stage breakdown */}
        <div className="bg-[#1A1A20] border border-[#26262F] rounded p-4">
          <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-3">Stage dwell (median min)</div>
          {[
            ["Ingest → Claim", data.stages.ingest_to_claim_median_min],
            ["Claim → Submit", data.stages.claim_to_submit_median_min],
            ["Submit → Publish", data.stages.submit_to_publish_median_min],
          ].map(([label, val]) => (
            <div key={label as string} className="mb-2">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-[#B8B0A4]">{label}</span>
                <span className="text-[#E8A33D]">{val ?? "—"}</span>
              </div>
              <Bar value={Number(val) || 0} max={Math.max(
                Number(data.stages.ingest_to_claim_median_min) || 0,
                Number(data.stages.claim_to_submit_median_min) || 0,
                Number(data.stages.submit_to_publish_median_min) || 0,
                1
              )} />
            </div>
          ))}
        </div>

        {/* Slowest story */}
        <div className="bg-[#1A1A20] border border-[#26262F] rounded p-4">
          <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-3">Slowest story</div>
          {data.dwell.slowest ? (
            <>
              <div className="text-[#F2EDE4] text-sm leading-snug mb-2">{data.dwell.slowest.subject}</div>
              <div className="text-[#E8A33D] text-xl font-mono">{data.dwell.slowest.dwell_minutes} min</div>
              <a href={`/stories/${data.dwell.slowest.id}`}
                className="text-[10px] text-[#6B6B80] hover:text-[#E8A33D] mt-2 block">
                view story →
              </a>
            </>
          ) : (
            <div className="text-[#6B6B80] text-xs">No data</div>
          )}
        </div>
      </div>

      {/* By subject */}
      {Object.keys(data.by_subject).length > 0 && (
        <div className="bg-[#1A1A20] border border-[#26262F] rounded p-4">
          <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-3">By subject</div>
          <div className="flex flex-col gap-2">
            {Object.entries(data.by_subject)
              .sort(([, a], [, b]) => b - a)
              .map(([subject, count]) => (
                <div key={subject}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[#B8B0A4] truncate max-w-xs">{subject}</span>
                    <span className="text-[#E8A33D]">{count}</span>
                  </div>
                  <Bar value={count} max={maxSubject} />
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
