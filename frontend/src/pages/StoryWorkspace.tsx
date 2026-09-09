import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { deskApi, StoryDetail, BriefRevision } from "../lib/api";
import { Badge, Spinner, ErrorMsg, ago, ts, TierDot } from "../components/ui";
import { useAuth } from "../hooks/useAuth";

export default function StoryWorkspace() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [story, setStory] = useState<StoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [acting, setActing] = useState(false);

  // Editor state
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [mergeTarget, setMergeTarget] = useState("");
  const [mergeReason, setMergeReason] = useState("");

  const load = () => {
    deskApi.story(Number(id))
      .then((s) => {
        setStory(s);
        const latest = s.revisions[s.revisions.length - 1];
        if (latest) { setHeadline(latest.headline); setBody(latest.body); }
      })
      .catch(() => setError("Story not found."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [id]);

  const act = async (fn: () => Promise<unknown>) => {
    setActing(true);
    setError("");
    try { await fn(); load(); }
    catch (e: any) { setError(e?.data?.error || e?.data?.detail || "Action failed."); }
    finally { setActing(false); }
  };

  if (loading) return <Spinner />;
  if (!story) return <ErrorMsg msg={error || "Not found"} />;

  const latest = story.revisions[story.revisions.length - 1];
  const livePub = story.publications.find((p) => p.status === "LIVE");
  const activeItems = story.story_items.filter((si) => !si.detached_at);

  const canClaim = user?.role === "REPORTER" && story.status === "NEW";
  const canRevise = ["REPORTER", "EDITOR"].includes(user?.role || "") && !["SPIKED", "PUBLISHED"].includes(story.status);
  const canSubmit = user?.role === "REPORTER" && story.status === "DRAFT";
  const canPublish = user?.role === "EDITOR" && ["IN_REVIEW", "DRAFT"].includes(story.status);
  const canCorrect = user?.role === "EDITOR" && story.status === "PUBLISHED";
  const canMerge = user?.role === "EDITOR";
  const canSpike = ["REPORTER", "EDITOR"].includes(user?.role || "") && story.status !== "PUBLISHED";

  return (
    <div className="flex h-[calc(100vh-48px)]">
      {/* Left: brief editor */}
      <div className="flex-1 flex flex-col border-r border-[#26262F] overflow-y-auto">
        <div className="p-4 border-b border-[#26262F] flex items-center gap-3">
          <Badge label={story.status} />
          {story.cluster_confidence != null && (
            <span className="text-[10px] text-[#6B6B80]">
              conf {Math.round(story.cluster_confidence * 100)}%
            </span>
          )}
          <span className="text-[10px] text-[#6B6B80] ml-auto">
            {activeItems.length} source{activeItems.length !== 1 ? "s" : ""}
          </span>
        </div>

        <div className="p-4 flex flex-col gap-3 flex-1">
          {error && <ErrorMsg msg={error} />}

          <input
            className="bg-[#0E0E11] border border-[#26262F] rounded px-3 py-2 text-sm text-[#F2EDE4] focus:outline-none focus:border-[#E8A33D] font-serif"
            placeholder="Headline"
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            disabled={!canRevise}
          />
          <textarea
            className="bg-[#0E0E11] border border-[#26262F] rounded px-3 py-2 text-sm text-[#F2EDE4] focus:outline-none focus:border-[#E8A33D] resize-none flex-1 min-h-40 leading-relaxed"
            placeholder="Brief body (60–80 words)"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            disabled={!canRevise}
          />

          {canRevise && (
            <input
              className="bg-[#0E0E11] border border-[#26262F] rounded px-3 py-2 text-xs text-[#B8B0A4] focus:outline-none focus:border-[#E8A33D]"
              placeholder="Change note (optional)"
              value={changeNote}
              onChange={(e) => setChangeNote(e.target.value)}
            />
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2 pt-2">
            {canClaim && (
              <button onClick={() => act(() => deskApi.claim(story.id))} disabled={acting}
                className="btn-primary">Claim</button>
            )}
            {canRevise && (
              <button onClick={() => act(() => deskApi.revise(story.id, { headline, body, change_note: changeNote }))}
                disabled={acting || !headline || !body} className="btn-primary">Save Draft</button>
            )}
            {canSubmit && (
              <button onClick={() => act(() => deskApi.submit(story.id))} disabled={acting}
                className="btn-amber">Submit for Review</button>
            )}
            {canPublish && (
              <button onClick={() => act(() => deskApi.publish(story.id))} disabled={acting}
                className="btn-green">Publish</button>
            )}
            {canCorrect && (
              <button onClick={() => act(() => deskApi.correct(story.id, { headline, body, change_note: changeNote || "Correction" }))}
                disabled={acting || !changeNote} className="btn-amber">Publish Correction</button>
            )}
            {canSpike && (
              <button onClick={() => act(() => deskApi.spike(story.id))} disabled={acting}
                className="btn-red">Spike</button>
            )}
          </div>

          {/* Merge */}
          {canMerge && (
            <div className="border-t border-[#26262F] pt-3 mt-2">
              <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-2">Merge into story</div>
              <div className="flex gap-2">
                <input
                  className="flex-1 bg-[#0E0E11] border border-[#26262F] rounded px-2 py-1.5 text-xs text-[#F2EDE4] focus:outline-none focus:border-[#E8A33D]"
                  placeholder="Story ID"
                  value={mergeTarget}
                  onChange={(e) => setMergeTarget(e.target.value)}
                />
                <input
                  className="flex-1 bg-[#0E0E11] border border-[#26262F] rounded px-2 py-1.5 text-xs text-[#F2EDE4] focus:outline-none focus:border-[#E8A33D]"
                  placeholder="Reason"
                  value={mergeReason}
                  onChange={(e) => setMergeReason(e.target.value)}
                />
                <button
                  onClick={() => act(() => deskApi.merge(story.id, Number(mergeTarget), mergeReason))}
                  disabled={acting || !mergeTarget}
                  className="btn-amber text-xs px-3"
                >Merge</button>
              </div>
            </div>
          )}

          {/* Revision history */}
          <div className="border-t border-[#26262F] pt-3 mt-2">
            <button
              onClick={() => setShowHistory((h) => !h)}
              className="text-[10px] text-[#6B6B80] uppercase tracking-wider hover:text-[#F2EDE4]"
            >
              {showHistory ? "▾" : "▸"} Revision history ({story.revisions.length})
            </button>
            {showHistory && (
              <div className="mt-2 flex flex-col gap-2">
                {[...story.revisions].reverse().map((rev) => (
                  <div key={rev.id} className="bg-[#0E0E11] rounded p-2 text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[#E8A33D]">v{rev.version}</span>
                      <Badge label={rev.kind} />
                      <span className="text-[#6B6B80]">{rev.author?.username || "system"}</span>
                      <span className="text-[#6B6B80] ml-auto">{ago(rev.created_at)}</span>
                    </div>
                    <div className="text-[#F2EDE4] font-serif">{rev.headline}</div>
                    {rev.change_note && <div className="text-[#6B6B80] mt-1 italic">{rev.change_note}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Publications */}
          {story.publications.length > 0 && (
            <div className="border-t border-[#26262F] pt-3">
              <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-2">Publications</div>
              {story.publications.map((pub) => (
                <div key={pub.id} className="flex items-center gap-2 text-xs py-1">
                  <Badge label={pub.status} />
                  <span className="text-[#6B6B80]">v{pub.version_no}</span>
                  <span className="text-[#6B6B80]">{pub.published_by.username}</span>
                  <span className="text-[#6B6B80] ml-auto">{ts(pub.published_at)}</span>
                  {pub.status === "LIVE" && story.slug && (
                    <a href={`/published/${story.slug}`} target="_blank" rel="noreferrer"
                      className="text-[#E8A33D] hover:underline">view →</a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: source items */}
      <div className="w-96 flex flex-col overflow-y-auto">
        <div className="p-4 border-b border-[#26262F] text-[10px] text-[#6B6B80] uppercase tracking-wider">
          Source items
        </div>
        <div className="flex flex-col gap-0">
          {activeItems.map((si) => (
            <div key={si.id} className="border-b border-[#26262F] p-3 hover:bg-[#1A1A20] group">
              <div className="flex items-start gap-2">
                <TierDot tier={si.item.source.trust_tier} />
                <div className="flex-1 min-w-0">
                  <div className="text-[#F2EDE4] text-xs leading-snug">{si.item.headline}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[#6B6B80] text-[10px]">{si.item.source.name}</span>
                    <Badge label={si.item.source.kind} />
                    {si.similarity_score != null && (
                      <span className="text-[10px] text-[#6B6B80]">
                        {Math.round(si.similarity_score * 100)}% match
                      </span>
                    )}
                  </div>
                  <div className="text-[#6B6B80] text-[10px] mt-0.5">{ago(si.item.received_at)}</div>
                </div>
                {["REPORTER", "EDITOR"].includes(user?.role || "") && (
                  <button
                    onClick={() => act(() => deskApi.detach(story.id, si.item.id))}
                    className="opacity-0 group-hover:opacity-100 text-[#E05252] text-[10px] hover:text-[#E05252] transition-opacity"
                    title="Detach"
                  >✕</button>
                )}
              </div>
              <div className="text-[#6B6B80] text-[10px] mt-2 leading-relaxed line-clamp-3">
                {si.item.body.slice(0, 200)}…
              </div>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        .btn-primary { background:#26262F; color:#F2EDE4; font-size:12px; padding:6px 14px; border-radius:4px; cursor:pointer; transition:background 0.15s; }
        .btn-primary:hover { background:#3A3A4A; }
        .btn-primary:disabled { opacity:0.4; cursor:not-allowed; }
        .btn-amber { background:#E8A33D; color:#0E0E11; font-size:12px; font-weight:700; padding:6px 14px; border-radius:4px; cursor:pointer; transition:background 0.15s; }
        .btn-amber:hover { background:#A8722A; }
        .btn-amber:disabled { opacity:0.4; cursor:not-allowed; }
        .btn-green { background:#4CAF7D; color:#0E0E11; font-size:12px; font-weight:700; padding:6px 14px; border-radius:4px; cursor:pointer; transition:background 0.15s; }
        .btn-green:hover { background:#3A8F62; }
        .btn-green:disabled { opacity:0.4; cursor:not-allowed; }
        .btn-red { background:#2A1A1A; color:#E05252; font-size:12px; padding:6px 14px; border-radius:4px; cursor:pointer; border:1px solid #E05252/30; transition:background 0.15s; }
        .btn-red:hover { background:#3A2020; }
        .btn-red:disabled { opacity:0.4; cursor:not-allowed; }
      `}</style>
    </div>
  );
}
