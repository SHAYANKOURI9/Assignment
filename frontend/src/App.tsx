import { Navigate, Route, Routes } from "react-router-dom";
import Nav from "./components/Nav";
import { Spinner } from "./components/ui";
import { useAuth } from "./hooks/useAuth";
import Desk from "./pages/Desk";
import Inbox from "./pages/Inbox";
import Ingest from "./pages/Ingest";
import Login from "./pages/Login";
import PublishedBrief from "./pages/PublishedBrief";
import Stories from "./pages/Stories";
import StoryWorkspace from "./pages/StoryWorkspace";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;

  return <>{children}</>;
}

function AppShell() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-[#0E0E11] text-[#F2EDE4]">
      {user && <Nav />}
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/published/:slug" element={<PublishedBrief />} />
        <Route path="/" element={<RequireAuth><Navigate to="/stories" replace /></RequireAuth>} />
        <Route path="/inbox" element={<RequireAuth><Inbox /></RequireAuth>} />
        <Route path="/stories" element={<RequireAuth><Stories /></RequireAuth>} />
        <Route path="/stories/:id" element={<RequireAuth><StoryWorkspace /></RequireAuth>} />
        <Route path="/ingest" element={<RequireAuth><Ingest /></RequireAuth>} />
        <Route path="/desk" element={<RequireAuth><Desk /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/stories" replace />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return <AppShell />;
}
