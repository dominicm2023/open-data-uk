/* Licensed HMOs by postcode district.

   Seen whole, the country is a density: where the registers are thick with
   licences the map glows. Closer, the glow gives way to the districts
   themselves, each filled by its count, and a click opens one: how many
   licences, on which council's register, of what kind.

   Districts, never doors. The data this draws (districts.geojson) holds a
   count per postcode district and nothing finer, so there is no property
   to find here however far you zoom; the zoom stops at the scale of a
   district for the same reason.

   MapLibre GL JS, the shapes and the counts are all served from this site.
   There is no basemap from anywhere else: the land is the postcode areas.
   No glyphs are loaded, so the names on the map are HTML, not map text.
*/
import { Map as MapLibre, NavigationControl, AttributionControl, Marker, LngLatBounds } from "/maplibre-gl.mjs";

const $ = id => document.getElementById(id);
const mapEl = $("hmo-map"), panel = $("hmo-panel"), legend = $("hmo-legend"), nogl = $("hmo-nogl");
const css = getComputedStyle(document.documentElement);
const token = n => css.getPropertyValue(n).trim();
const DARK = window.matchMedia("(prefers-color-scheme: dark)").matches;
const STILL = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SEQ = [1, 2, 3, 4, 5].map(i => token(`--seq-${i}`) || ["#dce8f6", "#abc6e6", "#7099cb", "#3f6fae", "#14549c"][i - 1]);
const STEPS = [25, 100, 300, 700];                      // a district's licences: the edges between the five colours
const SEA = DARK ? "#0c1620" : "#d5e3ee", LAND = DARK ? "#1b1d21" : "#fbfbf9", COAST = DARK ? "#3c4048" : "#b9bcb4";
const INK = token("--ink") || "#16181c", ACCENT = token("--accent") || "#14549c";
const GB = [[-8.4, 49.7], [2.2, 59.2]];
const fmt = n => Math.round(n).toLocaleString("en-GB");
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

function fail() { mapEl.hidden = true; panel.hidden = true; legend.hidden = true; nogl.hidden = false; }

function boundsOf(geom) {
  const b = new LngLatBounds();
  for (const poly of geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates]) for (const p of poly[0]) b.extend(p);
  return b;
}

function drawLegend() {
  legend.textContent = "";
  legend.append(el("span", "hmo-legend-title", "Licences in a district"));
  const edges = [1, ...STEPS];
  edges.forEach((from, i) => {
    const s = el("span", "hmo-key"); const sw = el("i"); sw.style.background = SEQ[i];
    s.append(sw, document.createTextNode(i < STEPS.length ? `${from} to ${STEPS[i] - 1}` : `${from} or more`)); legend.append(s);
  });
  const none = el("span", "hmo-key"); const sw = el("i", "hmo-none"); none.append(sw, document.createTextNode("none on these registers")); legend.append(none);
}

function showDistrict(p) {
  panel.textContent = "";
  panel.append(el("h2", null, p.district));
  if (!p.licences) {
    panel.append(el("p", "hmo-big", "No licences listed"),
      el("p", "note", `The registers in this table list no licensed HMO in ${p.district}. That is not the same as none: only some councils publish their register as open data, and an HMO without a licence is on no register.`));
  } else {
    panel.append(el("p", "hmo-big", `${fmt(p.licences)} licensed HMO${p.licences === 1 ? "" : "s"}`));
    const councils = JSON.parse(p.councils), types = JSON.parse(p.types);
    const ul = el("ul", "hmo-list");
    for (const c of councils) {
      const li = el("li"); const a = el("a", null, c.council); a.href = c.source_url; a.rel = "noopener";
      li.append(a, document.createTextNode(` ${fmt(c.licences)} on its register` + (c.as_of ? `, dated ${c.as_of}` : ", which states no date")));
      ul.append(li);
    }
    panel.append(el("h3", null, councils.length === 1 ? "Whose register" : "Whose registers"), ul);
    if (types.length && !(types.length === 1 && types[0][0] === "not stated")) {
      const tl = el("ul", "hmo-list"); for (const [t, n] of types) tl.append(el("li", null, `${t}: ${fmt(n)}`));
      panel.append(el("h3", null, "Kind of licence, in the council's words"), tl);
    }
    if (p.occupants_of) panel.append(el("p", "note", `${fmt(p.occupants)} people are permitted to live in the ${fmt(p.occupants_of)} of these whose licence says how many.`));
    panel.append(el("p", "note", "The address of each is on the council's own register, linked above. This table holds the district only."));
  }
  const back = el("button", "hmo-reset", "Whole country"); back.type = "button"; back.addEventListener("click", () => window.dispatchEvent(new Event("hmo-home")));
  panel.append(back);
}

async function start() {
  let districts, areas;
  try {
    [districts, areas] = await Promise.all(["districts", "areas"].map(n =>
      fetch(`/api/family/hmo_registers/${n}.geojson`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })));
  } catch (err) { nogl.textContent = "The map's data could not be loaded. Every figure it would show is in the table below."; return fail(); }

  const counted = districts.features.filter(f => f.properties.licences > 0);
  const byName = new Map(districts.features.map(f => [f.properties.district, f]));
  const points = { type: "FeatureCollection", features: counted.map(f => ({ type: "Feature", properties: { licences: f.properties.licences },
    geometry: { type: "Point", coordinates: [f.properties.lon, f.properties.lat] } })) };
  const top = Math.max(...counted.map(f => f.properties.licences));

  let map;
  try {
    map = new MapLibre({
      container: mapEl, attributionControl: false, minZoom: 4, maxZoom: 12.5, dragRotate: false, pitchWithRotate: false,
      maxBounds: [[-13, 48.5], [6, 61.5]], bounds: GB, fitBoundsOptions: { padding: 20 },
      style: { version: 8, sources: {}, layers: [{ id: "sea", type: "background", paint: { "background-color": SEA } }] },
    });
  } catch (err) { return fail(); }
  map.touchZoomRotate.disableRotation();
  map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new AttributionControl({ compact: true, customAttribution: "Boundaries: M. Longair / mySociety, OGL v3. Contains OS, Royal Mail and ONS data © Crown copyright and database right 2020." }), "bottom-right");
  map.on("error", e => { if (e && e.error && /webgl/i.test(String(e.error.message))) fail(); });

  map.on("load", () => {
    map.addSource("areas", { type: "geojson", data: areas });
    map.addSource("districts", { type: "geojson", data: districts, promoteId: "district" });
    map.addSource("points", { type: "geojson", data: points });
    map.addLayer({ id: "land", type: "fill", source: "areas", paint: { "fill-color": LAND } });
    map.addLayer({ id: "coast", type: "line", source: "areas", paint: { "line-color": COAST, "line-width": 0.6,
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 8, 0.25] } });
    // the districts these registers say nothing about: outlines only, and only up close
    map.addLayer({ id: "quiet", type: "fill", source: "districts", filter: ["==", ["get", "licences"], 0], minzoom: 7.5,
      paint: { "fill-color": COAST, "fill-opacity": ["case", ["boolean", ["feature-state", "on"], false], 0.35, 0] } });
    map.addLayer({ id: "quiet-line", type: "line", source: "districts", filter: ["==", ["get", "licences"], 0], minzoom: 7.5,
      paint: { "line-color": COAST, "line-width": 0.7, "line-opacity": ["interpolate", ["linear"], ["zoom"], 7.5, 0, 9, 0.8] } });
    map.addLayer({ id: "count", type: "fill", source: "districts", filter: [">", ["get", "licences"], 0],
      paint: { "fill-color": ["step", ["get", "licences"], SEQ[0], STEPS[0], SEQ[1], STEPS[1], SEQ[2], STEPS[2], SEQ[3], STEPS[3], SEQ[4]],
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 0, 8.5, 0.9] } });
    map.addLayer({ id: "count-line", type: "line", source: "districts", filter: [">", ["get", "licences"], 0],
      paint: { "line-color": ["case", ["boolean", ["feature-state", "on"], false], INK, LAND],
        "line-width": ["case", ["boolean", ["feature-state", "on"], false], 2.5, 0.8],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 0, 8.5, 1] } });
    // seen whole: a density, weighted by each district's licences
    map.addLayer({ id: "heat", type: "heatmap", source: "points", maxzoom: 9,
      paint: { "heatmap-weight": ["interpolate", ["linear"], ["get", "licences"], 0, 0.05, top, 1],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 4, 1.4, 8, 2.4],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 4, 22, 6, 36, 8, 64],
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.08, SEQ[1], 0.3, SEQ[2], 0.6, SEQ[3], 1, SEQ[4]],
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 0.9, 8.5, 0] } });

    // names, as HTML: a council's name when the country is whole, a district's code up close
    const councils = new Map();
    for (const f of counted) for (const c of JSON.parse(f.properties.councils)) {
      const e = councils.get(c.council) || { n: 0, x: 0, y: 0, b: new LngLatBounds() };
      e.n += c.licences; e.x += f.properties.lon * c.licences; e.y += f.properties.lat * c.licences; e.b.extend(boundsOf(f.geometry)); councils.set(c.council, e);
    }
    const far = [], near = [];
    // beside the glow, not over it; and councils that are neighbours (Camden, Lambeth) take a side each
    const placed = [...councils].map(([name, e]) => ({ name, e, lon: e.x / e.n, lat: e.y / e.n })).sort((a, b) => b.lat - a.lat);
    placed.forEach((c, i) => {
      const near = placed.filter(o => o !== c && Math.hypot(o.lon - c.lon, (o.lat - c.lat) * 1.7) < 0.8);
      const upper = !near.length || near.every(o => o.lat < c.lat);
      const b = el("button", "hmo-place"); b.type = "button"; b.append(el("b", null, c.name.replace(/^London Borough of /, "")), el("span", null, `${fmt(c.e.n)} licences`));
      b.addEventListener("click", ev => { ev.stopPropagation(); go(c.e.b, 40); });
      far.push(new Marker({ element: b, anchor: near.length ? (upper ? "bottom-left" : "top-left") : "left", offset: near.length ? [12, upper ? -6 : 6] : [18, 0] }).setLngLat([c.lon, c.lat]).addTo(map));
    });
    for (const f of counted) {
      const b = el("button", "hmo-district"); b.type = "button"; b.append(el("b", null, f.properties.district), el("span", null, fmt(f.properties.licences)));
      b.addEventListener("click", ev => { ev.stopPropagation(); open(f.properties.district, false); });
      near.push(new Marker({ element: b, anchor: "center" }).setLngLat([f.properties.lon, f.properties.lat]).addTo(map));
    }
    const names = () => { const z = map.getZoom();
      for (const m of far) m.getElement().hidden = z >= 8;
      for (const m of near) m.getElement().hidden = z < 9.6; };
    map.on("zoom", names); names();

    let on = null, over = null;
    const state = (id, s) => { if (id != null) map.setFeatureState({ source: "districts", id }, s); };
    function go(bounds, pad) { map.fitBounds(bounds, { padding: pad, maxZoom: 11.5, animate: !STILL, duration: 900 }); }
    function open(name, move) {
      const f = byName.get(name); if (!f) return;
      state(on, { on: false }); on = name; state(on, { on: true });
      showDistrict(f.properties);
      if (move) go(boundsOf(f.geometry), 60);
    }
    for (const layer of ["count", "quiet"]) {
      map.on("click", layer, e => { if (e.features && e.features[0]) open(e.features[0].properties.district, false); });
      map.on("mousemove", layer, e => { map.getCanvas().style.cursor = "pointer"; over = e.features && e.features[0] ? e.features[0].properties.district : null; mapEl.title = over || ""; });
      map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; mapEl.title = ""; });
    }
    // seen whole, a click anywhere near a council's registers goes to them
    map.on("click", e => { if (map.getZoom() >= 7) return;
      let best = null, bd = 1.2; for (const [, c] of councils) { const d = Math.hypot(c.x / c.n - e.lngLat.lng, (c.y / c.n - e.lngLat.lat) * 1.7); if (d < bd) { bd = d; best = c; } }
      if (best) go(best.b, 40); });
    window.addEventListener("hmo-home", () => { state(on, { on: false }); on = null; map.fitBounds(GB, { padding: 20, animate: !STILL, duration: 900 }); });
    for (const b of document.querySelectorAll(".hmo-go")) b.addEventListener("click", () => {
      open(b.closest("tr").dataset.district, true); mapEl.scrollIntoView({ behavior: STILL ? "auto" : "smooth", block: "center" }); });
    const q = new URLSearchParams(location.search).get("district");
    if (q && byName.has(q.toUpperCase())) open(q.toUpperCase(), true);
  });
  drawLegend();
}

start();
