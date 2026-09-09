import { useState, useRef } from "react";
import { ingestApi } from "../lib/api";
import { Spinner, ErrorMsg } from "../components/ui";

export default function Ingest() {
  const [mode, setMode] = useState<"manual" | "screenshot">("manual");
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [sourceSlug, setSourceSlug] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleScreenshot = async (file: File) => {
    setExtracting(true);
    setError("");
    try {
      const result = await ingestApi.screenshot(file);
      setHeadline(result.headline);
      setBody(result.body);
      setLlmAvailable(result.llm_available);
      if (!result.llm_available) {
        setError("No ANTHROPIC_API_KEY set — screenshot text extraction unavailable. Fill in manually.");
      }
    } catch {
      setError("Screenshot extraction failed.");
    } finally {
      setExtracting(false);
    }
  };

  const handleSubmit = async () => {
    if (!headline || !body || !sourceSlug) {
      setError("Headline, body, and source slug are required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await ingestApi.manual({ headline, body, source_slug: sourceSlug, url });
      setSuccess("Item added to the pile.");
      setHeadline(""); setBody(""); setUrl("");
    } catch (e: any) {
      setError(e?.data?.error || "Failed to ingest item.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-[#E8A33D] font-mono text-lg uppercase tracking-widest mb-6">Ingest</h1>

      <div className="flex gap-2 mb-6">
        {(["manual", "screenshot"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)}
            className={`text-xs uppercase px-3 py-1.5 rounded transition-colors ${
              mode === m ? "bg-[#E8A33D] text-[#0E0E11] font-bold" : "text-[#6B6B80] hover:text-[#F2EDE4]"
            }`}>
            {m}
          </button>
        ))}
      </div>

      {mode === "screenshot" && (
        <div
          className="border-2 border-dashed border-[#26262F] rounded p-8 text-center mb-4 cursor-pointer hover:border-[#E8A33D]/40 transition-colors"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleScreenshot(f); }}
        >
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleScreenshot(f); }} />
          {extracting ? (
            <div className="text-[#6B6B80] text-sm">Extracting text…</div>
          ) : (
            <>
              <div className="text-[#6B6B80] text-sm mb-1">Drop a screenshot or click to upload</div>
              <div className="text-[10px] text-[#26262F]">
                {llmAvailable === false ? "LLM unavailable — fill in manually" : "PNG, JPG, WEBP"}
              </div>
            </>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {error && <ErrorMsg msg={error} />}
        {success && (
          <div className="text-[#4CAF7D] text-xs bg-[#1A2A1A] border border-[#4CAF7D]/30 rounded px-3 py-2">
            {success}
          </div>
        )}

        <input className="input" placeholder="Headline" value={headline}
          onChange={(e) => setHeadline(e.target.value)} />
        <textarea className="input min-h-32 resize-none" placeholder="Body text"
          value={body} onChange={(e) => setBody(e.target.value)} />
        <input className="input" placeholder="Source slug (e.g. bharat-news-service)"
          value={sourceSlug} onChange={(e) => setSourceSlug(e.target.value)} />
        <input className="input" placeholder="URL (optional)"
          value={url} onChange={(e) => setUrl(e.target.value)} />

        <button onClick={handleSubmit} disabled={loading}
          className="bg-[#E8A33D] text-[#0E0E11] font-bold text-sm py-2 rounded hover:bg-[#A8722A] transition-colors disabled:opacity-50">
          {loading ? "Adding…" : "Add to pile"}
        </button>
      </div>

      <style>{`.input { background:#0E0E11; border:1px solid #26262F; border-radius:4px; padding:8px 12px; font-size:13px; color:#F2EDE4; font-family:inherit; width:100%; outline:none; } .input:focus { border-color:#E8A33D; }`}</style>
    </div>
  );
}
