import { type KeyboardEvent } from "react";
import { useMissionStore } from "../store/missionStore";
import { useCommandAgent } from "../hooks/useCommandAgent";
import { useCouncilStream } from "../hooks/useCouncilStream";
import type { LandingSite } from "../types";

// ── Scan trigger ──────────────────────────────────────────────────────────────
async function triggerScan() {
  const store = useMissionStore.getState();
  if (store.isScanning) return;
  store.setIsScanning(true);
  store.setScanError(null);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90_000);

  try {
    const res = await fetch("/api/scan-zones", { method: "POST", signal: controller.signal });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `Server error ${res.status}` }));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    const report = await res.json();
    store.setScanReport(report);
  } catch (e: unknown) {
    const msg =
      e instanceof Error && e.name === "AbortError"
        ? "Scan timed out (90 s) — server may be overloaded, try again"
        : e instanceof Error
          ? e.message
          : "Scan failed — check the console for details";
    store.setScanError(msg);
    console.error("Scan failed:", e);
  } finally {
    clearTimeout(timeoutId);
    store.setIsScanning(false);
  }
}

// ── Score bar + label ─────────────────────────────────────────────────────────
function MetricBar({ label, value, max = 100, color, suffix = "%" }: {
  label: string; value: number; max?: number; color: string; suffix?: string;
}) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <span className="text-[11px] text-slate-400 font-mono uppercase tracking-wider">{label}</span>
        <span className="text-xs text-white font-mono font-semibold tabular-nums">
          {value.toFixed(1)}{suffix}
        </span>
      </div>
      <div className="score-bar-track">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ── Site telemetry card (3 metric cards) ─────────────────────────────────────
function TelemetryCard({ icon, label, primary, secondary, color }: {
  icon: string; label: string; primary: string; secondary: string; color: string;
}) {
  return (
    <div
      className="rounded-lg p-3 border"
      style={{ borderColor: `${color}25`, background: `${color}08` }}
    >
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-[10px] font-mono" style={{ color }}>{icon}</span>
        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-sm font-semibold text-white font-mono tabular-nums">{primary}</div>
      <div className="text-[10px] text-slate-500 font-mono mt-0.5">{secondary}</div>
    </div>
  );
}

// ── Selected site detail ──────────────────────────────────────────────────────
function SiteCard({ site }: { site: LandingSite }) {
  const verdictColor =
    site.survival_score >= 65 ? "#22c55e" :
    site.survival_score >= 40 ? "#f59e0b" : "#ef4444";
  const verdictLabel =
    site.survival_score >= 65 ? "GO" :
    site.survival_score >= 40 ? "CAUTION" : "NO-GO";

  return (
    <div className="space-y-3 animate-slide-up">
      {/* Site header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider mb-0.5">Selected Site</div>
          <div className="text-sm font-semibold text-white font-display leading-tight" style={{ letterSpacing: "-0.01em" }}>
            {site.name}
          </div>
          <div className="text-[11px] text-slate-500 font-mono tabular-nums mt-0.5">
            {site.lat.toFixed(2)}°S · {site.lon.toFixed(2)}°E · {site.elev_m.toFixed(0)} m
          </div>
        </div>
        <div
          className="shrink-0 px-2 py-1 rounded text-[10px] font-bold font-mono border mt-0.5"
          style={{ color: verdictColor, borderColor: `${verdictColor}50`, background: `${verdictColor}15` }}
        >
          {verdictLabel}
        </div>
      </div>

      {/* Composite score bar */}
      <div className="border-t border-lunar-border/60 pt-3">
        <MetricBar label="Survival Score" value={site.survival_score} color={verdictColor} suffix="" />
      </div>

      {/* 3 telemetry cards */}
      <div className="grid grid-cols-1 gap-2">
        <TelemetryCard
          icon="☀"
          label="Solar Illumination"
          primary={`${site.solar_power_pct.toFixed(1)}%`}
          secondary={`Max darkness: ${site.longest_darkness_hrs}h consecutive`}
          color="#f59e0b"
        />
        <TelemetryCard
          icon="◎"
          label="Earth DTE Comms"
          primary={`${site.dte_comms_pct.toFixed(1)}%`}
          secondary={`Max blackout: ${site.longest_blackout_hrs}h consecutive`}
          color="#06b6d4"
        />
        <TelemetryCard
          icon="▲"
          label="Terrain Safety"
          primary={`${site.terrain_slope_deg.toFixed(1)}° slope`}
          secondary={`Elevation: ${site.elev_m.toFixed(0)} m above datum`}
          color={site.terrain_slope_deg > 15 ? "#ef4444" : site.terrain_slope_deg > 10 ? "#f59e0b" : "#22c55e"}
        />
      </div>
    </div>
  );
}

// ── Candidate site list ───────────────────────────────────────────────────────
function SiteSelector() {
  const { sites, selectedSite, selectSite } = useMissionStore();
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2">
        Artemis Candidate Sites
      </div>
      {sites.map((site) => {
        const isSelected = selectedSite?.site_id === site.site_id;
        const score = site.survival_score;
        const scoreColor =
          score === 0 ? "#ef4444" :
          score >= 40 ? "#22c55e" : "#f59e0b";
        const isPSR = site.longest_darkness_hrs >= 700;

        return (
          <button
            key={site.site_id}
            onClick={() => selectSite(site)}
            className={`w-full text-left px-3 py-2.5 rounded-lg transition-all border
                        ${isSelected
                          ? "border-lunar-accent/60 bg-lunar-accent/10 text-white"
                          : "border-lunar-border/60 hover:border-lunar-accent/30 hover:bg-white/[0.02] text-slate-300"}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs truncate font-prose">{site.name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                {isPSR && (
                  <span className="text-[9px] font-mono font-semibold px-1 py-0.5 rounded"
                    style={{ color: "#ef4444", background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)" }}>
                    PSR
                  </span>
                )}
                <span className="text-xs font-mono font-semibold tabular-nums" style={{ color: scoreColor }}>
                  {score.toFixed(0)}
                </span>
              </div>
            </div>
            {/* Score bar */}
            <div className="score-bar-track mt-1.5">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, score)}%`, backgroundColor: scoreColor }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ── Main HUD ──────────────────────────────────────────────────────────────────
export default function MissionControlHUD() {
  const {
    selectedSite, terrainFallback, commandInput, commandLoading,
    setCommandInput, isScanning, lastCommand, scanError, scanReport,
  } = useMissionStore();

  const { sendCommand } = useCommandAgent();
  const { triggerCouncil } = useCouncilStream();

  const handleCommand = async () => {
    if (!commandInput.trim() || commandLoading) return;
    await sendCommand(commandInput);
    setCommandInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleCommand();
  };

  return (
    <>
      {/* ── Top Bar ─────────────────────────────────────────────────── */}
      <div className="absolute top-0 left-0 right-0 z-10 glass-panel border-b border-slate-400/15">
        <div className="flex items-center gap-4 px-4 py-2.5">
          {/* Logo */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-lunar-accent font-display font-semibold text-sm tracking-tight" style={{ letterSpacing: "-0.02em" }}>
              SELENE SCOUT
            </span>
            {isScanning && (
              <span className="text-[10px] text-caution-amber font-mono animate-pulse">
                · SCANNING
              </span>
            )}
          </div>

          {/* Centre readout: command response → selected site → idle hint */}
          <div className="flex-1 text-center text-xs font-mono text-slate-400 tabular-nums truncate px-2">
            {commandLoading ? (
              <span className="text-lunar-accent animate-pulse">Parsing command…</span>
            ) : lastCommand?.response_text ? (
              <span className="text-slate-200 font-prose">{lastCommand.response_text}</span>
            ) : selectedSite ? (
              <span>
                <span className="text-slate-200 font-prose font-medium">{selectedSite.name}</span>
                <span className="text-slate-500 mx-1.5">·</span>
                {selectedSite.lat.toFixed(2)}°S, {selectedSite.lon.toFixed(2)}°E
                <span className="text-slate-500 mx-1.5">·</span>
                {selectedSite.elev_m.toFixed(0)} m
              </span>
            ) : (
              <span className="text-slate-500">Select a landing site or type a command below</span>
            )}
          </div>

          {/* Terrain fallback warning */}
          {terrainFallback && (
            <div className="shrink-0 text-[10px] font-mono text-caution-amber border border-caution-amber/25 rounded px-2 py-0.5">
              ⚠ No terrain DEM
            </div>
          )}

          {/* Council trigger */}
          {selectedSite && (
            <button
              onClick={() => triggerCouncil(selectedSite.site_id)}
              className="shrink-0 px-3 py-1.5 text-xs rounded
                         bg-lunar-accent/15 hover:bg-lunar-accent/30
                         border border-lunar-accent/35 text-lunar-accent
                         transition-colors font-mono"
            >
              Mission Council
            </button>
          )}
        </div>
      </div>

      {/* ── Right Drawer ────────────────────────────────────────────── */}
      <div className="absolute top-11 right-0 bottom-14 z-10 w-72
                      glass-panel hud-reticle border-l border-slate-400/15 overflow-y-auto">
        <div className="p-4 space-y-5">

          {/* Scan CTA */}
          <button
            onClick={triggerScan}
            disabled={isScanning}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg
                       border border-lunar-accent/35 bg-lunar-accent/10
                       hover:bg-lunar-accent/20 hover:border-lunar-accent/55
                       text-xs text-lunar-accent font-mono
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-all duration-200"
          >
            {isScanning ? (
              <>
                <span className="w-3 h-3 border border-lunar-accent border-t-transparent rounded-full animate-spin" />
                Scanning 48 zones…
              </>
            ) : (
              <>
                <span className="radar-sweep inline-block text-[10px]">◈</span>
                Scan 48 Candidate Zones (AI)
              </>
            )}
          </button>

          {/* Scan error */}
          {scanError && (
            <div className="rounded-lg px-3 py-2.5 border border-red-500/30 bg-red-500/10 text-[11px] font-mono text-red-400 leading-relaxed">
              <span className="text-red-500 font-semibold">SCAN ERROR</span>
              <br />
              {scanError}
            </div>
          )}

          {/* Scan results */}
          {scanReport && !isScanning && (
            <div className="space-y-2">
              <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">
                AI Scan — Top 3 Zones
              </div>
              {scanReport.top_sites.map((site) => (
                <div
                  key={site.rank}
                  className="rounded-lg p-3 border border-lunar-border/60 bg-white/[0.02] space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
                      #{site.rank}
                    </span>
                    <span
                      className="text-xs font-mono font-semibold tabular-nums"
                      style={{ color: site.rank === 1 ? "#ffd700" : site.rank === 2 ? "#c0c0c0" : "#cd7f32" }}
                    >
                      {site.overall_score.toFixed(0)} / 100
                    </span>
                  </div>
                  <div className="text-xs font-semibold text-white font-display truncate">{site.site_id}</div>
                  <div className="text-[10px] font-mono text-slate-500 tabular-nums">
                    {site.lat.toFixed(2)}°S · {site.lon.toFixed(2)}°E
                  </div>
                  <div className="text-[10px] font-prose text-slate-400 leading-tight">{site.key_advantage}</div>
                </div>
              ))}
              {scanReport.mission_summary && (
                <div className="text-[10px] font-prose text-slate-500 leading-relaxed px-1">
                  {scanReport.mission_summary}
                </div>
              )}
            </div>
          )}

          {/* Command input */}
          <div>
            <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2">
              Natural Language Command
            </div>
            <div className="flex gap-2">
              <input
                value={commandInput}
                onChange={(e) => setCommandInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Fly to Shackleton Rim…"
                className="flex-1 bg-lunar-dark/80 border border-lunar-border/60 rounded px-3 py-2
                           text-xs font-mono text-white placeholder-slate-700
                           focus:outline-none focus:border-lunar-accent/50 focus:bg-lunar-dark
                           transition-colors"
              />
              <button
                onClick={handleCommand}
                disabled={commandLoading}
                className="px-3 py-2 rounded bg-lunar-accent/15 hover:bg-lunar-accent/30
                           border border-lunar-accent/35 text-lunar-accent text-xs font-mono
                           disabled:opacity-40 transition-colors"
              >
                {commandLoading ? "…" : "→"}
              </button>
            </div>
          </div>

          {/* Site selector */}
          <SiteSelector />

          {/* Selected site detail or empty state */}
          {selectedSite ? (
            <>
              <div className="border-t border-slate-800/80 pt-4">
                <SiteCard site={selectedSite} />
              </div>
              {/* Council trigger below card */}
              <button
                onClick={() => triggerCouncil(selectedSite.site_id)}
                className="w-full py-2.5 rounded-lg border border-slate-700/60
                           bg-white/[0.02] hover:bg-white/[0.04] hover:border-slate-600/60
                           text-xs text-slate-400 hover:text-slate-200
                           transition-all font-mono"
              >
                Mission Council →
              </button>
            </>
          ) : (
            <div className="border-t border-slate-800/80 pt-4">
              <p className="text-xs text-slate-600 font-prose leading-relaxed text-center py-4">
                Select a site above to see solar, comms, and terrain analysis.
              </p>
            </div>
          )}

        </div>
      </div>
    </>
  );
}
