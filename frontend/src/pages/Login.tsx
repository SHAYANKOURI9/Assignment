import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { authApi } from "../lib/api";

const DEMO_USERS = [
  { username: "reporter", label: "Reporter", role: "REPORTER" },
  { username: "editor", label: "Editor", role: "EDITOR" },
  { username: "deskhead", label: "Desk Head", role: "DESK_HEAD" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const doLogin = async (u: string, p: string) => {
    setLoading(true);
    setError("");
    try {
      await login(u, p);
      navigate("/stories");
    } catch {
      setError("Invalid credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0E0E11]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-[#E8A33D] text-2xl font-mono font-bold tracking-widest uppercase mb-1">
            Brief Desk
          </div>
          <div className="text-[#6B6B80] text-xs">News desk workflow system</div>
        </div>

        <div className="bg-[#1A1A20] border border-[#26262F] rounded p-6 mb-4">
          <form
            onSubmit={(e) => { e.preventDefault(); doLogin(username, password); }}
            className="flex flex-col gap-3"
          >
            <input
              className="bg-[#0E0E11] border border-[#26262F] rounded px-3 py-2 text-sm text-[#F2EDE4] placeholder-[#6B6B80] focus:outline-none focus:border-[#E8A33D]"
              placeholder="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
            <input
              type="password"
              className="bg-[#0E0E11] border border-[#26262F] rounded px-3 py-2 text-sm text-[#F2EDE4] placeholder-[#6B6B80] focus:outline-none focus:border-[#E8A33D]"
              placeholder="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && <div className="text-[#E05252] text-xs">{error}</div>}
            <button
              type="submit"
              disabled={loading}
              className="bg-[#E8A33D] text-[#0E0E11] font-bold text-sm py-2 rounded hover:bg-[#A8722A] transition-colors disabled:opacity-50"
            >
              {loading ? "signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <div className="bg-[#1A1A20] border border-[#26262F] rounded p-4">
          <div className="text-[#6B6B80] text-[10px] uppercase tracking-wider mb-3">
            One-click demo sign-in
          </div>
          <div className="flex gap-2">
            {DEMO_USERS.map((u) => (
              <button
                key={u.username}
                onClick={() => doLogin(u.username, "demo")}
                disabled={loading}
                className="flex-1 text-xs py-2 px-3 bg-[#26262F] hover:bg-[#E8A33D] hover:text-[#0E0E11] text-[#F2EDE4] rounded transition-colors disabled:opacity-50"
              >
                <div className="font-bold">{u.label}</div>
                <div className="text-[10px] opacity-60">{u.username}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
