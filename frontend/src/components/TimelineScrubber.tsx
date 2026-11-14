/**
 * TimelineScrubber — bottom bar mission timeline control.
 *
 * Shows: date/time display, play/pause, speed selector (1x/100x/1000x),
 *        scrub slider (Nov 15 – Dec 15, 2026), sightline status indicators.
 */

import { useMissionStore, MISSION_START, MISSION_END } from "../store/missionStore";
import type { PlaybackSpeed } from "../types";

const DURATION_MS = MISSION_END.getTime() - MISSION_START.getTime();

function formatDate(d: Date): string {
  return d.toUTCString().slice(0, 22) + " UTC";
}

export default function TimelineScrubber() {
  const {
    missionTime, isPlaying, playbackSpeed,
    setMissionTime, togglePlayback, setPlaybackSpeed,
    sightlines,
  } = useMissionStore();

  const progress = (missionTime.getTime() - MISSION_START.getTime()) / DURATION_MS;

  const handleScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const frac = parseFloat(e.target.value) / 1000;
    setMissionTime(new Date(MISSION_START.getTime() + frac * DURATION_MS));
  };

  const speeds: PlaybackSpeed[] = [1, 100, 1000];

  return (
    <div className="absolute bottom-0 left-0 right-0 z-10 glass-panel border-t border-lunar-border">
      <div className="flex items-center gap-4 px-4 py-2">
        {/* Play/Pause */}
        <button
          onClick={togglePlayback}
          className="w-8 h-8 rounded flex items-center justify-center
                     bg-lunar-accent/20 hover:bg-lunar-accent/40
                     border border-lunar-accent/40 text-lunar-accent
                     transition-colors shrink-0"
        >
          {isPlaying ? "⏸" : "▶"}
        </button>

        {/* Speed selector */}
        <div className="flex gap-1 shrink-0">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => setPlaybackSpeed(s)}
              className={`px-2 py-0.5 text-xs font-mono rounded border transition-colors
                          ${playbackSpeed === s
                            ? "border-lunar-accent bg-lunar-accent/20 text-lunar-accent"
                            : "border-lunar-border text-slate-500 hover:text-slate-300"}`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Date display */}
        <div className="text-xs font-mono text-slate-300 shrink-0 w-52 tabular-nums">
          {formatDate(missionTime)}
        </div>

        {/* Scrub slider */}
        <div className="flex-1 relative">
          <input
            type="range"
            min={0}
            max={1000}
            value={Math.round(progress * 1000)}
            onChange={handleScrub}
            className="w-full h-1.5 appearance-none bg-lunar-border rounded-full
                       [&::-webkit-slider-thumb]:appearance-none
                       [&::-webkit-slider-thumb]:w-3
                       [&::-webkit-slider-thumb]:h-3
                       [&::-webkit-slider-thumb]:rounded-full
                       [&::-webkit-slider-thumb]:bg-lunar-accent
                       [&::-webkit-slider-thumb]:cursor-pointer"
            style={{
              background: `linear-gradient(to right, #3b82f6 ${progress * 100}%, #1f2d4a ${progress * 100}%)`,
            }}
          />
          {/* Mission labels */}
          <div className="flex justify-between text-xs font-mono text-slate-600 mt-0.5">
            <span>15 Nov 2026</span>
            <span>15 Dec 2026</span>
          </div>
        </div>

        {/* Sightline status indicators */}
        <div className="flex gap-3 shrink-0">
          {sightlines ? (
            <>
              <div className="flex items-center gap-1.5 text-xs font-mono">
                <span className={`w-2 h-2 rounded-full ${sightlines.sunBlocked ? "bg-alert-red" : "bg-solar-gold"}`} />
                <span className={sightlines.sunBlocked ? "text-alert-red" : "text-solar-gold"}>
                  SUN {sightlines.sunBlocked ? "BLOCKED" : `${sightlines.sunElevation.toFixed(1)}°`}
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-mono">
                <span className={`w-2 h-2 rounded-full ${sightlines.earthBlocked ? "bg-alert-red animate-pulse" : "bg-earth-cyan"}`} />
                <span className={sightlines.earthBlocked ? "text-alert-red" : "text-earth-cyan"}>
                  EARTH {sightlines.earthBlocked ? "BLOCKED" : `${sightlines.earthElevation.toFixed(1)}°`}
                </span>
              </div>
            </>
          ) : (
            <span className="text-xs font-mono text-slate-600">— select site —</span>
          )}
        </div>
      </div>
    </div>
  );
}
