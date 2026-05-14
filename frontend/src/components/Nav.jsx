import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { getUser, logout } from "../services/api";

export function Navbar() {
  const user = getUser();
  const nav = useNavigate();
  return (
    <nav className="bg-panel border-b border-slate-700 px-6 py-3 flex justify-between items-center">
      <div className="flex items-center gap-3">
        <div className="text-xl font-bold text-accent">AutoCTI</div>
        <span className="text-xs text-slate-400">
          Autonomous CTI · Agentic SOC
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <Link to="/" className="hover:text-accent">Incidents</Link>
        {user && (
          <>
            <span className="text-slate-400">
              {user.username} <em className="text-xs">({user.role})</em>
            </span>
            <button
              onClick={() => {
                logout();
                nav("/login");
              }}
              className="bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded"
            >
              Logout
            </button>
          </>
        )}
      </div>
    </nav>
  );
}

export function RiskBadge({ score }) {
  const s = Number(score || 0);
  const color =
    s >= 0.75 ? "bg-red-600" : s >= 0.5 ? "bg-amber-500" : s >= 0.25 ? "bg-yellow-500" : "bg-green-600";
  return (
    <span
      className={`${color} text-white text-xs font-semibold px-2 py-0.5 rounded`}
    >
      {s.toFixed(2)}
    </span>
  );
}

export function StatusPill({ status }) {
  const map = {
    open: "bg-red-700",
    triaged: "bg-amber-600",
    closed: "bg-slate-600",
  };
  return (
    <span className={`${map[status] || "bg-slate-600"} text-xs px-2 py-0.5 rounded`}>
      {status}
    </span>
  );
}
