/**
 * MissionBriefingOverlay — first-load glassmorphic panel over the 3D globe.
 * Dismissed by clicking "Start Exploring" or any demo preset.
 * No separate landing page — the globe is always live behind it.
 */

import { useMissionStore } from "../store/missionStore";
import type { PresetId } from "../types";

const PRESETS: { id: PresetId; label: string; description: string; icon: string }[] = [
  {
    id: "scan_shackleton",
    label: "Scan Shackleton Rim",
    description: "AI radar sweep of 48 candidate sites → drops 3 ranked landing pins",
    icon: "⬡",
  },
  {
    id: "simulate_blackout",
    label: "Simulate Comms Blackout",
    description: "Fly into crater floor, accelerate timeline → watch Earth disappear",
    icon: "◎",
  },
  {
    id: "compare_ridge",
    label: "Compare 200m Ridge Shift",
    description: "Autonomous flythrough: shadowed depression vs. sunlit ridge peak",
    icon: "⟺",
  },
];

async function runPreset(id: PresetId) {
  const store = useMissionStore.getState();

  if (id === "scan_shackleton") {
    store.setIsScanning(true);
    store.dismissOverlay();
    try {
      const res = await fetch("/api/scan-zones", { method: "POST" });
      const report = await res.json();
      store.setScanReport(report);
    } catch (e) {
      console.error("Scan failed:", e);
    } finally {
      store.setIsScanning(false);
    }
    return;
  }

  if (id === "simulate_blackout") {
    store.dismissOverlay();
    const floor = store.sites.find((s) => s.site_id === "shackleton_floor");
    if (floor) {
      store.selectSite(floor);
      store.setPlaybackSpeed(1000);
      store.togglePlayback();
    }
    return;
  }

  if (id === "compare_ridge") {
    store.dismissOverlay();
    const rim = store.sites.find((s) => s.site_id === "shackleton_rim");
    if (rim) store.selectSite(rim);
    return;
  }
}

export default function MissionBriefingOverlay() {
  const dismissOverlay = useMissionStore((s) => s.dismissOverlay);

  return (
    <div className="absolute inset-0 flex items-center justify-center z-20 pointer-events-none">
      <div className="glass-panel rounded-2xl p-8 max-w-lg w-full mx-4 pointer-events-auto animate-fade-in">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-lunar-accent/20 border border-lunar-accent/40 flex items-center justify-center">
            <span className="text-lunar-accent text-lg font-mono">◎</span>
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-wide font-mono">
              SELENE SCOUT
            </h1>
            <p className="text-xs text-slate-400 font-mono tracking-widest uppercase">
              Lunar Landing Site Navigator
            </p>
          </div>
        </div>

        {/* Brief */}
        <p className="text-sm text-slate-300 leading-relaxed mb-6">
          AI-powered analysis of Artemis candidate landing zones at the Lunar South Pole.
          Real-time 3D terrain, physics-accurate solar illumination, and a Mission Control
          Council that tells you exactly why you should — or absolutely should not — land in
          that crater.
        </p>

        {/* Demo presets */}
        <div className="space-y-2 mb-6">
          <p className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-3">
            One-click demos for judges
          </p>
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              onClick={() => runPreset(preset.id)}
              className="w-full text-left px-4 py-3 rounded-lg border border-lunar-border
                         hover:border-lunar-accent/60 hover:bg-lunar-accent/10
                         transition-all duration-200 group"
            >
              <div className="flex items-center gap-3">
                <span className="text-lunar-accent font-mono text-lg w-6 text-center">
                  {preset.icon}
                </span>
                <div>
                  <div className="text-sm font-semibold text-white group-hover:text-lunar-accent transition-colors">
                    {preset.label}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">{preset.description}</div>
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={dismissOverlay}
          className="w-full py-3 rounded-lg bg-lunar-accent hover:bg-blue-500
                     text-white font-semibold text-sm font-mono tracking-wide
                     transition-colors duration-200"
        >
          Start Exploring →
        </button>

        {/* Footer note */}
        <p className="text-xs text-slate-600 mt-4 text-center">
          Mission window: 15 Nov – 15 Dec 2026 · South Pole 85–90°S
        </p>
      </div>
    </div>
  );
}
