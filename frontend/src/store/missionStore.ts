import { create } from "zustand";
import type {
  LandingSite,
  CouncilMessage,
  ScoutReport,
  ViewerCommand,
  PlaybackSpeed,
  SightlineStatus,
} from "../types";

const MISSION_START = new Date("2026-11-15T00:00:00Z");
const MISSION_END   = new Date("2026-12-15T00:00:00Z");

interface MissionState {
  // Globe / scene
  sites: LandingSite[];
  selectedSite: LandingSite | null;
  scanReport: ScoutReport | null;
  isScanning: boolean;
  scanError: string | null;
  sightlines: SightlineStatus | null;

  // Timeline
  missionTime: Date;
  isPlaying: boolean;
  playbackSpeed: PlaybackSpeed;

  // Council
  councilMessages: CouncilMessage[];
  councilLoading: boolean;
  lastCommand: ViewerCommand | null;

  // UI state
  overlayDismissed: boolean;
  drawerOpen: boolean;
  commandInput: string;
  commandLoading: boolean;
  terrainFallback: boolean; // true when Cesium Ion token is absent

  // Actions
  setSites: (sites: LandingSite[]) => void;
  selectSite: (site: LandingSite | null) => void;
  setScanReport: (report: ScoutReport | null) => void;
  setIsScanning: (v: boolean) => void;
  setScanError: (err: string | null) => void;
  setSightlines: (s: SightlineStatus | null) => void;
  setMissionTime: (t: Date) => void;
  togglePlayback: () => void;
  setPlaybackSpeed: (s: PlaybackSpeed) => void;
  addCouncilChunk: (agent: CouncilMessage["agent"], text: string) => void;
  clearCouncil: () => void;
  setCouncilLoading: (v: boolean) => void;
  setLastCommand: (cmd: ViewerCommand | null) => void;
  dismissOverlay: () => void;
  setDrawerOpen: (v: boolean) => void;
  setCommandInput: (v: string) => void;
  setCommandLoading: (v: boolean) => void;
  setTerrainFallback: (v: boolean) => void;
}

export const useMissionStore = create<MissionState>((set, get) => ({
  sites: [],
  selectedSite: null,
  scanReport: null,
  isScanning: false,
  scanError: null,
  sightlines: null,

  missionTime: MISSION_START,
  isPlaying: false,
  playbackSpeed: 100,

  councilMessages: [],
  councilLoading: false,
  lastCommand: null,

  overlayDismissed: false,
  drawerOpen: true,
  commandInput: "",
  commandLoading: false,
  terrainFallback: false,

  setSites: (sites) => set({ sites }),
  selectSite: (site) => set({ selectedSite: site, drawerOpen: true }),
  setScanReport: (report) => set({ scanReport: report }),
  setIsScanning: (v) => set({ isScanning: v }),
  setScanError: (err) => set({ scanError: err }),
  setSightlines: (s) => set({ sightlines: s }),

  setMissionTime: (t) => {
    const clamped = t < MISSION_START ? MISSION_START : t > MISSION_END ? MISSION_END : t;
    set({ missionTime: clamped });
  },

  togglePlayback: () => set((s) => ({ isPlaying: !s.isPlaying })),
  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),

  addCouncilChunk: (agent, text) =>
    set((state) => {
      const msgs = [...state.councilMessages];
      const last = msgs[msgs.length - 1];
      if (last && last.agent === agent) {
        // Append chunk to existing message bubble
        msgs[msgs.length - 1] = { ...last, text: last.text + text };
      } else {
        msgs.push({
          id: `${agent}-${Date.now()}`,
          agent,
          text,
          timestamp: new Date(),
        });
      }
      return { councilMessages: msgs };
    }),

  clearCouncil: () => set({ councilMessages: [] }),
  setCouncilLoading: (v) => set({ councilLoading: v }),
  setLastCommand: (cmd) => set({ lastCommand: cmd }),

  dismissOverlay: () => set({ overlayDismissed: true }),
  setDrawerOpen: (v) => set({ drawerOpen: v }),
  setCommandInput: (v) => set({ commandInput: v }),
  setCommandLoading: (v) => set({ commandLoading: v }),
  setTerrainFallback: (v) => set({ terrainFallback: v }),
}));

export { MISSION_START, MISSION_END };
