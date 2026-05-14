import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../services/api";

export default function LoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(username, password);
      nav("/");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      <form
        onSubmit={submit}
        className="bg-panel border border-slate-700 p-8 rounded-lg w-96 shadow-lg"
      >
        <h1 className="text-2xl font-bold mb-1 text-accent">AutoCTI</h1>
        <p className="text-sm text-slate-400 mb-6">SOC analyst console</p>

        <label className="block text-xs mb-1 text-slate-400">Username</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 mb-4"
          required
        />

        <label className="block text-xs mb-1 text-slate-400">Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 mb-4"
          required
        />

        {err && <div className="text-red-400 text-sm mb-3">{err}</div>}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-accent text-slate-900 font-semibold py-2 rounded hover:bg-cyan-300 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-xs text-slate-500 mt-4">
          Default admin: <code>admin / admin123</code> (change via{" "}
          <code>create_admin.py</code>)
        </p>
      </form>
    </div>
  );
}
