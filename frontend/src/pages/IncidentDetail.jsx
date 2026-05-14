import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactFlow, { Background, Controls, MiniMap } from "reactflow";
import "reactflow/dist/style.css";

import {
  fetchIncident,
  fetchGraph,
  fetchSimilar,
  sendFeedback,
  logout,
  getUser,
} from "../services/api";

const NODE_COLOURS = {
  Incident: "#6ee7f9",
  Event: "#f59e0b",
  IP: "#a78bfa",
};

function riskColor(r) {
  if (r >= 0.7) return "#EF4444";
  if (r >= 0.4) return "#F59E0B";
  return "#22C55E";
}

function toFlow(graph) {
  if (!graph) return { nodes: [], edges: [] };
  const nodes = (graph.nodes || []).map((n, idx) => ({
    id: n.id,
    data: { label: `${n.type}: ${n.label}` },
    position: {
      x: 120 + (idx % 6) * 180,
      y: 80 + Math.floor(idx / 6) * 120,
    },
    style: {
      background: NODE_COLOURS[n.type] || "#64748b",
      color: "#0b1020",
      border: "1px solid #1e293b",
      borderRadius: 6,
      padding: 6,
      fontSize: 12,
    },
  }));
  const edges = (graph.edges || []).map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.type,
    animated: e.type === "TARGETS",
    style: { stroke: "#475569" },
    labelStyle: { fill: "#94a3b8", fontSize: 10 },
  }));
  return { nodes, edges };
}

export default function IncidentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const user = getUser();
  const [incident, setIncident] = useState(null);
  const [graph, setGraph] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const [inc, g, sim] = await Promise.all([
      fetchIncident(id),
      fetchGraph(id).catch(() => null),
      fetchSimilar(id).catch(() => []),
    ]);
    setIncident(inc);
    setGraph(g);
    setSimilar(sim);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function verdict(v) {
    setBusy(true);
    setMsg("");
    try {
      await sendFeedback(id, v);
      setMsg(`Feedback '${v}' recorded. Weights updated.`);
      await load();
    } catch (e) {
      setMsg(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  // Inline navbar (same look as Incidents.jsx)
  const navbar = (
    <div
      style={{
        background: "#131A30",
        borderBottom: "1px solid #1F2A44",
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
        <button onClick={() => navigate("/")} style={navBtn}>
          Incidents
        </button>
        <button onClick={() => navigate("/events")} style={navBtn}>
          Events
        </button>
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
  );

  if (!incident) {
    return (
      <div style={{ minHeight: "100vh" }}>
        {navbar}
        <div style={{ padding: 24, color: "#94A3B8" }}>Loading…</div>
      </div>
    );
  }

  const flow = toFlow(graph);

  return (
    <div style={{ minHeight: "100vh" }}>
      {navbar}
      <div
        style={{
          padding: 24,
          display: "grid",
          gridTemplateColumns: "2fr 1fr",
          gap: 24,
          maxWidth: 1400,
          margin: "0 auto",
        }}
      >
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ padding: 20 }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
              <span
                style={{
                  background: riskColor(incident.risk_score),
                  color: "#0B1020",
                  padding: "3px 10px",
                  borderRadius: 4,
                  fontWeight: 700,
                  fontSize: 13,
                }}
              >
                Risk {Number(incident.risk_score).toFixed(2)}
              </span>
              <span style={{ color: "#94A3B8", fontSize: 13 }}>
                Status: {incident.status}
              </span>
              <span style={{ color: "#475569", fontSize: 11, fontFamily: "monospace" }}>
                id: {incident.id}
              </span>
            </div>
            <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>
              {incident.title}
            </h1>
            <div style={{ fontSize: 13, color: "#94A3B8", marginTop: 6 }}>
              Tactics: {(incident.tactics || []).join(", ") || "—"}
            </div>
          </div>

          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ fontWeight: 600, marginBottom: 8, marginTop: 0 }}>
              AI explanation
            </h3>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontSize: 13,
                color: "#E5E7EB",
                fontFamily: "inherit",
                margin: 0,
              }}
            >
              {incident.explanation || "(pending)"}
            </pre>
            {incident.recommended_actions?.length > 0 && (
              <>
                <h4 style={{ fontWeight: 600, marginTop: 16, marginBottom: 8 }}>
                  Recommended actions
                </h4>
                <ul style={{ marginLeft: 20, fontSize: 13, color: "#cbd5e1" }}>
                  {incident.recommended_actions.map((a, i) => (
                    <li key={i} style={{ marginBottom: 4 }}>
                      {typeof a === "string" ? a : JSON.stringify(a)}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ fontWeight: 600, marginBottom: 12, marginTop: 0 }}>
              Timeline
            </h3>
            <ol
              style={{
                position: "relative",
                borderLeft: "1px solid #334155",
                marginLeft: 12,
                listStyle: "none",
                padding: 0,
              }}
            >
              {(incident.events || [])
                .slice()
                .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
                .map((e) => (
                  <li
                    key={e.id}
                    style={{ marginLeft: 16, paddingBottom: 14, position: "relative" }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        width: 8,
                        height: 8,
                        background: "#22D3EE",
                        borderRadius: "50%",
                        left: -20,
                        top: 6,
                      }}
                    />
                    <div style={{ fontSize: 11, color: "#94A3B8" }}>
                      {new Date(e.timestamp).toLocaleString()}
                    </div>
                    <div style={{ fontWeight: 500 }}>
                      {e.event_type} — {e.src_ip} → {e.dst_ip}
                    </div>
                    <div style={{ fontSize: 13, color: "#cbd5e1" }}>
                      {e.description}
                    </div>
                  </li>
                ))}
            </ol>
          </div>

          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ fontWeight: 600, marginBottom: 8, marginTop: 0 }}>
              Analyst verdict
            </h3>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                disabled={busy}
                onClick={() => verdict("confirmed")}
                style={{ ...verdictBtn, background: "#dc2626" }}
              >
                Confirm threat
              </button>
              <button
                disabled={busy}
                onClick={() => verdict("false_positive")}
                style={{ ...verdictBtn, background: "#d97706" }}
              >
                False positive
              </button>
              <button
                disabled={busy}
                onClick={() => verdict("dismissed")}
                style={{ ...verdictBtn, background: "#475569" }}
              >
                Dismiss
              </button>
            </div>
            {msg && (
              <div style={{ fontSize: 13, color: "#94A3B8", marginTop: 8 }}>
                {msg}
              </div>
            )}
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ padding: 12, height: 420 }}>
            <h3 style={{ fontWeight: 600, marginBottom: 8, paddingLeft: 8, marginTop: 4 }}>
              Knowledge graph
            </h3>
            <div style={{ height: 370 }}>
              {flow.nodes.length > 0 ? (
                <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView>
                  <Background color="#1e293b" />
                  <MiniMap pannable />
                  <Controls />
                </ReactFlow>
              ) : (
                <div style={{ color: "#64748b", fontSize: 13, padding: 16 }}>
                  Graph data unavailable (Neo4j offline or empty).
                </div>
              )}
            </div>
          </div>

          <div
    className="card"
    style={{
      padding: 0,
      display: "flex",
      flexDirection: "column",
      height: 500,
      overflow: "hidden",
    }}
  >
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #1F2A44" }}>
        <h3 style={{ fontWeight: 600, margin: 0, fontSize: 15 }}>
          Knowledge graph{" "}
          <span style={{ color: "#94A3B8", fontSize: 12, fontWeight: 400 }}>
            ({flow.nodes.length} nodes, {flow.edges.length} edges)
          </span>
        </h3>
      </div>
      <div style={{ flex: 1, position: "relative", background: "#0B1020" }}>
        {flow.nodes.length > 0 ? (
          <ReactFlow
            nodes={flow.nodes}
            edges={flow.edges}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.1}
            maxZoom={2}
            style={{ width: "100%", height: "100%" }}
          >
            <Background color="#1e293b" gap={16} />
            <MiniMap
              pannable
              zoomable
              style={{ background: "#131A30" }}
              nodeColor="#22D3EE"
            />
            <Controls />
          </ReactFlow>
        ) : (
          <div style={{ color: "#64748b", fontSize: 13, padding: 16 }}>
            Graph data unavailable (Neo4j offline or empty).
          </div>
        )}
      </div>
    </div>
        </div>
      </div>
    </div>
  );
}

const navBtn = {
  background: "transparent",
  color: "#E5E7EB",
  border: "1px solid #1F2A44",
  padding: "6px 12px",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
};

const verdictBtn = {
  color: "#fff",
  border: "none",
  padding: "8px 16px",
  borderRadius: 6,
  fontSize: 13,
  fontWeight: 500,
  cursor: "pointer",
};