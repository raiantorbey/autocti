import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listEvents, logout, getUser } from "../services/api";

const PAGE_SIZE = 50;

function severityBadge(sev) {
  if (sev >= 0.7) return { color: "#EF4444", label: "HIGH" };
  if (sev >= 0.4) return { color: "#F59E0B", label: "MED" };
  return { color: "#22C55E", label: "LOW" };
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function Events() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters (committed values used in API call)
  const [filters, setFilters] = useState({
    q: "",
    severityMin: "",
    severityMax: "",
    srcIp: "",
    eventType: "",
    source: "",
    since: "",
    until: "",
    sort: "timestamp",
    order: "desc",
  });
  // Draft values (typed in inputs, applied on Apply / Enter)
  const [draft, setDraft] = useState(filters);

  const navigate = useNavigate();
  const user = getUser();

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const params = useMemo(() => {
    const p = { limit: PAGE_SIZE, offset, ...filters };
    // strip empty
    Object.keys(p).forEach((k) => p[k] === "" && delete p[k]);
    // coerce numerics
    if (p.severityMin !== undefined) p.severityMin = Number(p.severityMin);
    if (p.severityMax !== undefined) p.severityMax = Number(p.severityMax);
    return p;
  }, [filters, offset]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listEvents(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [params]);

  function applyFilters() {
    setOffset(0);
    setFilters(draft);
  }

  function clearFilters() {
    const cleared = {
      q: "", severityMin: "", severityMax: "",
      srcIp: "", eventType: "", source: "",
      since: "", until: "",
      sort: "timestamp", order: "desc",
    };
    setDraft(cleared);
    setFilters(cleared);
    setOffset(0);
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div style={{ minHeight: "100vh" }}>
      {/* Navbar */}
      <div
        style={{
          background: "#131A30", borderBottom: "1px solid #1F2A44",
          padding: "12px 24px", display: "flex",
          justifyContent: "space-between", alignItems: "center",
        }}
      >
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>
            🛡️ AutoCTI <span style={{ opacity: 0.6, fontSize: 13 }}>SOC Dashboard</span>
          </div>
          <button className="btn" onClick={() => navigate("/")} style={navBtn}>Incidents</button>
          <button className="btn" style={{ ...navBtn, color: "#22D3EE", borderBottom: "2px solid #22D3EE" }}>
            Events
          </button>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 13, opacity: 0.75 }}>
            {user?.username} ({user?.role})
          </span>
          <button className="btn btn-warn" onClick={handleLogout}>Logout</button>
        </div>
      </div>

      <div style={{ maxWidth: 1400, margin: "0 auto", padding: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>Events</h1>

        {/* Filter bar */}
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
            <input
              className="input"
              placeholder="Search (description, IP, type)…"
              value={draft.q}
              onChange={(e) => setDraft({ ...draft, q: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && applyFilters()}
            />
            <input
              className="input" placeholder="Source IP" value={draft.srcIp}
              onChange={(e) => setDraft({ ...draft, srcIp: e.target.value })}
            />
            <input
              className="input" placeholder="Event type (port_scan, …)"
              value={draft.eventType}
              onChange={(e) => setDraft({ ...draft, eventType: e.target.value })}
            />
            <input
              className="input" placeholder="Source (suricata, …)"
              value={draft.source}
              onChange={(e) => setDraft({ ...draft, source: e.target.value })}
            />
            <input
              className="input" type="number" step="0.1" min="0" max="1"
              placeholder="Sev min" value={draft.severityMin}
              onChange={(e) => setDraft({ ...draft, severityMin: e.target.value })}
            />
            <input
              className="input" type="number" step="0.1" min="0" max="1"
              placeholder="Sev max" value={draft.severityMax}
              onChange={(e) => setDraft({ ...draft, severityMax: e.target.value })}
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr 1fr", gap: 10 }}>
            <input
              className="input" type="datetime-local" placeholder="Since"
              value={draft.since}
              onChange={(e) => setDraft({ ...draft, since: e.target.value })}
            />
            <input
              className="input" type="datetime-local" placeholder="Until"
              value={draft.until}
              onChange={(e) => setDraft({ ...draft, until: e.target.value })}
            />
            <select
              className="input" value={draft.sort}
              onChange={(e) => setDraft({ ...draft, sort: e.target.value })}
            >
              <option value="timestamp">Sort: time</option>
              <option value="severity">Sort: severity</option>
            </select>
            <select
              className="input" value={draft.order}
              onChange={(e) => setDraft({ ...draft, order: e.target.value })}
            >
              <option value="desc">Newest first</option>
              <option value="asc">Oldest first</option>
            </select>
            <button className="btn btn-primary" onClick={applyFilters}>Apply</button>
            <button className="btn" style={navBtn} onClick={clearFilters}>Clear</button>
          </div>
        </div>

        {/* Result count + page nav */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div style={{ fontSize: 13, color: "#94A3B8" }}>
            {loading ? "Loading…" : `${total.toLocaleString()} events · page ${currentPage} of ${totalPages}`}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn"
              style={navBtn}
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              ← Prev
            </button>
            <button
              className="btn"
              style={navBtn}
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </div>

        {error && (
          <div className="card" style={{ padding: 12, color: "#EF4444", marginBottom: 12 }}>
            Error: {error}
          </div>
        )}

        {/* Table */}
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#0B1020", color: "#94A3B8" }}>
                <th style={th}>Time</th>
                <th style={th}>Severity</th>
                <th style={th}>Type</th>
                <th style={th}>Source</th>
                <th style={th}>Src IP</th>
                <th style={th}>Dst IP</th>
                <th style={th}>Description</th>
                <th style={th}>Incident</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={8} style={{ padding: 24, textAlign: "center", color: "#94A3B8" }}>
                    No events match the current filters.
                  </td>
                </tr>
              )}
              {items.map((e) => {
                const b = severityBadge(e.severity);
                return (
                  <tr key={e.id} style={{ borderTop: "1px solid #1F2A44" }}>
                    <td style={td}>{formatTime(e.timestamp)}</td>
                    <td style={td}>
                      <span style={{
                        background: b.color, color: "#0B1020",
                        padding: "2px 8px", borderRadius: 4, fontWeight: 600, fontSize: 11,
                      }}>
                        {b.label} {e.severity?.toFixed(2)}
                      </span>
                    </td>
                    <td style={td}><code style={{ color: "#22D3EE" }}>{e.event_type}</code></td>
                    <td style={td}>{e.source}</td>
                    <td style={td}><code>{e.src_ip || "—"}</code></td>
                    <td style={td}><code>{e.dst_ip || "—"}</code></td>
                    <td style={{ ...td, maxWidth: 360, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {e.description}
                    </td>
                    <td style={td}>
                      {e.incident_id ? (
                        <button
                          onClick={() => navigate(`/incidents/${e.incident_id}`)}
                          style={{ background: "transparent", border: "none", color: "#22D3EE", cursor: "pointer", fontSize: 13 }}
                        >
                          view →
                        </button>
                      ) : (
                        <span style={{ color: "#475569" }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Bottom pagination */}
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
          <button className="btn" style={navBtn} disabled={offset === 0} onClick={() => setOffset(0)}>« First</button>
          <button className="btn" style={navBtn} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Prev</button>
          <button className="btn" style={navBtn} disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next →</button>
          <button className="btn" style={navBtn} disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((totalPages - 1) * PAGE_SIZE)}>Last »</button>
        </div>
      </div>
    </div>
  );
}

const th = { padding: "10px 12px", textAlign: "left", fontWeight: 600, fontSize: 11, letterSpacing: 1 };
const td = { padding: "10px 12px", verticalAlign: "middle" };
const navBtn = {
  background: "transparent",
  color: "#E5E7EB",
  border: "1px solid #1F2A44",
  padding: "6px 12px",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
};