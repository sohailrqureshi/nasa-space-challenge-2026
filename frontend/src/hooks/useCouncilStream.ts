/**
 * useCouncilStream — SSE-based Mission Control Council streaming hook.
 *
 * Connects to GET /api/council/stream?site_id=<id>.
 * Handles three named SSE event types (power_officer, comms_officer, flight_director)
 * independently — each fills its own card without blocking the others.
 *
 * Cleans up the EventSource on component unmount or new site selection.
 */

import { useRef, useCallback } from "react";
import { useMissionStore } from "../store/missionStore";

export function useCouncilStream() {
  const esRef = useRef<EventSource | null>(null);
  const { addCouncilChunk, clearCouncil, setCouncilLoading } = useMissionStore();

  const triggerCouncil = useCallback((siteId: string) => {
    // Close any existing stream
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    clearCouncil();
    setCouncilLoading(true);

    const es = new EventSource(`/api/council/stream?site_id=${encodeURIComponent(siteId)}`);
    esRef.current = es;

    const addHandler = (agent: "power_officer" | "comms_officer" | "flight_director") =>
      (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data) as { text: string };
          if (payload.text) addCouncilChunk(agent, payload.text);
        } catch {
          // Ignore malformed chunks
        }
      };

    es.addEventListener("power_officer",   addHandler("power_officer"));
    es.addEventListener("comms_officer",   addHandler("comms_officer"));
    es.addEventListener("flight_director", addHandler("flight_director"));

    es.addEventListener("done", () => {
      setCouncilLoading(false);
      es.close();
      esRef.current = null;
    });

    es.onerror = (err) => {
      console.error("Council SSE error:", err);
      setCouncilLoading(false);
      es.close();
      esRef.current = null;
    };
  }, [addCouncilChunk, clearCouncil, setCouncilLoading]);

  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setCouncilLoading(false);
    }
  }, [setCouncilLoading]);

  return { triggerCouncil, closeStream };
}
