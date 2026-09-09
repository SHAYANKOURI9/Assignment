import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const links = [
  { to: "/inbox", label: "Inbox", roles: ["REPORTER", "EDITOR"] },
  { to: "/stories", label: "Stories", roles: ["REPORTER", "EDITOR"] },
  { to: "/ingest", label: "Ingest", roles: ["REPORTER", "EDITOR"] },
  { to: "/desk", label: "Dashboard", roles: ["DESK_HEAD", "EDITOR"] },
];

export default function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <nav className="flex items-center gap-6 px-6 py-3 bg-[#1A1A20] border-b border-[#26262F] sticky top-0 z-50">
      <span className="text-[#E8A33D] font-mono font-bold tracking-widest text-sm uppercase">
        Brief Desk
      </span>
      <div className="flex gap-4 flex-1">
        {links
          .filter((l) => !user || l.roles.includes(user.role))
          .map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `text-xs uppercase tracking-wider transition-colors ${
                  isActive ? "text-[#E8A33D]" : "text-[#6B6B80] hover:text-[#F2EDE4]"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
      </div>
      {user && (
        <div className="flex items-center gap-3 text-xs text-[#6B6B80]">
          <span>{user.username}</span>
          <span className="text-[#26262F]">·</span>
          <span className="text-[#E8A33D] uppercase text-[10px]">{user.role}</span>
          <button
            onClick={handleLogout}
            className="text-[#6B6B80] hover:text-[#E05252] transition-colors ml-2"
          >
            sign out
          </button>
        </div>
      )}
    </nav>
  );
}
