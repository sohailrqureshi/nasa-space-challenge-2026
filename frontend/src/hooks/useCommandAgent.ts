/**
 * useCommandAgent — natural-language command parsing hook.
 *
 * Calls POST /api/command and applies the resulting ViewerCommand
 * to the mission store (site selection, time range, scan trigger, etc.).
 */

import { useCallback } from "react";
import { useMissionStore } from "../store/missionStore";
import { useCouncilStream } from "./useCouncilStream";
import type { ViewerCommand } from "../types";

export function useCommandAgent() {
  const store = useMissionStore();
  const { triggerCouncil } = useCouncilStream();

  const sendCommand = useCallback(async (query: string): Promise<void> => {
    store.setCommandLoading(true);
    store.setLastQuery(query);
    try {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const cmd: ViewerCommand = await res.json();
      store.setLastCommand(cmd);
      await applyCommand(cmd, store, triggerCouncil);
    } catch (e) {
      console.error("Command error:", e);
    } finally {
      store.setCommandLoading(false);
    }
  }, [store, triggerCouncil]);

  return { sendCommand };
}

async function applyCommand(
  cmd: ViewerCommand,
  store: ReturnType<typeof useMissionStore.getState>,
  triggerCouncil: (siteId: string) => void,
) {
  switch (cmd.action) {
    case "fly_to": {
      if (cmd.site_id) {
        const site = store.sites.find((s) => s.site_id === cmd.site_id);
        if (site) {
          store.selectSite(site);
          triggerCouncil(site.site_id);
        }
      }
      break;
    }

    case "set_time_range": {
      if (cmd.time_range) {
        const start = new Date(cmd.time_range.start_iso);
        store.setMissionTime(start);
        if (cmd.time_range.speed_multiplier) {
          store.setPlaybackSpeed(
            cmd.time_range.speed_multiplier >= 1000 ? 1000 :
            cmd.time_range.speed_multiplier >= 100  ? 100  : 1
          );
        }
        store.togglePlayback();
      }
      break;
    }

    case "compare_sites": {
      if (cmd.sites && cmd.sites.length > 0) {
        const site = store.sites.find((s) => s.site_id === cmd.sites![0]);
        if (site) {
          store.selectSite(site);
          triggerCouncil(site.site_id);
        }
      }
      break;
    }

    case "scan_zones": {
      store.setIsScanning(true);
      try {
        const res = await fetch("/api/scan-zones", { method: "POST" });
        const report = await res.json();
        store.setScanReport(report);
      } catch (e) {
        console.error("Scan zones error:", e);
      } finally {
        store.setIsScanning(false);
      }
      break;
    }

    case "play_flythrough_tour": {
      const sites = store.sites;
      if (sites.length === 0) break;
      // Sort by survival_score descending so the tour visits best-to-worst
      const ordered = [...sites].sort((a, b) => b.survival_score - a.survival_score);
      // Fly to each site in sequence: 4 s per stop (matches CesiumViewer flyTo duration 2.5 s + dwell)
      ordered.forEach((site, i) => {
        setTimeout(() => {
          useMissionStore.getState().selectSite(site);
        }, i * 4000);
      });
      break;
    }

    case "none":
    default:
      break;
  }
}
