/**
 * CouncilFeed — streaming Mission Control Council messages panel.
 *
 * Shows three agent cards (Power Officer, Comms Officer, Flight Director).
 * Each fills independently as SSE chunks arrive — no sequential blocking.
 */

import { useEffect, useRef } from "react";
import { useMissionStore } from "../store/missionStore";
import type { CouncilMessage } from "../types";

const AGENT_META = {
  power_officer:  { title: "Power Officer",    icon: "☀", color: "#f59e0b" },
  comms_officer:  { title: "Comms Officer",     icon: "◎", color: "#06b6d4" },
  flight_director:{ title: "Flight Director",   icon: "◈", color: "#a855f7" },
} as const;

function AgentCard({ agent, messages }: {
  agent: CouncilMessage["agent"];
  messages: CouncilMessage[];
}) {
  const meta       = AGENT_META[agent];
  const agentMsgs  = messages.filter((m) => m.agent === agent);
  const text       = agentMsgs.map((m) => m.text).join("");
  const isStreaming = useMissionStore((s) => s.councilLoading) && text.length === 0;
  const isActive    = useMissionStore((s) => s.councilLoading) && text.length > 0;
  const endRef      = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [text]);

  return (
    <div
      className="rounded-lg border p-3 space-y-2 transition-all duration-300"
      style={{ borderColor: `${meta.color}30`, background: `${meta.color}08` }}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <span style={{ color: meta.color }} className="font-mono text-sm">
          {meta.icon}
        </span>
        <span className="text-xs font-mono font-semibold text-white tracking-wide">
          {meta.title}
        </span>
        {isStreaming && (
          <span className="text-xs font-mono text-slate-500 animate-pulse ml-auto">
            connecting…
          </span>
        )}
        {isActive && (
          <span
            className="ml-auto w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ background: meta.color }}
          />
        )}
      </div>

      {/* Content */}
      <div className="text-xs text-slate-300 leading-relaxed min-h-8 font-mono">
        {text ? (
          <span className={isActive ? "streaming" : ""}>{text}</span>
        ) : isStreaming ? (
          <span className="text-slate-600 italic">Waiting for response…</span>
        ) : (
          <span className="text-slate-600 italic">
            Select a site and click Mission Council to begin.
          </span>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}

export default function CouncilFeed() {
  const { councilMessages, councilLoading, drawerOpen } = useMissionStore();

  if (!drawerOpen) return null;

  return (
    <div className="absolute bottom-16 left-0 z-10 w-80
                    glass-panel border-r border-lunar-border
                    max-h-96 overflow-y-auto">
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-500 uppercase tracking-wider">
            Mission Control Council
          </span>
          {councilLoading && (
            <span className="text-xs font-mono text-lunar-accent animate-pulse">
              LIVE
            </span>
          )}
        </div>

        {(["power_officer", "comms_officer", "flight_director"] as const).map((agent) => (
          <AgentCard key={agent} agent={agent} messages={councilMessages} />
        ))}
      </div>
    </div>
  );
}
