import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { listIncidents, logout, getUser } from "../services/api";
import { subscribe } from "../services/realtime";
import SensorControl from "../components/SensorControl";
import LiveArchitecture from "../components/LiveArchitecture";

function riskClass(r) {
  if (r >= 0.7) return "btn-danger";
  if (r >= 0.4) return "btn-warn";
  return "btn-ok";
}

export default function Incidents() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const user = getUser();

  async function load() {
    try {
      const data = await listIncidents();
      setItems(data || []);
      setErr(null);
    } catch (e) {
      setErr(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    return subscribe((msg) => {
      if (["correlate", "score", "explain", "feedback"].includes(msg.topic)) {
        load();
      }
    });
  }, []);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  const isIncidentsTab = location.pathname === "/";

  return (
    <div style={{ minHeight: "100vh" }}>
      {/* Navbar */}
      <div
        style={{
          background: "#131a30",
          borderBottom: "1px solid #1f2a44",
          padding: "12px 24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>
            🛡️ AutoCTI{" "}
            <span style={{ opacity: 0.6, fontSize: 13 }}>SOC Dashboard</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => navigate("/")}
              style={{
                ...navBtn,
                color: isIncidentsTab ? "#22D3EE" : "#E5E7EB",
                borderBottom: isIncidentsTab ? "2px solid #22D3EE" : "1px solid #1F2A44",
              }}
            >
              Incidents
            </button>
            <button
              onClick={() => navigate("/events")}
              style={navBtn}
            >
              Events
            </button>
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 13, opacity: 0.75 }}>
            {user?.username} ({user?.role})
          </span>
          <button className="btn btn-warn" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </div>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>
          SOC Dashboard
        </h1>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
            marginBottom: 24,
          }}
        >
          <SensorControl />
          <LiveArchitecture />
        </div>

        <div className="card" style={{ padding: 16 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 12,
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 600 }}>
              Incidents ({items.length})
            </div>
            <button className="btn btn-primary" onClick={load}>
              ↻ Refresh
            </button>
          </div>

          {err && (
            <div style={{ color: "#ef4444", marginBottom: 12 }}>Error: {err}</div>
          )}

          {loading ? (
            <div style={{ opacity: 0.7 }}>Loading…</div>
          ) : items.length === 0 ? (
            <div style={{ opacity: 0.7, padding: 16, textAlign: "center" }}>
              No incidents yet. Click <strong>Start scanning</strong> above to
              generate live activity.
            </div>
          ) : (
            <div style={{ overflow: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", opacity: 0.75 }}>
                    <th style={th}>Risk</th>
                    <th style={th}>Title</th>
                    <th style={th}>Status</th>
                    <th style={th}>Tactics</th>
                    <th style={th}>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((inc) => (
                    <tr
                      key={inc.id}
                      onClick={() => navigate(`/incidents/${inc.id}`)}
                      style={{
                        cursor: "pointer",
                        borderTop: "1px solid #1f2a44",
                      }}
                    >
                      <td style={td}>
                        <span
                          className={`btn ${riskClass(inc.risk_score)}`}
                          style={{ padding: "2px 10px", fontSize: 13 }}
                        >
                          {Number(inc.risk_score).toFixed(2)}
                        </span>
                      </td>
                      <td style={td}>{inc.title}</td>
                      <td style={td}>{inc.status}</td>
                      <td style={td}>
                        {(inc.tactics || []).map((t) => (
                          <span
                            key={t}
                            style={{
                              display: "inline-block",
                              padding: "1px 8px",
                              marginRight: 4,
                              fontSize: 12,
                              borderRadius: 6,
                              background: "#1f2a44",
                            }}
                          >
                            {t}
                          </span>
                        ))}
                      </td>
                      <td style={td}>
                        {inc.updated_at
                          ? new Date(inc.updated_at).toLocaleString()
                          : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const th = { padding: "8px 6px", fontWeight: 600, fontSize: 13 };
const td = { padding: "10px 6px", fontSize: 14 };

const navBtn = {
  background: "transparent",
  color: "#E5E7EB",
  border: "1px solid #1F2A44",
  padding: "6px 12px",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
};