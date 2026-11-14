// Interactive globe: D3 orthographic projection on a canvas with Natural Earth land.
// Drag to rotate, wheel or +/− to zoom, reset button; hotspots coloured by radiative
// power (FRP) with a hover tooltip. Ported from the prototype.
/* global d3 */
import { $, state } from './state.js';

const RAD = Math.PI / 180;
const AREA_VIEW = { Canada: { lon: -100, lat: 38 }, Argentina: { lon: -63, lat: -27 } };

let canvas, ctx;
let landGeo = null;
let points = [];                 // [lat, lon, frp, date]
let rotation = { ...AREA_VIEW.Canada };
let zoom = 1;
let dragging = false;
let lastPointer = null;

export function frpColour(frp) { return frp > 80 ? '#ff704c' : frp > 20 ? '#ffa45e' : '#f7d68c'; }

export function setPoints(pts) { points = pts; draw(); }

// Known areas have a hand-picked view; any other area centres on its own hotspots.
function areaView(area) {
  if (AREA_VIEW[area]) return AREA_VIEW[area];
  let lat = 0, lon = 0, n = 0;
  for (const day of Object.values(state.archive)) {
    for (const [la, lo] of day[area]?.points || []) { lat += la; lon += lo; n++; }
    if (n > 2000) break;
  }
  return n ? { lon: lon / n, lat: Math.max(-60, Math.min(60, lat / n)) } : AREA_VIEW.Canada;
}

export function fitArea() { rotation = { ...areaView(state.area) }; draw(); }

function size() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  return { w, h, r: Math.min(w * 0.40, (h - 215) * 0.48) * zoom, cx: w / 2, cy: (h - 180) / 2 + 5 };
}

function project(lon, lat) {
  const { r, cx, cy } = size();
  const l = (lon - rotation.lon) * RAD, p = lat * RAD, c = rotation.lat * RAD;
  const z = Math.sin(c) * Math.sin(p) + Math.cos(c) * Math.cos(p) * Math.cos(l);
  return { x: cx + r * Math.cos(p) * Math.sin(l), y: cy - r * (Math.cos(c) * Math.sin(p) - Math.sin(c) * Math.cos(p) * Math.cos(l)), z };
}

function line(coords, colour, width = 0.5) {
  ctx.beginPath();
  let pen = false;
  for (const v of coords) {
    const p = project(v[0], v[1]);
    if (p.z > 0) { if (pen) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y); pen = true; } else pen = false;
  }
  ctx.strokeStyle = colour;
  ctx.lineWidth = width;
  ctx.stroke();
}

export function resize() {
  if (!canvas || !canvas.clientWidth) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

export function draw() {
  if (!ctx || !canvas.width) return;
  const { w, h, r, cx, cy } = size();
  if (r <= 0) return;   // hidden (Report page, no-data notice) or too small to draw
  const dark = document.documentElement.dataset.theme !== 'light';
  ctx.clearRect(0, 0, w, h);
  const bg = ctx.createRadialGradient(cx, cy, r * 0.3, cx, cy, r * 1.8);
  bg.addColorStop(0, dark ? '#20332c' : '#d5e3d1');
  bg.addColorStop(1, dark ? '#111c18' : '#eef3e9');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  // Quiet star field and atmosphere.
  for (let i = 0; i < 90; i++) {
    const x = (i * 137.5) % w, y = (i * 77.31) % (h - 130);
    ctx.fillStyle = dark ? '#8da99b38' : '#61796422';
    ctx.fillRect(x, y, i % 7 === 0 ? 2 : 1, 1);
  }
  ctx.save();
  ctx.shadowColor = dark ? '#8ac7aa60' : '#739e8760';
  ctx.shadowBlur = 35;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = dark ? '#122b2c' : '#a9c7c5';
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.clip();
  const ocean = ctx.createRadialGradient(cx - r * 0.4, cy - r * 0.5, r * 0.1, cx, cy, r * 1.2);
  ocean.addColorStop(0, dark ? '#254b48' : '#d0e2d8');
  ocean.addColorStop(1, dark ? '#091c21' : '#85acae');
  ctx.fillStyle = ocean;
  ctx.fillRect(cx - r, cy - r, r * 2, r * 2);

  // Land, clipped at the visible hemisphere.
  if (landGeo && window.d3) {
    const projection = d3.geoOrthographic().translate([cx, cy]).scale(r).rotate([-rotation.lon, -rotation.lat]).clipAngle(90);
    const path = d3.geoPath(projection, ctx);
    ctx.beginPath();
    path(landGeo);
    ctx.fillStyle = dark ? '#426650' : '#8cab82';
    ctx.fill();
    ctx.strokeStyle = dark ? '#91b89855' : '#5a7b5b66';
    ctx.lineWidth = 0.65;
    ctx.stroke();
  }
  const grid = dark ? '#a7c8b71b' : '#244c4220';
  for (let lat = -60; lat <= 60; lat += 30) line(Array.from({ length: 181 }, (_, i) => [-180 + i * 2, lat]), grid);
  for (let lon = -180; lon < 180; lon += 30) line(Array.from({ length: 91 }, (_, i) => [lon, -90 + i * 2]), grid);

  for (const p of points) {
    const v = project(p[1], p[0]);
    if (v.z <= 0.02) continue;
    const colour = frpColour(p[2]);
    ctx.beginPath();
    ctx.arc(v.x, v.y, 3.2 + Math.min(p[2] / 130, 2), 0, Math.PI * 2);
    ctx.fillStyle = colour + '30';
    ctx.shadowBlur = 7;
    ctx.shadowColor = colour;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(v.x, v.y, 1.7 + Math.min(p[2] / 180, 1), 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  const shade = ctx.createRadialGradient(cx - r * 0.4, cy - r * 0.4, r * 0.1, cx, cy, r * 1.08);
  shade.addColorStop(0, '#00000000');
  shade.addColorStop(0.7, '#00000000');
  shade.addColorStop(1, '#00000070');
  ctx.fillStyle = shade;
  ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
  ctx.restore();
  ctx.beginPath();
  ctx.arc(cx, cy, r + 0.5, 0, Math.PI * 2);
  ctx.strokeStyle = dark ? '#b1e2c85c' : '#688d7660';
  ctx.lineWidth = 1.2;
  ctx.stroke();
}

function zoomBy(delta) { zoom = Math.max(0.75, Math.min(1.8, zoom + delta)); draw(); }

function hover(e) {
  const rect = canvas.getBoundingClientRect();
  let closest = null, best = 10;
  for (const p of points) {
    const v = project(p[1], p[0]);
    const dist = Math.hypot(v.x - (e.clientX - rect.left), v.y - (e.clientY - rect.top));
    if (v.z > 0 && dist < best) { best = dist; closest = p; }
  }
  const tip = $('globe-tooltip');
  if (closest) {
    tip.textContent = `${closest[3] || state.date} · ${closest[0].toFixed(3)}°, ${closest[1].toFixed(3)}° · ${closest[2].toFixed(1)} MW`;
    tip.hidden = false;
  } else tip.hidden = true;
}

export function initGlobe() {
  canvas = $('globe');
  ctx = canvas.getContext('2d');
  fetch('data/land.geojson')
    .then((r) => r.json())
    .then((data) => { landGeo = data; resize(); })
    .catch(() => { $('map-detail').textContent = 'Globe coastlines unavailable; observation markers remain available.'; });
  new ResizeObserver(resize).observe(canvas);

  canvas.addEventListener('pointerdown', (e) => {
    dragging = true;
    lastPointer = { x: e.clientX, y: e.clientY };
    canvas.setPointerCapture(e.pointerId);
    $('globe-tooltip').hidden = true;
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!dragging) { hover(e); return; }
    rotation.lon -= (e.clientX - lastPointer.x) * 0.4 / zoom;
    rotation.lat = Math.max(-80, Math.min(80, rotation.lat + (e.clientY - lastPointer.y) * 0.35 / zoom));
    lastPointer = { x: e.clientX, y: e.clientY };
    draw();
  });
  for (const evt of ['pointerup', 'pointercancel']) canvas.addEventListener(evt, () => { dragging = false; });
  canvas.addEventListener('pointerleave', () => { $('globe-tooltip').hidden = true; });
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); zoomBy(e.deltaY > 0 ? -0.08 : 0.08); }, { passive: false });
  $('zoom-in').onclick = () => zoomBy(0.15);
  $('zoom-out').onclick = () => zoomBy(-0.15);
  $('reset-globe').onclick = () => { zoom = 1; fitArea(); };
  document.addEventListener('firecal:fit-area', fitArea);
  document.addEventListener('firecal:theme', draw);
  document.addEventListener('firecal:page', resize);
}
