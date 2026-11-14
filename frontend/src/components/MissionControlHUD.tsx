/**
 * MissionControlHUD — top bar + right metrics drawer.
 *
 * Top bar: app title, selected site coords, terrain fallback warning,
 *          preset trigger buttons, natural-language command input.
 * Right drawer: Power & Comms gauge cards, site metrics, command bar.
 */

import { useState, type KeyboardEvent } from "react";
import { useMissionStore } from "../store/missionStore";
import { useCommandAgent } from "../hooks/useCommandAgent";
import { useCouncilStream } from "../hooks/useCouncilStream";
import type { LandingSite } from "../types";

function ScoreGauge({ label, value, max = 100, color }: {
  label: string; value: number; max?: number; color: string;
}) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs font-mono">
        <span className="text-slate-400">{label}</span>
        <span className="text-white font-semibold">{value.toFixed(1)}{max === 100 ? "%" : ""}</span>
      </div>
      <div className="h-1.5 bg-lunar-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function SiteCard({ site }: { site: LandingSite }) {
  const verdictColor =
    site.survival_score >= 65 ? "#22c55e" :
    site.survival_score >= 40 ? "#f59e0b" : "#ef4444";
  const verdictLabel =
    site.survival_score >= 65 ? "GO" :
    site.survival_score >= 40 ? "CAUTION" : "NO-GO";

  return (
    <div className="space-y-3 animate-slide-up">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-slate-400 font-mono">SELECTED SITE</div>
          <div className="text-sm font-bold text-white">{site.name}</div>
          <div className="text-xs text-slate-500 font-mono">
            {site.lat.toFixed(2)}°S, {site.lon.toFixed(2)}°E · {site.elev_m.toFixed(0)} m
          </div>
        </div>
        <div
          className="px-2 py-1 rounded text-xs font-bold font-mono border"
          style={{ color: verdictColor, borderColor: `${verdictColor}60`, background: `${verdictColor}20` }}
        >
          {verdictLabel}
        </div>
      </div>

      <div className="border-t border-lunar-border pt-3 space-y-2.5">
        <ScoreGauge label="Solar Power" value={site.solar_power_pct} color="#f59e0b" />
        <ScoreGauge label="DTE Comms"   value={site.dte_comms_pct}   color="#06b6d4" />
        <ScoreGauge label="Survival Score" value={site.survival_score} color={verdictColor} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div className="bg-lunar-dark rounded p-2 border border-lunar-border">
          <div className="text-slate-500">Max darkness</div>
          <div className="text-white font-semibold">{site.longest_darkness_hrs}h</div>
        </div>
        <div className="bg-lunar-dark rounded p-2 border border-lunar-border">
          <div className="text-slate-500">Max blackout</div>
          <div className="text-white font-semibold">{site.longest_blackout_hrs}h</div>
        </div>
        <div className="bg-lunar-dark rounded p-2 border border-lunar-border">
          <div className="text-slate-500">Slope</div>
          <div className="text-white font-semibold">{site.terrain_slope_deg.toFixed(1)}°</div>
        </div>
        <div className="bg-lunar-dark rounded p-2 border border-lunar-border">
          <div className="text-slate-500">Elevation</div>
          <div className="text-white font-semibold">{site.elev_m.toFixed(0)} m</div>
        </div>
      </div>
    </div>
  );
}

function SiteSelector() {
  const { sites, selectedSite, selectSite } = useMissionStore();
  return (
    <div className="space-y-1">
      <div className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-2">
        Artemis Candidate Sites
      </div>
      {sites.map((site) => {
        const isSelected = selectedSite?.site_id === site.site_id;
        const scoreColor =
          site.survival_score >= 65 ? "text-go-green" :
          site.survival_score >= 40 ? "text-caution-amber" : "text-alert-red";
        return (
          <button
            key={site.site_id}
            onClick={() => selectSite(site)}
            className={`w-full text-left px-3 py-2 rounded-lg text-xs font-mono transition-all
                        border ${isSelected
                          ? "border-lunar-accent bg-lunar-accent/15 text-white"
                          : "border-lunar-border hover:border-lunar-accent/40 text-slate-300"}`}
          >
            <div className="flex justify-between items-center">
              <span className="truncate">{site.name}</span>
              <span className={`font-bold ml-2 shrink-0 ${scoreColor}`}>
                {site.survival_score.toFixed(0)}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

export default function MissionControlHUD() {
  const {
    selectedSite, terrainFallback, commandInput, commandLoading,
    setCommandInput, isScanning,
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
      <div className="absolute top-0 left-0 right-0 z-10 glass-panel border-b border-lunar-border">
        <div className="flex items-center gap-4 px-4 py-2.5">
          {/* Logo */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-lunar-accent font-mono font-bold text-sm tracking-widest">
              SELENE SCOUT
            </span>
            {isScanning && (
              <span className="text-xs text-caution-amber font-mono animate-pulse">
                · SCANNING
              </span>
            )}
          </div>

          {/* Selected site coords */}
          <div className="flex-1 text-center text-xs font-mono text-slate-400">
            {selectedSite ? (
              <span>
                <span className="text-white">{selectedSite.name}</span>
                {" · "}
                {selectedSite.lat.toFixed(2)}°S, {selectedSite.lon.toFixed(2)}°E
                {" · "}
                {selectedSite.elev_m.toFixed(0)} m
              </span>
            ) : (
              <span>Select a landing site or type a command below</span>
            )}
          </div>

          {/* Terrain fallback warning */}
          {terrainFallback && (
            <div className="shrink-0 text-xs font-mono text-caution-amber border border-caution-amber/30 rounded px-2 py-0.5">
              ⚠ No terrain DEM
            </div>
          )}

          {/* Council trigger */}
          {selectedSite && (
            <button
              onClick={() => triggerCouncil(selectedSite.site_id)}
              className="shrink-0 px-3 py-1 text-xs font-mono rounded
                         bg-lunar-accent/20 hover:bg-lunar-accent/40
                         border border-lunar-accent/40 text-lunar-accent
                         transition-colors"
            >
              Mission Council
            </button>
          )}
        </div>
      </div>

      {/* ── Right Drawer ────────────────────────────────────────────── */}
      <div className="absolute top-12 right-0 bottom-16 z-10 w-72
                      glass-panel border-l border-lunar-border overflow-y-auto">
        <div className="p-4 space-y-5">
          {/* Command input */}
          <div>
            <div className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">
              Natural Language Command
            </div>
            <div className="flex gap-2">
              <input
                value={commandInput}
                onChange={(e) => setCommandInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Fly to Shackleton Rim…"
                className="flex-1 bg-lunar-dark border border-lunar-border rounded px-3 py-2
                           text-xs font-mono text-white placeholder-slate-600
                           focus:outline-none focus:border-lunar-accent/60"
              />
              <button
                onClick={handleCommand}
                disabled={commandLoading}
                className="px-3 py-2 rounded bg-lunar-accent/20 hover:bg-lunar-accent/40
                           border border-lunar-accent/40 text-lunar-accent text-xs font-mono
                           disabled:opacity-40 transition-colors"
              >
                {commandLoading ? "…" : "→"}
              </button>
            </div>
          </div>

          {/* Site selector list */}
          <SiteSelector />

          {/* Selected site detail card */}
          {selectedSite && <SiteCard site={selectedSite} />}
        </div>
      </div>
    </>
  );
}
