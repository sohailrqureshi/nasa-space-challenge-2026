// CRITICAL: Set lunar ellipsoid BEFORE any Cesium object is imported or instantiated.
// If this executes inside a component useEffect, module-level Cesium constants
// (Cartesian3.ZERO, etc.) have already initialised against WGS84 — causing silent
// polar coordinate drift. It must be at module top-level, before the React tree.
import * as Cesium from "cesium";
Cesium.Ellipsoid.default = Cesium.Ellipsoid.MOON;

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
