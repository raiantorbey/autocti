import { useEffect, useState } from "react";
import { startSensor, stopSensor, sensorStatus } from "../services/api";
import { subscribe } from "../services/realtime";

const STATE = {
  IDLE: "idle",
  STARTING: "starting",
  RUNNING: "running",
  STOPPING: "stopping",
  ERROR: "error",
};

export default function SensorControl() {
  const [state, setState] = useState(STATE.IDLE);
  const [mode, setMode] = useState("off");
  const [emitted, setEmitted] = useState(0);
  const [startedAt, setStartedAt] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    sensorStatus()
      .then((s) => {
        setMode(s.mode || "off");
        setEmitted(s.events_emitted || 0);
        setStartedAt(s.started_at);
        setState(s.running ? STATE.RUNNING : STATE.IDLE);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    return subscribe((msg) => {
      if (msg.topic === "sensor") {
        if (msg.action === "started") {
          setState(STATE.RUNNING);
          setMode(msg.mode || "live");
          setStartedAt(msg.started_at);
        }
        if (msg.action === "stopped") setState(STATE.IDLE);
        if (msg.action === "flow_detected") setEmitted((n) => n + 1);
      }
    });
  }, []);

  async function onStart() {
    setError(null);
    setState(STATE.STARTING);
    try {
      const r = await startSensor();
      setState(r.running ? STATE.RUNNING : STATE.ERROR);
      setMode(r.mode || "live");
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setState(STATE.ERROR);
    }
  }

  async function onStop() {
    setState(STATE.STOPPING);
    try {
      await stopSensor();
      setState(STATE.IDLE);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setState(STATE.ERROR);
    }
  }

  const running = state === STATE.RUNNING;
  const busy = state === STATE.STARTING || state === STATE.STOPPING;

  return (
    <div className="card" style={{ padding: 16, display: "flex", gap: 16, alignItems: "center" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 16 }}>Live network sensor</div>
        <div style={{ fontSize: 13, opacity: 0.75, marginTop: 4 }}>
          {running
            ? `Capturing — mode=${mode} · ${emitted} flows ingested`
            : state === STATE.ERROR
            ? `Error: ${error}`
            : "Idle. Click Start to begin capturing flows."}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        {!running ? (
          <button
            className="btn btn-primary"
            disabled={busy}
            onClick={onStart}
            aria-busy={busy}
          >
            {state === STATE.STARTING ? (
              <>
                <span className="spinner" /> Starting…
              </>
            ) : (
              "▶ Start scanning"
            )}
          </button>
        ) : (
          <button className="btn btn-danger" disabled={busy} onClick={onStop}>
            {state === STATE.STOPPING ? "Stopping…" : "■ Stop"}
          </button>
        )}
      </div>
      <Pulse on={running} />
    </div>
  );
}

function Pulse({ on }) {
  return (
    <div
      title={on ? "Live" : "Idle"}
      style={{
        width: 12,
        height: 12,
        borderRadius: 99,
        background: on ? "#22c55e" : "#475569",
        boxShadow: on ? "0 0 0 0 rgba(34,197,94,.7)" : "none",
        animation: on ? "autocti-pulse 1.4s infinite" : "none",
      }}
    />
  );
}