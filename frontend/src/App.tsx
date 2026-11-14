import { useEffect, useRef } from "react";
import { useMissionStore, MISSION_START, MISSION_END } from "./store/missionStore";
import CesiumViewer from "./components/CesiumViewer";
import MissionBriefingOverlay from "./components/MissionBriefingOverlay";
import MissionControlHUD from "./components/MissionControlHUD";
import CouncilFeed from "./components/CouncilFeed";
import TimelineScrubber from "./components/TimelineScrubber";

export default function App() {
  const {
    isPlaying, playbackSpeed, missionTime, setMissionTime,
    overlayDismissed, setSites,
  } = useMissionStore();

  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);

  // Fetch pre-scored sites on mount
  useEffect(() => {
    fetch("/api/sites")
      .then((r) => r.json())
      .then(setSites)
      .catch(console.error);
  }, [setSites]);

  // Playback tick — advances missionTime at the selected multiplier
  useEffect(() => {
    if (!isPlaying) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastTickRef.current = null;
      return;
    }
    const tick = (now: number) => {
      if (lastTickRef.current !== null) {
        const wallMs  = now - lastTickRef.current;
        const simMs   = wallMs * playbackSpeed;
        const next    = new Date(missionTime.getTime() + simMs);
        if (next >= MISSION_END) {
          setMissionTime(MISSION_END);
          useMissionStore.getState().togglePlayback();
          return;
        }
        setMissionTime(next);
      }
      lastTickRef.current = now;
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, playbackSpeed, missionTime, setMissionTime]);

  return (
    <div className="relative w-full h-full bg-lunar-dark">
      {/* 3D Globe — full viewport, always rendered */}
      <CesiumViewer />

      {/* Mission Briefing overlay (dismissible, floats over globe) */}
      {!overlayDismissed && <MissionBriefingOverlay />}

      {/* Top HUD bar + right drawer */}
      {overlayDismissed && <MissionControlHUD />}

      {/* Council feed drawer */}
      {overlayDismissed && <CouncilFeed />}

      {/* Bottom timeline scrubber */}
      {overlayDismissed && <TimelineScrubber />}
    </div>
  );
}
