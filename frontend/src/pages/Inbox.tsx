import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ingestApi, deskApi, RawItem } from "../lib/api";
import { Badge, Spinner, ErrorMsg, ago, TierDot } from "../components/ui";
import { useAuth } from "../hooks/useAuth";

export default function Inbox() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState<RawItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  const [clustering, setClustering] = useState(false);
  const [clusterMsg, setClusterMsg] = useState("");

  const load = () => {
    setLoading(true);
    ingestApi.items("UNTRIAGED")
      .then(setItems)
      .catch(() => setError("Failed to load inbox."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  // Keyboard navigation: j/k to move, c to cluster
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return;
      if (e.key === "j") setSelected((s) => Math.min(s + 1, items.length - 1));
      if (e.key === "k") setSelected((s) => Math.max(s - 1, 0));
      if (e.key === "c") handleCluster();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [items]);

  const handleCluster = async () => {
    setClustering(true);
    setClusterMsg("");
    try {
      const r = await deskApi.cluster();
      setClusterMsg(`✓ ${r.stories_created} stories created from ${r.items_clustered} items`);
      load();
    } catch {
      setClusterMsg("Clustering failed.");
    } finally {
      setClustering(false);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-[#E8A33D] font-mono text-lg uppercase tracking-widest">Inbox</h1>
          <div className="text-[#6B6B80] text-xs mt-1">
            {items.length} untriaged · <kbd className="text-[#F2EDE4]">j/k</kbd> navigate · <kbd className="text-[#F2EDE4]">c</kbd> cluster
          </div>
        </div>
        <button
          onClick={handleCluster}
          disabled={clustering}
          className="px-4 py-2 bg-[#E8A33D] text-[#0E0E11] text-xs font-bold rounded hover:bg-[#A8722A] transition-colors disabled:opacity-50"
        >
          {clustering ? "Clustering…" : "Run Cluster"}
        </button>
      </div>

      {clusterMsg && (
        <div className="mb-4 text-xs text-[#4CAF7D] bg-[#1A2A1A] border border-[#4CAF7D]/30 rounded px-3 py-2">
          {clusterMsg}
        </div>
      )}
      {error && <ErrorMsg msg={error} />}

      {items.length === 0 ? (
        <div className="text-[#6B6B80] text-sm text-center py-16">
          Inbox is empty — all items have been triaged.
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {items.map((item, i) => (
            <div
              key={item.id}
              onClick={() => setSelected(i)}
              className={`flex items-start gap-3 px-3 py-2.5 rounded cursor-pointer transition-colors ${
                i === selected ? "bg-[#26262F] border border-[#E8A33D]/30" : "hover:bg-[#1A1A20]"
              }`}
            >
              <TierDot tier={item.source.trust_tier} />
              <div className="flex-1 min-w-0">
                <div className="text-[#F2EDE4] text-sm truncate">{item.headline}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[#6B6B80] text-[10px]">{item.source.name}</span>
                  <Badge label={item.source.kind} />
                  <span className="text-[#6B6B80] text-[10px]">{ago(item.received_at)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {items[selected] && (
        <div className="mt-6 bg-[#1A1A20] border border-[#26262F] rounded p-4">
          <div className="text-[#E8A33D] text-sm font-bold mb-2">{items[selected].headline}</div>
          <div className="text-[#B8B0A4] text-xs whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
            {items[selected].body}
          </div>
          {items[selected].url && (
            <a href={items[selected].url} target="_blank" rel="noreferrer"
              className="text-[#6B6B80] text-[10px] hover:text-[#E8A33D] mt-2 block">
              {items[selected].url}
            </a>
          )}
        </div>
      )}
    </div>
  );
}
