import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { deskApi, StoryDetail } from "../lib/api";
import { Badge, Spinner, ErrorMsg, ts } from "../components/ui";

export default function PublishedBrief() {
  const { slug } = useParams<{ slug: string }>();
  const [story, setStory] = useState<StoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    deskApi.published(slug!)
      .then(setStory)
      .catch(() => setError("Brief not found."))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <Spinner />;
  if (error || !story) return <ErrorMsg msg={error || "Not found"} />;

  const livePub = story.publications.find((p) => p.status === "LIVE");
  const corrections = story.publications.filter((p) => p.status === "CORRECTED");
  const superseded = story.publications.filter((p) => p.status === "SUPERSEDED");
  const mergeNote = story.revisions.find((r) => r.kind === "MERGE_NOTE");

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Status notices */}
      {corrections.length > 0 && (
        <div className="mb-4 text-xs text-[#E8A33D] bg-[#2A2A1A] border border-[#E8A33D]/30 rounded px-3 py-2">
          ✎ Corrected · {ts(corrections[corrections.length - 1].published_at)}
        </div>
      )}
      {mergeNote && (
        <div className="mb-4 text-xs text-[#6B6B80] bg-[#1A1A20] border border-[#26262F] rounded px-3 py-2">
          ⇄ {mergeNote.change_note}
        </div>
      )}

      {livePub && (
        <>
          <h1 className="font-serif text-2xl text-[#F2EDE4] leading-tight mb-4">
            {livePub.revision.headline}
          </h1>
          <div className="text-[#B8B0A4] text-sm leading-relaxed mb-6 whitespace-pre-wrap">
            {livePub.revision.body}
          </div>
        </>
      )}

      <div className="border-t border-[#26262F] pt-4">
        <div className="text-[10px] text-[#6B6B80] uppercase tracking-wider mb-3">Sources</div>
        <div className="flex flex-col gap-2">
          {story.story_items.filter((si) => !si.detached_at).map((si) => (
            <div key={si.id} className="flex items-center gap-2 text-xs">
              <Badge label={si.item.source.kind} />
              <span className="text-[#B8B0A4]">{si.item.source.name}</span>
              {si.item.url && (
                <a href={si.item.url} target="_blank" rel="noreferrer"
                  className="text-[#6B6B80] hover:text-[#E8A33D] ml-auto">↗</a>
              )}
            </div>
          ))}
        </div>
      </div>

      {livePub && (
        <div className="mt-4 text-[10px] text-[#6B6B80]">
          Published {ts(livePub.published_at)} by {livePub.published_by.username}
          {livePub.version_no > 1 && ` · version ${livePub.version_no}`}
        </div>
      )}
    </div>
  );
}
