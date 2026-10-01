/* Licensed HMOs by postcode district.

   Every district is filled by its count at every scale, so the country seen
   whole is the districts themselves, not a blur over them (a heatmap until
   1 October 2026, which melted 600 districts into blobs). Their edges come
   in as the map closes on them, and a click opens one: how many licences,
   on which council's register, of what kind.

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
// The map's own ramp in light mode: the site's palest blue was too near the
// land for a district of a few licences to be seen with the country whole.
// Dark mode keeps the site's tokens, which already stand off a dark land.
const SEQ = DARK ? [1, 2, 3, 4, 5].map(i => token(`--seq-${i}`) || ["#24384f", "#31517a", "#4470a4", "#5f91cc", "#7ab3ee"][i - 1])
  : ["#bcd3ec", "#86acd8", "#5584c0", "#2c5f9f", "#0d3a78"];
const STEPS = [25, 100, 300, 700];                      // a district's licences: the edges between the five colours
const SEA = DARK ? "#0c1620" : "#d3e1ec", LAND = DARK ? "#1b1d21" : "#f3f2ec", COAST = DARK ? "#3c4048" : "#b3b6ad";
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
    map.addLayer({ id: "land", type: "fill", source: "areas", paint: { "fill-color": LAND } });
    map.addLayer({ id: "coast", type: "line", source: "areas", paint: { "line-color": COAST, "line-width": 0.6,
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 8, 0.25] } });
    // the districts these registers say nothing about: outlines only, and only up close
    map.addLayer({ id: "quiet", type: "fill", source: "districts", filter: ["==", ["get", "licences"], 0], minzoom: 7.5,
      paint: { "fill-color": COAST, "fill-opacity": ["case", ["boolean", ["feature-state", "on"], false], 0.35, 0] } });
    map.addLayer({ id: "quiet-line", type: "line", source: "districts", filter: ["==", ["get", "licences"], 0], minzoom: 7.5,
      paint: { "line-color": COAST, "line-width": 0.7, "line-opacity": ["interpolate", ["linear"], ["zoom"], 7.5, 0, 9, 0.8] } });
    // every district with licences, filled by its count, at every scale
    map.addLayer({ id: "count", type: "fill", source: "districts", filter: [">", ["get", "licences"], 0],
      paint: { "fill-color": ["step", ["get", "licences"], SEQ[0], STEPS[0], SEQ[1], STEPS[1], SEQ[2], STEPS[2], SEQ[3], STEPS[3], SEQ[4]],
        "fill-opacity": 0.92, "fill-antialias": true } });
    // edges between districts: hairlines seen whole, so the country is not a
    // mesh, firming up as the map closes in; the open district is outlined
    map.addLayer({ id: "count-line", type: "line", source: "districts", filter: [">", ["get", "licences"], 0],
      paint: { "line-color": ["case", ["boolean", ["feature-state", "on"], false], INK, LAND],
        // zoom must lead a paint expression, so the open district's width rides each stop
        "line-width": ["interpolate", ["linear"], ["zoom"],
          5, ["case", ["boolean", ["feature-state", "on"], false], 2.5, 0.15],
          8, ["case", ["boolean", ["feature-state", "on"], false], 2.5, 0.6],
          11, ["case", ["boolean", ["feature-state", "on"], false], 2.5, 1.2]],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.35, 8, 0.9] } });

    // names, as HTML: a council's name when the country is whole, a district's code up close
    const councils = new Map();
    for (const f of counted) for (const c of JSON.parse(f.properties.councils)) {
      const e = councils.get(c.council) || { n: 0, x: 0, y: 0, b: new LngLatBounds() };
      e.n += c.licences; e.x += f.properties.lon * c.licences; e.y += f.properties.lat * c.licences; e.b.extend(boundsOf(f.geometry)); councils.set(c.council, e);
    }
    const far = [], near = [];
    // beside the glow, not over it. Where councils are neighbours (five of them
    // are London boroughs) the one with more licences keeps its name and the
    // others wait until there is room: checked on every move, largest first.
    const placed = [...councils].map(([name, e]) => ({ name, e, lon: e.x / e.n, lat: e.y / e.n })).sort((a, b) => b.e.n - a.e.n);
    for (const c of placed) {
      const b = el("button", "hmo-place"); b.type = "button"; const more = el("span", "hmo-more");
      b.append(el("b", null, c.name.replace(/^London Borough of /, "")), el("span", null, `${fmt(c.e.n)} licences`), more);
      const m = new Marker({ element: b, anchor: "center" }).setLngLat([c.lon, c.lat]).addTo(map);
      m.size = null; m.bounds = c.e.b; m.more = more; m.group = [m]; far.push(m);
      // a label standing in for its hidden neighbours opens all of them
      b.addEventListener("click", ev => { ev.stopPropagation(); const g = new LngLatBounds(); for (const o of m.group) g.extend(o.bounds); go(g, 40); });
    }
    for (const f of counted) {
      const b = el("button", "hmo-district"); b.type = "button"; b.append(el("b", null, f.properties.district), el("span", null, fmt(f.properties.licences)));
      b.addEventListener("click", ev => { ev.stopPropagation(); open(f.properties.district, false); });
      const m = new Marker({ element: b, anchor: "center" }).setLngLat([f.properties.lon, f.properties.lat]).addTo(map);
      const bb = boundsOf(f.geometry); m.wide = (bb.getEast() - bb.getWest()) * Math.cos(f.properties.lat * Math.PI / 180);
      near.push(m);
    }
    const names = () => { const z = map.getZoom();
      // Councils whose points fall within 30px of a larger one's are its
      // neighbours at this scale (the London boroughs): one label stands for
      // them and says how many. Each shown label takes the first of four
      // places beside its point that stays inside the map and clear of the
      // labels already placed; largest council first.
      const W = mapEl.clientWidth, H = mapEl.clientHeight, shown = [], boxes = [];
      for (const m of far) {
        const e = m.getElement();
        m.group = [m];
        if (z >= 9) { e.hidden = true; continue; }
        if (!m.size) { e.hidden = false; m.more.hidden = true; m.size = [e.offsetWidth + 6, e.offsetHeight + 16]; }
        const p = map.project(m.getLngLat());
        const host = shown.find(o => Math.hypot(o.p.x - p.x, o.p.y - p.y) < 30);
        if (host) { host.m.group.push(m); e.hidden = true; continue; }
        const [w, h] = m.size, gap = 14;
        const spots = [[gap + w / 2, 0], [-gap - w / 2, 0], [0, -gap - h / 2], [0, gap + h / 2]];
        let best = null;
        for (const [dx, dy] of spots) {
          const cx = p.x + dx, cy = p.y + dy, box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2];
          const inside = box[0] >= 2 && box[1] >= 2 && box[2] <= W - 2 && box[3] <= H - 2;
          const clear = !boxes.some(o => box[0] < o[2] && o[0] < box[2] && box[1] < o[3] && o[1] < box[3]);
          if (clear && inside) { best = [dx, dy, box]; break; }
          if (clear && !best) best = [dx, dy, box];
        }
        if (!best) {
          const near = shown.reduce((a, o) => (!a || Math.hypot(o.p.x - p.x, o.p.y - p.y) < Math.hypot(a.p.x - p.x, a.p.y - p.y) ? o : a), null);
          if (near) near.m.group.push(m);
          e.hidden = true; continue;
        }
        e.hidden = false; m.setOffset([best[0], best[1]]);
        boxes.push(best[2]); shown.push({ m, p });
      }
      for (const b of shown) {
        const n = b.m.group.length - 1;
        b.m.more.hidden = !n;
        b.m.more.textContent = n ? `+${n} nearby` : "";
        b.m.getElement().title = n ? "With " + b.m.group.slice(1).map(o => o.getElement().querySelector("b").textContent).join(", ") : "";
      }
      // a district's code is shown once the district is wide enough on screen to hold it:
      // the WC and EC districts are a few streets each, and piled up over central London
      const px = 512 * Math.pow(2, z) / 360;
      for (const m of near) m.getElement().hidden = z < 9.2 || m.wide * px < 46; };
    map.on("move", names); names();

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
