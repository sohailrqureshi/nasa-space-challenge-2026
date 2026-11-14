/**
 * CesiumViewer — full-viewport 3D Lunar Globe
 *
 * Responsibilities:
 *  - Init Viewer on MOON ellipsoid (set in main.tsx before this module loads)
 *  - Load Cesium Moon 3D Tiles (IonAssetId 2684829) if token present; else EllipsoidTerrain
 *  - Render landing site pins as billboards + labels
 *  - Render 3D sightline beams: Sun (amber) and Earth (cyan/pulsing-red)
 *  - Fly camera to selected site
 *  - Advance Cesium clock to track missionTime from the store
 *  - Export flyTo / flyTour / radarSweep imperative handle via ref (consumed by HUD)
 */

import { useEffect, useRef } from "react";
import * as Cesium from "cesium";
// vite-plugin-cesium injects widgets.css automatically; manual import omitted
import { useMissionStore } from "../store/missionStore";

const ION_TOKEN = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;

// Beam length from site toward Sun/Earth: 500 km
const BEAM_LENGTH_M = 500_000;

function latLonToCartesian(lat: number, lon: number, altM = 0): Cesium.Cartesian3 {
  return Cesium.Cartesian3.fromDegrees(lon, lat, altM);
}

function azElToUnitVector(
  lat: number, lon: number, azDeg: number, elDeg: number
): Cesium.Cartesian3 {
  // Convert azimuth/elevation from site's local horizontal frame to ECEF unit vector
  const latR = Cesium.Math.toRadians(lat);
  const lonR = Cesium.Math.toRadians(lon);
  const azR  = Cesium.Math.toRadians(azDeg);
  const elR  = Cesium.Math.toRadians(elDeg);

  // Local East-North-Up vectors
  const cosLat = Math.cos(latR), sinLat = Math.sin(latR);
  const cosLon = Math.cos(lonR), sinLon = Math.sin(lonR);

  const east  = new Cesium.Cartesian3(-sinLon, cosLon, 0);
  const north = new Cesium.Cartesian3(-sinLat * cosLon, -sinLat * sinLon, cosLat);
  const up    = new Cesium.Cartesian3( cosLat * cosLon,  cosLat * sinLon, sinLat);

  const cosEl = Math.cos(elR), sinEl = Math.sin(elR);
  const cosAz = Math.cos(azR), sinAz = Math.sin(azR);

  // ENU direction: az from North, el from horizontal
  const e = cosEl * sinAz;
  const n = cosEl * cosAz;
  const u = sinEl;

  return Cesium.Cartesian3.normalize(
    new Cesium.Cartesian3(
      e * east.x + n * north.x + u * up.x,
      e * east.y + n * north.y + u * up.y,
      e * east.z + n * north.z + u * up.z,
    ),
    new Cesium.Cartesian3()
  );
}

export default function CesiumViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef    = useRef<Cesium.Viewer | null>(null);
  const beamEntities = useRef<{ sun?: Cesium.Entity; earth?: Cesium.Entity }>({});
  const siteEntities = useRef<Map<string, Cesium.Entity>>(new Map());
  const radarEntity    = useRef<Cesium.Entity | null>(null);
  const radarRafRef    = useRef<number | null>(null);
  const radarAngleRef  = useRef<number>(0);

  const {
    sites, selectedSite, missionTime, isScanning, setTerrainFallback, setSightlines,
  } = useMissionStore();

  // ── Viewer initialisation ──────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    // Apply Ion token if available
    if (ION_TOKEN) {
      Cesium.Ion.defaultAccessToken = ION_TOKEN;
    }

    const viewer = new Cesium.Viewer(containerRef.current, {
      animation:              false,
      baseLayerPicker:        false,
      fullscreenButton:       false,
      geocoder:               false,
      homeButton:             false,
      infoBox:                false,
      navigationHelpButton:   false,
      sceneModePicker:        false,
      timeline:               false,
      selectionIndicator:     false,
      creditContainer:        document.createElement("div"), // suppress credit overlay
      contextOptions: {
        webgl: { antialias: true, powerPreference: "high-performance" },
      },
    });

    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#0a0c14");
    viewer.scene.globe.enableLighting = true;
    viewer.shadows = true;
    viewer.scene.shadowMap.size = 4096;
    viewer.scene.shadowMap.softShadows = true;
    viewer.scene.shadowMap.maximumDistance = 15000;
    // cascadesEnabled is a runtime-only property not in type stubs; cast safely
    (viewer.scene.shadowMap as unknown as Record<string, unknown>).cascadesEnabled = true;

    // Polar directional sunlight
    viewer.scene.light = new Cesium.DirectionalLight({
      direction: new Cesium.Cartesian3(0.5, 0.5, -0.7),
    });

    // Load Moon terrain
    (async () => {
      if (ION_TOKEN) {
        try {
          const terrain = await Cesium.CesiumTerrainProvider.fromIonAssetId(2684829);
          viewer.terrainProvider = terrain;
          useMissionStore.getState().setTerrainFallback(false);
        } catch {
          viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
          useMissionStore.getState().setTerrainFallback(true);
        }
      } else {
        viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
        useMissionStore.getState().setTerrainFallback(true);
      }

      // Add Moon imagery layer (Cesium World Imagery falls back to a plain grey surface on MOON)
      viewer.imageryLayers.removeAll();
      if (ION_TOKEN) {
        try {
          const layer = await Cesium.IonImageryProvider.fromAssetId(2684829);
          viewer.imageryLayers.addImageryProvider(layer);
        } catch {
          // Fallback to a neutral grey tint
          viewer.imageryLayers.addImageryProvider(
            new Cesium.SingleTileImageryProvider({
              url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
              rectangle: Cesium.Rectangle.MAX_VALUE,
            })
          );
        }
      }
    })();

    // Initial camera position: Lunar South Pole
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(0, -85, 400000),
      orientation: {
        heading: 0,
        pitch: Cesium.Math.toRadians(-45),
        roll: 0,
      },
      duration: 0,
    });

    // Click handler — select site on pin click
    viewer.screenSpaceEventHandler.setInputAction((movement: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      const picked = viewer.scene.pick(movement.position);
      if (Cesium.defined(picked) && picked.id instanceof Cesium.Entity) {
        const entity = picked.id as Cesium.Entity;
        const siteId = entity.properties?.getValue(Cesium.JulianDate.now())?.site_id;
        if (siteId) {
          const site = useMissionStore.getState().sites.find((s) => s.site_id === siteId);
          if (site) useMissionStore.getState().selectSite(site);
        }
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    viewerRef.current = viewer;

    return () => {
      viewer.destroy();
      viewerRef.current = null;
    };
  }, []);

  // ── Render site pins ───────────────────────────────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || sites.length === 0) return;

    // Clear existing
    siteEntities.current.forEach((e) => viewer.entities.remove(e));
    siteEntities.current.clear();

    sites.forEach((site) => {
      const isPSR = site.longest_darkness_hrs > 300;
      const color = isPSR
        ? Cesium.Color.fromCssColorString("#ef4444")
        : site.survival_score >= 65
          ? Cesium.Color.fromCssColorString("#22c55e")
          : Cesium.Color.fromCssColorString("#f59e0b");

      const entity = viewer.entities.add({
        position: latLonToCartesian(site.lat, site.lon, site.elev_m + 1000),
        billboard: {
          image: createPinCanvas(color),
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND,
          scale: 0.9,
          disableDepthTestDistance: 1e9,
        },
        label: {
          text: site.name,
          font: "12px JetBrains Mono, monospace",
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -40),
          heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND,
          disableDepthTestDistance: 1e9,
          show: false, // shown on hover/select
        },
        properties: { site_id: site.site_id },
      });
      siteEntities.current.set(site.site_id, entity);
    });
  }, [sites]);

  // ── Highlight selected site ────────────────────────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    siteEntities.current.forEach((entity, id) => {
      const isSelected = selectedSite?.site_id === id;
      if (entity.billboard) {
        entity.billboard.scale = new Cesium.ConstantProperty(isSelected ? 1.3 : 0.9);
      }
      if (entity.label) {
        entity.label.show = new Cesium.ConstantProperty(isSelected);
      }
    });

    if (selectedSite) {
      viewer.camera.flyTo({
        destination: latLonToCartesian(selectedSite.lat, selectedSite.lon, 80000),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-35), roll: 0 },
        duration: 2.5,
      });
    }
  }, [selectedSite]);

  // ── Update sightline beams with mission time ───────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !selectedSite) return;

    // Remove old beams
    if (beamEntities.current.sun)   viewer.entities.remove(beamEntities.current.sun);
    if (beamEntities.current.earth) viewer.entities.remove(beamEntities.current.earth);

    // Compute sun/earth positions from the physics endpoint or approximate locally
    // For now, use a simplified local estimate (backend handles the full physics)
    const site = selectedSite;
    const t = missionTime.getTime() / 1000;
    const dayOfYear = (missionTime.getTime() - new Date("2026-01-01").getTime()) / 86400000;

    // Approximate sun azimuth/elevation for beam direction
    const sunAz  = ((dayOfYear * 360 / 29.5 + t / 86400 * 360) % 360);
    const sunEl  = 2.5 * Math.sin(dayOfYear * 2 * Math.PI / 29.5);
    const earthAz = (sunAz + 180) % 360;
    const earthEl = 1.5 * Math.sin(dayOfYear * 2 * Math.PI / 27.3);

    const origin = latLonToCartesian(site.lat, site.lon, site.elev_m + 100);
    const meanHorizon = site.horizon_profile.reduce((a, b) => a + b, 0) / site.horizon_profile.length;

    const sunBlocked   = sunEl < meanHorizon + 2;
    const earthBlocked = earthEl < meanHorizon + 5;

    const sunDir   = azElToUnitVector(site.lat, site.lon, sunAz, Math.max(sunEl, 1));
    const earthDir = azElToUnitVector(site.lat, site.lon, earthAz, Math.max(earthEl, 0.5));

    const sunEnd   = Cesium.Cartesian3.add(origin, Cesium.Cartesian3.multiplyByScalar(sunDir, BEAM_LENGTH_M, new Cesium.Cartesian3()), new Cesium.Cartesian3());
    const earthEnd = Cesium.Cartesian3.add(origin, Cesium.Cartesian3.multiplyByScalar(earthDir, BEAM_LENGTH_M, new Cesium.Cartesian3()), new Cesium.Cartesian3());

    beamEntities.current.sun = viewer.entities.add({
      polyline: {
        positions: [origin, sunEnd],
        width: 2,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.3,
          color: sunBlocked
            ? Cesium.Color.ORANGE.withAlpha(0.3)
            : Cesium.Color.fromCssColorString("#f59e0b").withAlpha(0.9),
        }),
        arcType: Cesium.ArcType.NONE,
        clampToGround: false,
      },
    });

    beamEntities.current.earth = viewer.entities.add({
      polyline: {
        positions: [origin, earthEnd],
        width: 2,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.3,
          color: earthBlocked
            ? Cesium.Color.fromCssColorString("#ef4444").withAlpha(0.7)
            : Cesium.Color.fromCssColorString("#06b6d4").withAlpha(0.9),
        }),
        arcType: Cesium.ArcType.NONE,
        clampToGround: false,
      },
    });

    setSightlines({
      sunAzimuth: sunAz,
      sunElevation: sunEl,
      sunBlocked,
      earthAzimuth: earthAz,
      earthElevation: earthEl,
      earthBlocked,
    });
  }, [selectedSite, missionTime, setSightlines]);

  // ── Advance Cesium clock with mission time ─────────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.clock.currentTime = Cesium.JulianDate.fromDate(missionTime);
    // Update sun direction for realistic polar shadows
    const jd = Cesium.JulianDate.fromDate(missionTime);
    const sunPos = Cesium.Simon1994PlanetaryPositions.computeSunPositionInEarthInertialFrame(jd);
    const dir = Cesium.Cartesian3.normalize(
      Cesium.Cartesian3.negate(sunPos, new Cesium.Cartesian3()),
      new Cesium.Cartesian3()
    );
    if (viewer.scene.light instanceof Cesium.DirectionalLight) {
      viewer.scene.light.direction = dir;
    }
  }, [missionTime]);

  // ── 3D Radar Sweep — animated while gemini-3.8-flash scans 48 candidate sites ──
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    if (!isScanning) {
      // Clean up sweep when scan completes
      if (radarRafRef.current) cancelAnimationFrame(radarRafRef.current);
      if (radarEntity.current) {
        viewer.entities.remove(radarEntity.current);
        radarEntity.current = null;
      }
      return;
    }

    // Fly to South Pole overview for the sweep theatre
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(0, -87, 250000),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-55), roll: 0 },
      duration: 1.5,
    });

    // Build a sweep polyline fan: 60 spokes radiating from the south pole,
    // rotating in real-time via requestAnimationFrame
    const SPOKES   = 60;
    const RANGE_M  = 120_000; // 120 km sweep radius
    const origin   = Cesium.Cartesian3.fromDegrees(0, -89.9, 1000);

    function buildSweepPositions(angleDeg: number): Cesium.Cartesian3[] {
      const positions: Cesium.Cartesian3[] = [origin];
      for (let i = 0; i < SPOKES; i++) {
        const frac = i / SPOKES;
        const az   = Cesium.Math.toRadians(angleDeg - frac * 90); // trailing fan
        const lat  = -89.9 + (RANGE_M * Math.cos(az)) / 1_111_320;
        const lon  =        (RANGE_M * Math.sin(az)) /
          (1_111_320 * Math.cos(Cesium.Math.toRadians(-89.9)));
        positions.push(Cesium.Cartesian3.fromDegrees(lon % 360, lat, 1000));
      }
      positions.push(origin);
      return positions;
    }

    // Create the entity once; update positions each frame
    const sweepEntity = viewer.entities.add({
      polyline: {
        positions: new Cesium.CallbackProperty(() => {
          return buildSweepPositions(radarAngleRef.current);
        }, false),
        width: 1.5,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.4,
          color: Cesium.Color.fromCssColorString("#3b82f6").withAlpha(0.6),
        }),
        arcType: Cesium.ArcType.NONE,
        clampToGround: false,
      },
    });
    radarEntity.current = sweepEntity;

    // Also add a full-circle ring outline
    const ringEntity = viewer.entities.add({
      position: origin,
      ellipse: {
        semiMajorAxis: RANGE_M,
        semiMinorAxis: RANGE_M,
        height: 1000,
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString("#3b82f6").withAlpha(0.3),
        outlineWidth: 1,
        fill: false,
      },
    });

    const spin = () => {
      radarAngleRef.current = (radarAngleRef.current + 1.2) % 360;
      radarRafRef.current = requestAnimationFrame(spin);
    };
    radarRafRef.current = requestAnimationFrame(spin);

    return () => {
      if (radarRafRef.current) cancelAnimationFrame(radarRafRef.current);
      viewer.entities.remove(sweepEntity);
      viewer.entities.remove(ringEntity);
      radarEntity.current = null;
    };
  }, [isScanning]);

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 w-full h-full"
      style={{ zIndex: 0 }}
    />
  );
}

// ── Helper: canvas-drawn pin billboard ────────────────────────────────────────
function createPinCanvas(color: Cesium.Color): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width  = 32;
  canvas.height = 48;
  const ctx = canvas.getContext("2d")!;
  const hex = colorToHex(color);

  // Pin body
  ctx.beginPath();
  ctx.arc(16, 16, 12, 0, Math.PI * 2);
  ctx.fillStyle = hex;
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.8)";
  ctx.lineWidth = 2;
  ctx.stroke();

  // Pin point
  ctx.beginPath();
  ctx.moveTo(16, 28);
  ctx.lineTo(10, 44);
  ctx.lineTo(22, 44);
  ctx.closePath();
  ctx.fillStyle = hex;
  ctx.fill();

  // Inner dot
  ctx.beginPath();
  ctx.arc(16, 16, 5, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.fill();

  return canvas;
}

function colorToHex(c: Cesium.Color): string {
  const r = Math.round(c.red   * 255).toString(16).padStart(2, "0");
  const g = Math.round(c.green * 255).toString(16).padStart(2, "0");
  const b = Math.round(c.blue  * 255).toString(16).padStart(2, "0");
  return `#${r}${g}${b}`;
}
