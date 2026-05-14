import { useEffect, useRef, useState } from "react";
import { subscribe, isConnected } from "../services/realtime";

const NODES = [
  { id: "sensor",     label: "Sensor",      x: 60,  y: 100 },
  { id: "ingest",     label: "Ingestion",   x: 200, y: 100 },
  { id: "correlate",  label: "Correlation", x: 340, y: 100 },
  { id: "score",      label: "Risk",        x: 480, y: 100 },
  { id: "explain",    label: "Explanation", x: 620, y: 100 },
  { id: "feedback",   label: "Feedback",    x: 480, y: 200 },
];

const EDGES = [
  ["sensor", "ingest"],
  ["ingest", "correlate"],
  ["correlate", "score"],
  ["score", "explain"],
  ["feedback", "score"],
];

const ACTIVITY_MS = 1200;

export default function LiveArchitecture() {
  const [active, setActive] = useState({});
  const [edgeActive, setEdgeActive] = useState({});
  const [stats, setStats] = useState({
    ingest: 0, correlate: 0, score: 0, explain: 0, feedback: 0, sensor: 0,
  });
  const [connected, setConnected] = useState(isConnected());
  const timers = useRef({});

  useEffect(() => {
    const off = subscribe((msg) => {
      if (msg.topic === "_status") {
        setConnected(msg.state === "connected");
        return;
      }
      const id = msg.topic;
      if (!NODES.find((n) => n.id === id)) return;

      setActive((s) => ({ ...s, [id]: Date.now() }));
      setStats((s) => ({ ...s, [id]: (s[id] || 0) + 1 }));

      const inEdge = EDGES.find(([, to]) => to === id);
      if (inEdge) {
        const ek = inEdge.join("→");
        setEdgeActive((s) => ({ ...s, [ek]: Date.now() }));
        clearTimeout(timers.current["e_" + ek]);
        timers.current["e_" + ek] = setTimeout(() => {
          setEdgeActive((s) => {
            const c = { ...s };
            delete c[ek];
            return c;
          });
        }, ACTIVITY_MS);
      }
      clearTimeout(timers.current["n_" + id]);
      timers.current["n_" + id] = setTimeout(() => {
        setActive((s) => {
          const c = { ...s };
          delete c[id];
          return c;
        });
      }, ACTIVITY_MS);
    });
    return off;
  }, []);

  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 16 }}>Live agent pipeline</div>
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: 99,
              background: connected ? "#22c55e" : "#ef4444",
              marginRight: 6,
            }}
          />
          {connected ? "WebSocket live" : "WebSocket offline"}
        </div>
      </div>

      <svg viewBox="0 0 720 260" style={{ width: "100%", height: 260, marginTop: 8 }}>
        {EDGES.map(([from, to]) => {
          const a = NODES.find((n) => n.id === from);
          const b = NODES.find((n) => n.id === to);
          const ek = `${from}→${to}`;
          const isActive = !!edgeActive[ek];
          return (
            <g key={ek}>
              <path
                className={`arch-edge ${isActive ? "active" : ""}`}
                d={`M${a.x + 50} ${a.y} L${b.x - 50} ${b.y}`}
              />
              {isActive && (
                <circle className="arch-flow" r="4">
                  <animateMotion
                    dur="0.9s"
                    repeatCount="1"
                    path={`M${a.x + 50} ${a.y} L${b.x - 50} ${b.y}`}
                  />
                </circle>
              )}
            </g>
          );
        })}

        {NODES.map((n) => {
          const isActive = !!active[n.id];
          return (
            <g key={n.id} className={`arch-node ${isActive ? "active" : ""}`}>
              <rect
                x={n.x - 50}
                y={n.y - 22}
                width="100"
                height="44"
                rx="10"
                fill="#131a30"
                stroke={isActive ? "#22d3ee" : "#1f2a44"}
                strokeWidth="2"
              />
              <text x={n.x} y={n.y - 2} textAnchor="middle" fill="#e5e7eb" fontSize="13" fontWeight="600">
                {n.label}
              </text>
              <text x={n.x} y={n.y + 14} textAnchor="middle" fill="#94a3b8" fontSize="11">
                {stats[n.id] || 0} hits
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}