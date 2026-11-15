import { useMissionStore } from "../store/missionStore";
import type { PresetId } from "../types";

const PRESETS: {
  id: PresetId;
  label: string;
  description: string;
  pill: string;
  pillColor: string;
}[] = [
  {
    id: "scan_shackleton",
    label: "Scan Shackleton Rim",
    description: "AI radar sweep of 48 candidate sites → drops 3 ranked landing pins",
    pill: "BATCH AI",
    pillColor: "#3b82f6",
  },
  {
    id: "simulate_blackout",
    label: "Simulate Comms Blackout",
    description: "Fly into crater floor, accelerate timeline → watch Earth disappear",
    pill: "DTE PHYSICS",
    pillColor: "#06b6d4",
  },
  {
    id: "compare_ridge",
    label: "Compare 200m Ridge Shift",
    description: "Autonomous flythrough: shadowed depression vs. sunlit ridge peak",
    pill: "3D TOUR",
    pillColor: "#a855f7",
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
      <div className="glass-panel rounded-2xl max-w-lg w-full mx-4 pointer-events-auto animate-fade-in overflow-hidden">
        <div className="p-8 pb-6">
          {/* Header */}
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-full bg-lunar-accent/15 border border-lunar-accent/35 flex items-center justify-center shrink-0">
              <span className="text-lunar-accent text-lg font-mono">◎</span>
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white font-display tracking-tight" style={{ letterSpacing: "-0.02em" }}>
                SELENE SCOUT
              </h1>
              <p className="text-[11px] text-slate-400 font-mono tracking-widest uppercase mt-0.5">
                Lunar Landing Site Navigator
              </p>
            </div>
          </div>

          {/* Brief */}
          <p className="text-sm text-slate-300 leading-relaxed mb-6 font-prose">
            AI-powered analysis of Artemis candidate landing zones at the Lunar South Pole.
            Real-time 3D terrain, physics-accurate solar illumination, and a Mission Control
            Council that tells you exactly why you should — or absolutely should not — land in
            that crater.
          </p>

          {/* Demo presets */}
          <div className="space-y-2 mb-5">
            <p className="text-[11px] font-mono text-slate-500 uppercase tracking-widest mb-3">
              One-click demos for judges
            </p>
            {PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => runPreset(preset.id)}
                className="w-full text-left rounded-lg border border-white/10
                           hover:border-blue-400/50 bg-white/[0.03] hover:bg-blue-500/[0.08]
                           transition-all duration-200 group cursor-pointer overflow-hidden"
              >
                <div className="flex items-center gap-3 p-3.5">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded tracking-wider"
                        style={{
                          color: preset.pillColor,
                          background: `${preset.pillColor}1a`,
                          border: `1px solid ${preset.pillColor}35`,
                        }}
                      >
                        {preset.pill}
                      </span>
                    </div>
                    <div className="text-sm font-semibold text-white group-hover:text-blue-300 transition-colors font-display" style={{ letterSpacing: "-0.01em" }}>
                      {preset.label}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5 leading-snug font-prose">
                      {preset.description}
                    </div>
                  </div>
                  <span className="text-slate-600 group-hover:text-blue-400 transition-all duration-200 group-hover:translate-x-0.5 font-mono text-sm shrink-0">
                    →
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* CTA */}
          <button
            onClick={dismissOverlay}
            className="w-full py-3 rounded-lg bg-lunar-accent hover:bg-blue-500
                       text-white font-semibold text-sm tracking-wide
                       transition-colors duration-200 font-display"
            style={{ letterSpacing: "-0.01em" }}
          >
            Start Exploring →
          </button>
        </div>

        {/* Footer bar */}
        <div className="border-t border-slate-800/80 bg-black/20 px-8 py-3">
          <p className="text-xs text-slate-300 text-center font-mono tabular-nums">
            Mission window: 15 Nov – 15 Dec 2026 · South Pole 85–90°S
          </p>
        </div>
      </div>
    </div>
  );
}
