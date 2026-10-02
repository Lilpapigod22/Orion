/* Market analysis chart — in the journal. Price + SMA20/SMA50 moving averages +
   support/resistance. Colours are checked for colour blindness on the dark background;
   SMA50 is also dashed because it is close to the price colour under deuteranopia. */
export const CHART = {
  price: '#2C9CCB', sma20: '#C2801F', sma50: '#9068D6',
  surface: '#07121C', grid: 'rgba(127,219,255,0.08)', text: '#BCD9E8', muted: '#5B8196',
};

export const fmtPrice = (v) => {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return Math.round(v).toLocaleString('en-GB');
  return a >= 10 ? v.toFixed(2) : Number(v.toPrecision(5)).toString();
};

// Round values for the scale: 1, 2, 2.5, 5 × 10^k.
function niceTicks(lo, hi, count = 4) {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(v);
  return ticks;
}

export function drawChart(canvas, data, hoverIndex = null) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const pad = { l: 4, r: 58, t: 8, b: 20 };
  const values = [...data.close, ...data.sma20, ...data.sma50, data.support, data.resistance]
    .filter((v) => v != null);
  let lo = Math.min(...values), hi = Math.max(...values);
  const margin = (hi - lo) * 0.06 || hi * 0.01;
  lo -= margin; hi += margin;
  const n = data.close.length;
  const x = (i) => pad.l + (i / Math.max(1, n - 1)) * (w - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (h - pad.t - pad.b);

  // Grid and scale on the right (as in trading platforms).
  ctx.font = '10px "JetBrains Mono", monospace';
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  for (const tick of niceTicks(lo, hi)) {
    ctx.strokeStyle = CHART.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.l, Math.round(y(tick)) + 0.5);
    ctx.lineTo(w - pad.r, Math.round(y(tick)) + 0.5);
    ctx.stroke();
    ctx.fillStyle = CHART.muted;
    ctx.fillText(fmtPrice(tick), w - pad.r + 6, y(tick));
  }
  ctx.textBaseline = 'alphabetic';
  [0, Math.floor((n - 1) / 2), n - 1].forEach((i, k) => {
    ctx.textAlign = ['left', 'center', 'right'][k];
    ctx.fillStyle = CHART.muted;
    ctx.fillText(data.time[i], x(i), h - 5);
  });

  // Support and resistance — thin labelled lines.
  for (const [label, level] of [['resistance', data.resistance], ['support', data.support]]) {
    if (level == null) continue;
    ctx.strokeStyle = 'rgba(188,217,232,0.35)';
    ctx.beginPath();
    ctx.moveTo(pad.l, y(level));
    ctx.lineTo(w - pad.r, y(level));
    ctx.stroke();
    // The label — on the right, on a dark backing so it does not blend into the lines.
    const text = `${label} ${fmtPrice(level)}`;
    const tw = ctx.measureText(text).width;
    const ty = y(level) + (label === 'support' ? 11 : -5);
    ctx.fillStyle = 'rgba(7,18,28,0.85)';
    ctx.fillRect(w - pad.r - tw - 16, ty - 9, tw + 6, 12);  // clear of the dot at the end
    ctx.fillStyle = CHART.text;
    ctx.textAlign = 'right';
    ctx.fillText(text, w - pad.r - 13, ty);
  }

  // A light wash under the price, then the lines.
  const wash = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
  wash.addColorStop(0, 'rgba(44,156,203,0.16)');
  wash.addColorStop(1, 'rgba(44,156,203,0)');
  ctx.beginPath();
  data.close.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.lineTo(x(n - 1), h - pad.b);
  ctx.lineTo(x(0), h - pad.b);
  ctx.fillStyle = wash;
  ctx.fill();

  const line = (series, color, width, dash = []) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = ctx.lineCap = 'round';
    ctx.setLineDash(dash);
    ctx.beginPath();
    let started = false;
    series.forEach((v, i) => {
      if (v == null) { started = false; return; }
      if (started) ctx.lineTo(x(i), y(v)); else { ctx.moveTo(x(i), y(v)); started = true; }
    });
    ctx.stroke();
    ctx.setLineDash([]);
  };
  line(data.sma50, CHART.sma50, 1.5, [6, 4]);
  line(data.sma20, CHART.sma20, 1.5);
  line(data.close, CHART.price, 2);

  // Dot at the end of the price — with a ring in the background colour.
  const dot = (i, v, color) => {
    ctx.beginPath();
    ctx.arc(x(i), y(v), 6, 0, Math.PI * 2);
    ctx.fillStyle = CHART.surface;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x(i), y(v), 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  };
  dot(n - 1, data.close[n - 1], CHART.price);

  if (hoverIndex != null) {
    ctx.strokeStyle = 'rgba(188,217,232,0.4)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(x(hoverIndex)) + 0.5, pad.t);
    ctx.lineTo(Math.round(x(hoverIndex)) + 0.5, h - pad.b);
    ctx.stroke();
    dot(hoverIndex, data.close[hoverIndex], CHART.price);
  }
  return { x, n, pad, w };
}
