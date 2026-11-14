// ── Domain types shared across the frontend ──────────────────────────────────

export interface LandingSite {
  site_id: string;
  name: string;
  lat: number;
  lon: number;
  elev_m: number;
  terrain_slope_deg: number;
  solar_power_pct: number;
  longest_darkness_hrs: number;
  dte_comms_pct: number;
  longest_blackout_hrs: number;
  survival_score: number;
  horizon_profile: number[]; // 72 azimuth points, degrees
}

export interface CouncilMessage {
  id: string;
  agent: "power_officer" | "comms_officer" | "flight_director";
  text: string;
  timestamp: Date;
}

export type VerdictLevel = "GO" | "CAUTION" | "NO_GO";

export interface SiteRecommendation {
  rank: number;
  site_id: string;
  lat: number;
  lon: number;
  overall_score: number;
  rationale: string;
  key_advantage: string;
  key_risk: string;
  marker_color: string;
}

export interface ScoutReport {
  top_sites: SiteRecommendation[];
  mission_summary: string;
  recommended_primary: string;
  scan_timestamp_utc: string;
}

export interface ViewerCommand {
  action:
    | "fly_to"
    | "set_time_range"
    | "compare_sites"
    | "play_flythrough_tour"
    | "scan_zones"
    | "none";
  site_id?: string;
  coordinates?: { lat: number; lon: number; altitude_m: number };
  time_range?: { start_iso: string; end_iso: string; speed_multiplier: number };
  sites?: string[];
  response_text: string;
  response_tone: "informative" | "cautionary" | "excited" | "sardonic";
}

export type PlaybackSpeed = 1 | 100 | 1000;

export interface SightlineStatus {
  sunAzimuth: number;
  sunElevation: number;
  sunBlocked: boolean;
  earthAzimuth: number;
  earthElevation: number;
  earthBlocked: boolean;
}

// Demo preset IDs
export type PresetId = "scan_shackleton" | "simulate_blackout" | "compare_ridge";
