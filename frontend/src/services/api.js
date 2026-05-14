import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("autocti_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("autocti_token");
      localStorage.removeItem("autocti_user");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

// --- auth ---
export async function login(username, password) {
  const body = new URLSearchParams({ username, password });
  const r = await axios.post(`${API_BASE}/auth/login`, body, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  localStorage.setItem("autocti_token", r.data.access_token);
  localStorage.setItem("autocti_user", JSON.stringify(r.data.user));
  return r.data;
}

export function logout() {
  localStorage.removeItem("autocti_token");
  localStorage.removeItem("autocti_user");
}

export function getUser() {
  const raw = localStorage.getItem("autocti_user");
  return raw ? JSON.parse(raw) : null;
}

export function isAuthed() {
  return !!localStorage.getItem("autocti_token");
}

// --- incidents (with ETag-aware caching) ---
let _incidentsEtag = null;
let _incidentsCache = [];

export const listIncidents = async (status) => {
  try {
    const r = await api.get("/incidents", {
      params: status ? { status } : {},
      headers: _incidentsEtag ? { "If-None-Match": _incidentsEtag } : {},
      validateStatus: (s) => s === 200 || s === 304,
    });
    if (r.status === 304) return _incidentsCache;
    if (r.headers.etag) _incidentsEtag = r.headers.etag;
    _incidentsCache = r.data;
    return r.data;
  } catch (e) {
    if (e?.response?.status === 304) return _incidentsCache;
    throw e;
  }
};

export const getIncident = (id) =>
  api.get(`/incidents/${id}`).then((r) => r.data);

export const getSimilar = (id, k = 5) =>
  api.get(`/incidents/${id}/similar`, { params: { k } }).then((r) => r.data);

export const ingestEvent = (payload) =>
  api.post("/events/ingest", payload).then((r) => r.data);

// --- events (paginated, filterable, sortable) ---
/**
 * @param {object} params
 *   limit         {number} default 50
 *   offset        {number} default 0
 *   severityMin   {number} 0..1
 *   severityMax   {number} 0..1
 *   srcIp         {string}
 *   dstIp         {string}
 *   eventType     {string}
 *   source        {string}
 *   since         {string ISO 8601}
 *   until         {string ISO 8601}
 *   q             {string} free-text search
 *   sort          {"timestamp"|"severity"}  default "timestamp"
 *   order         {"asc"|"desc"} default "desc"
 */
export const listEvents = (params = {}) => {
  // remap camelCase -> snake_case query params expected by backend
  const remap = {
    severityMin: "severity_min",
    severityMax: "severity_max",
    srcIp: "src_ip",
    dstIp: "dst_ip",
    eventType: "event_type",
  };
  const out = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    out[remap[k] || k] = v;
  }
  return api.get("/events", { params: out }).then((r) => r.data);
};

// --- feedback ---
export const submitFeedback = (incidentId, verdict, notes = "") =>
  api.post(`/feedback/${incidentId}`, { verdict, notes }).then((r) => r.data);

// --- graph ---
export const getIncidentGraph = (id) =>
  api.get(`/graph/incident/${id}`).then((r) => r.data);

// Backward-compat alias
export const fetchGraph = getIncidentGraph;
// --- admin ---
export const getWeights = () => api.get("/admin/weights").then((r) => r.data);
export const setWeights = (w) =>
  api.put("/admin/weights", w).then((r) => r.data);

// --- sensor controls ---
export const startSensor  = () => api.post("/sensor/start").then((r) => r.data);
export const stopSensor   = () => api.post("/sensor/stop").then((r) => r.data);
export const sensorStatus = () => api.get("/sensor/status").then((r) => r.data);

// ============================================================
// Backward-compat aliases — keep older components working
// ============================================================
export const fetchIncidents      = listIncidents;
export const fetchIncident       = getIncident;
export const fetchSimilar        = getSimilar;
export const fetchEvents         = listEvents;
export const postFeedback        = submitFeedback;
export const sendFeedback        = submitFeedback;
export const fetchWeights        = getWeights;
export const updateWeights       = setWeights;

export default api;