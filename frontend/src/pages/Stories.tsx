import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deskApi, Story } from "../lib/api";
import { Badge, Spinner, ErrorMsg, ago } from "../components/ui";
import { useAuth } from "../hooks/useAuth";

const STATUSES = ["NEW", "DRAFT", "IN_REVIEW", "PUBLISHED", "SPIKED"];

export default function Stories() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    deskApi.stories(filter || undefined)
      .then(setStories)
      .catch(() => setError("Failed to load stories."))
      .finally(() => setLoading(false));
  }, [filter]);

  const visible = stories.filter((s) =>
    !filter || s.status === filter
  );

  // Group by status for lane view
  const lanes = filter
    ? { [filter]: visible }
    : Object.fromEntries(
        STATUSES.map((st) => [st, stories.filter((s) => s.status === st)])
      );

  if (loading) return <Spinner />;

  return (
    <div className="p-6">
      <div className="flex items-center gap-4 mb-6">
        <h1 className="text-[#E8A33D] font-mono text-lg uppercase tracking-widest">Stories</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setFilter("")}
            className={`text-[10px] uppercase px-2 py-1 rounded transition-colors ${
              !filter ? "bg-[#E8A33D] text-[#0E0E11]" : "text-[#6B6B80] hover:text-[#F2EDE4]"
            }`}
          >
            All
          </button>
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s === filter ? "" : s)}
              className={`text-[10px] uppercase px-2 py-1 rounded transition-colors ${
                filter === s ? "bg-[#E8A33D] text-[#0E0E11]" : "text-[#6B6B80] hover:text-[#F2EDE4]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorMsg msg={error} />}

      <div className={`grid gap-4 ${filter ? "grid-cols-1 max-w-2xl" : "grid-cols-5"}`}>
        {Object.entries(lanes).map(([status, items]) => (
          <div key={status}>
            {!filter && (
              <div className="text-[10px] uppercase tracking-wider text-[#6B6B80] mb-2 flex items-center gap-2">
                {status}
                <span className="text-[#26262F]">({items.length})</span>
              </div>
            )}
            <div className="flex flex-col gap-2">
              {items.map((story) => (
                <div
                  key={story.id}
                  onClick={() => navigate(`/stories/${story.id}`)}
                  className="bg-[#1A1A20] border border-[#26262F] rounded p-3 cursor-pointer hover:border-[#E8A33D]/40 transition-colors"
                >
                  <div className="text-[#F2EDE4] text-xs leading-snug mb-2 line-clamp-2">
                    {story.latest_headline}
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <Badge label={story.status} />
                    {story.cluster_confidence != null && (
                      <span className="text-[10px] text-[#6B6B80]">
                        {Math.round(story.cluster_confidence * 100)}%
                      </span>
                    )}
                    <span className="text-[10px] text-[#6B6B80] ml-auto">
                      {story.item_count} src · {ago(story.created_at)}
                    </span>
                  </div>
                  {story.assigned_to && (
                    <div className="text-[10px] text-[#6B6B80] mt-1">
                      → {story.assigned_to.username}
                    </div>
                  )}
                </div>
              ))}
              {items.length === 0 && (
                <div className="text-[#26262F] text-[10px] text-center py-4">empty</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
