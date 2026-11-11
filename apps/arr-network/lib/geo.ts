import geo from "../data/india-states.json";

export interface GeoState { code: string; name: string; kind: string; d: string; cx: number; cy: number }
export const GEO = geo as { source: string; simplified: string; viewBox: string; states: GeoState[] };
/** Territories too small to click on the map: they get a larger invisible hit circle and a dot. */
export const SMALL = new Set(GEO.states.filter((s) => s.d.length < 1600).map((s) => s.code));
