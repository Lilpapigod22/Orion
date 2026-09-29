/* ==========================================================================
   О.Р.И.О.Н. HUD — логика на интерфейса.

   Python -> JS:  window.hud.<функция>(...)          (виж app.py -> Orion.hud)
   JS -> Python:  window.pywebview.api.<метод>(...)  (виж app.py -> HudApi)
   ========================================================================== */
'use strict';

const $ = (id) => document.getElementById(id);
const api = () => (window.pywebview && window.pywebview.api) || null;
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

window.addEventListener('error', (e) => api()?.report_error(`${e.message} @ ${e.lineno}`));
window.addEventListener('unhandledrejection', (e) => api()?.report_error(String(e.reason)));

const STATE_LABELS = {
  boot: 'Инициализация',
  idle: 'В готовност',
  standby: 'Очаквам „Орион“',
  calibrating: 'Калибрирам микрофона',
  listening: 'Слушам',
  thinking: 'Обработвам',
  speaking: 'Говоря',
  offline: 'Ядрото е недостъпно',
  approval: 'Очаквам одобрение',
};

const STATUS_TEXT = {
  boot: 'Инициализация', offline: 'Офлайн', listening: 'Слуша', standby: 'Слуша',
  calibrating: 'Слуша', thinking: 'Мисли', speaking: 'Говори', idle: 'Онлайн', approval: 'Чака',
};

const pad = (n) => String(n).padStart(2, '0');
const clockTime = (d = new Date(), seconds = false) =>
  `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ''}`;

/* --------------------------------------------------------------------------
   Реакторът — рисува се в canvas, 60 кадъра в секунда.
   -------------------------------------------------------------------------- */
const COLORS = {
  holo: [127, 219, 255],
  amber: [255, 181, 71],
  alert: [255, 90, 78],
};

// spin = скорост на въртене, energy = базова яркост на ядрото, sweep = радарно сканиране
const MODES = {
  boot:        { color: 'holo',  spin: 0.9,  energy: 0.25 },
  idle:        { color: 'holo',  spin: 0.18, energy: 0.32 },
  standby:     { color: 'amber', spin: 0.12, energy: 0.22, sweep: 0.35 },
  calibrating: { color: 'amber', spin: 0.5,  energy: 0.3,  sweep: 1 },
  listening:   { color: 'amber', spin: 0.45, energy: 0.5,  sweep: 1 },
  thinking:    { color: 'holo',  spin: 2.6,  energy: 0.45 },
  speaking:    { color: 'holo',  spin: 0.3,  energy: 0.4 },
  offline:     { color: 'alert', spin: 0.05, energy: 0.15 },
  approval:    { color: 'amber', spin: 0.08, energy: 0.3 },
};

const reactor = {
  // Реакторът е ядрото на 3D мрежата: рисува се тук и mind.js го слага в центъра ѝ.
  canvas: document.createElement('canvas'),
  get ctx() { return this.canvas.getContext('2d'); },
  size: 0,
  dpr: 1,
  mode: MODES.boot,
  color: [...COLORS.holo],
  spin: MODES.boot.spin,
  sweep: 0,
  level: 0,
  rot: [0, 0, 0, 0],
  drawIn: 0,          // 0 -> 1 при стартиране: пръстените се „изписват“
  spectrum: new Float32Array(24),
  last: performance.now(),
  t: 0,

  // Размерът идва от mind.js — ядрото е толкова голямо, колкото мрежата около него позволява.
  resize(size) {
    this.dpr = window.devicePixelRatio || 1;
    this.size = size;
    this.canvas.width = this.canvas.height = Math.round(size * this.dpr);
  },

  // Вика се от mind.js веднъж на кадър.
  frame(now, dt) {
    this.last = now;
    this.t += dt;
    const ease = (k) => Math.min(1, dt * k);
    const motion = reduceMotion ? 0.15 : 1;

    const target = COLORS[this.mode.color];
    for (let i = 0; i < 3; i++) this.color[i] += (target[i] - this.color[i]) * ease(4);
    this.spin += (this.mode.spin - this.spin) * ease(3);
    this.sweep += ((this.mode.sweep || 0) - this.sweep) * ease(4);
    this.drawIn = Math.min(1, this.drawIn + dt / 1.6);

    // Нивото на „енергия“ идва от гласа, когато Орион говори; иначе — спокойно дишане.
    let targetLevel;
    if (voice.analyser && voice.playing) {
      voice.analyser.getByteFrequencyData(voice.bins);
      // 24 честотни ленти в обхвата на речта; по-високите се усилват, защото са по-тихи.
      let sum = 0;
      for (let i = 0; i < 24; i++) {
        const v = Math.min(1, (voice.bins[2 + Math.round(i * 1.6)] / 255) * (0.8 + i / 14));
        this.spectrum[i] += (v - this.spectrum[i]) * ease(18);
        sum += v;
      }
      targetLevel = Math.min(1, (sum / 24) * 2.2);
    } else {
      for (let i = 0; i < 24; i++) this.spectrum[i] *= 1 - ease(6);
      const breathe = this.mode === MODES.thinking ? Math.sin(this.t * 7) * 0.12 : Math.sin(this.t * 1.3) * 0.06;
      targetLevel = this.mode.energy + breathe * motion;
    }
    this.level += (targetLevel - this.level) * ease(voice.playing ? 20 : 4);

    const s = this.spin * motion;
    this.rot[0] += dt * s * 0.22;
    this.rot[1] -= dt * s * 0.55;
    this.rot[2] += dt * s * 0.09;
    this.rot[3] += dt * (0.8 + s) * 1.4 * motion;

    this.draw();
  },

  draw() {
    const { ctx, size, dpr, level, drawIn } = this;
    const [r, g, b] = this.color.map(Math.round);
    const rgba = (a) => `rgba(${r},${g},${b},${a})`;
    const R = size * 0.48;
    const u = R / 200; // мащаб: всички размери са за R = 200

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.translate(size / 2, size / 2);
    ctx.lineCap = 'butt';

    // 1. Външна скала с чертички.
    const ticks = 90;
    for (let i = 0; i < Math.floor(ticks * drawIn); i++) {
      const a = this.rot[0] + (i / ticks) * Math.PI * 2;
      const major = i % 5 === 0;
      const r1 = R, r2 = R - (major ? 11 : 5) * u;
      ctx.strokeStyle = rgba(major ? 0.55 : 0.22);
      ctx.lineWidth = (major ? 1.4 : 1) * u;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
      ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
      ctx.stroke();
    }

    // 2. Тънък пръстен.
    ctx.strokeStyle = rgba(0.16);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(0, 0, R * 0.9, 0, Math.PI * 2 * drawIn);
    ctx.stroke();

    // 3. Сегментирани дъги — въртят се обратно; при „мислене“ са бързи.
    const arcs = [[0, 0.95], [1.25, 2.2], [2.5, 2.8], [3.3, 4.7], [5.0, 5.85]];
    ctx.lineWidth = 2.2 * u;
    ctx.strokeStyle = rgba(0.75);
    for (const [a0, a1] of arcs) {
      ctx.beginPath();
      ctx.arc(0, 0, R * 0.8, this.rot[1] + a0 * drawIn, this.rot[1] + a1 * drawIn);
      ctx.stroke();
    }

    // 4. Радарно сканиране, докато Орион слуша (кехлибарено).
    if (this.sweep > 0.02 && ctx.createConicGradient) {
      const grad = ctx.createConicGradient(this.rot[3], 0, 0);
      grad.addColorStop(0, rgba(0.32 * this.sweep));
      grad.addColorStop(0.18, rgba(0));
      grad.addColorStop(1, rgba(0));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, R * 0.76, 0, Math.PI * 2);
      ctx.arc(0, 0, R * 0.62, 0, Math.PI * 2, true);
      ctx.fill();
    }

    // 5. Спектър на гласа — лъчи около ядрото в четири огледални дяла,
    //    така че гласът „диша“ равномерно по целия кръг.
    const bars = 96;
    ctx.lineWidth = 2 * u;
    for (let i = 0; i < bars; i++) {
      const q = i % 48;
      const v = this.spectrum[q < 24 ? q : 47 - q];
      if (v < 0.02) continue;
      const a = -Math.PI / 2 + (i / bars) * Math.PI * 2;
      const r1 = R * 0.645, r2 = r1 + v * R * 0.2;
      ctx.strokeStyle = rgba(0.25 + v * 0.6);
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
      ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
      ctx.stroke();
    }

    // 6. Бобините на реактора — 10 сегмента, светят според енергията.
    const coils = 10, gap = 0.075;
    const inner = R * 0.44, outer = R * 0.6;
    for (let i = 0; i < coils; i++) {
      if (i / coils > drawIn) break;
      const a0 = this.rot[2] + (i / coils) * Math.PI * 2 + gap;
      const a1 = this.rot[2] + ((i + 1) / coils) * Math.PI * 2 - gap;
      ctx.beginPath();
      ctx.arc(0, 0, outer, a0, a1);
      ctx.arc(0, 0, inner, a1 - 0.02, a0 + 0.02, true);
      ctx.closePath();
      ctx.fillStyle = rgba(0.08 + level * 0.42);
      ctx.fill();
      ctx.strokeStyle = rgba(0.55);
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // 7. Вътрешен светещ пръстен.
    ctx.save();
    ctx.shadowColor = rgba(0.9);
    ctx.shadowBlur = (10 + level * 26) * u;
    ctx.strokeStyle = rgba(0.85);
    ctx.lineWidth = 2.6 * u;
    ctx.beginPath();
    ctx.arc(0, 0, R * 0.38, 0, Math.PI * 2 * drawIn);
    ctx.stroke();
    ctx.restore();

    // 8. Ядро — бяло-сините му размери следват гласа.
    const coreR = R * (0.25 + level * 0.11) * drawIn;
    if (coreR > 1) {
      const core = ctx.createRadialGradient(0, 0, 0, 0, 0, coreR);
      core.addColorStop(0, `rgba(255,255,255,${0.75 + level * 0.25})`);
      core.addColorStop(0.3, rgba(0.55 + level * 0.35));
      core.addColorStop(1, rgba(0));
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(0, 0, coreR, 0, Math.PI * 2);
      ctx.fill();
    }
  },
};

/* --------------------------------------------------------------------------
   Гласът — пуска MP3 от Python и подава честотите на реактора.
   -------------------------------------------------------------------------- */
const voice = {
  el: $('voice'),
  ctx: null,
  analyser: null,
  bins: null,
  playing: false,
  url: null,

  graph() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      const source = this.ctx.createMediaElementSource(this.el);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.6;
      this.bins = new Uint8Array(this.analyser.frequencyBinCount);
      source.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
  },

  play(b64) {
    this.stop(false);
    try { this.graph(); } catch (err) { api()?.report_error(`audio graph: ${err}`); }
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    this.url = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
    this.el.src = this.url;
    this.playing = true;
    this.el.play()
      .then(() => hud.setState('speaking'))
      .catch((err) => { api()?.report_error(`play: ${err}`); this.finish(); });
  },

  finish() {
    if (!this.playing) return;
    this.playing = false;
    if (this.url) { URL.revokeObjectURL(this.url); this.url = null; }
    api()?.speech_finished();
  },

  stop(notify = true) {
    this.el.pause();
    if (notify) this.finish();
    else this.playing = false;
  },
};
voice.el.addEventListener('ended', () => voice.finish());
voice.el.addEventListener('error', () => voice.finish());

/* --------------------------------------------------------------------------
   Функции, които Python вика: hud.setState(...), hud.addLog(...) и т.н.
   -------------------------------------------------------------------------- */
const log = $('log');
const subtitle = $('subtitle');
const WHO = {
  user: 'Сър', orion: 'Орион', tool: '▸ умение', evolve: '▸ развитие', system: 'Система', guide: '▸ подсказка',
  claude: '▸ Claude', chart: '▸ пазар', test: '▸ тест', reels: '▸ рийлове',
};

/* --------------------------------------------------------------------------
   Графика на пазарния анализ — в журнала. Цена + средни линии SMA20/SMA50 +
   подкрепа/съпротива. Цветовете са проверени за далтонизъм върху тъмния фон;
   SMA50 е и пунктирана, защото е близо до цвета на цената при деутеранопия.
   -------------------------------------------------------------------------- */
const CHART = {
  price: '#2C9CCB', sma20: '#C2801F', sma50: '#9068D6',
  surface: '#07121C', grid: 'rgba(127,219,255,0.08)', text: '#BCD9E8', muted: '#5B8196',
};

// Отговорите на Claude идват с markdown: **удебелено**, `код`, # заглавия. Показваме ги
// като текст с удебелявания — без innerHTML, така че нищо от отговора не се изпълнява.
function markdownLite(text) {
  const nodes = [];
  const clean = text.replace(/^#{1,6}\s+/gm, '').replace(/^\s*[-*]\s+/gm, '• ');
  for (const part of clean.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)) {
    if (!part) continue;
    if (part.startsWith('**') && part.endsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      nodes.push(strong);
    } else if (part.startsWith('`') && part.endsWith('`')) {
      const code = document.createElement('code');
      code.textContent = part.slice(1, -1);
      nodes.push(code);
    } else {
      nodes.push(document.createTextNode(part));
    }
  }
  return nodes;
}

const fmtPrice = (v) => {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return Math.round(v).toLocaleString('bg-BG').replace(/ /g, ' ');
  return a >= 10 ? v.toFixed(2) : Number(v.toPrecision(5)).toString();
};

// Кръгли стойности за скалата: 1, 2, 2.5, 5 × 10^k.
function niceTicks(lo, hi, count = 4) {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(v);
  return ticks;
}

function drawChart(canvas, data, hoverIndex = null) {
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

  // Решетка и скала вдясно (като в програмите за търговия).
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

  // Подкрепа и съпротива — тънки линии с надпис.
  for (const [label, level] of [['съпротива', data.resistance], ['подкрепа', data.support]]) {
    if (level == null) continue;
    ctx.strokeStyle = 'rgba(188,217,232,0.35)';
    ctx.beginPath();
    ctx.moveTo(pad.l, y(level));
    ctx.lineTo(w - pad.r, y(level));
    ctx.stroke();
    // Надписът — вдясно, върху тъмна подложка, за да не се слива с линиите.
    const text = `${label} ${fmtPrice(level)}`;
    const tw = ctx.measureText(text).width;
    const ty = y(level) + (label === 'подкрепа' ? 11 : -5);
    ctx.fillStyle = 'rgba(7,18,28,0.85)';
    ctx.fillRect(w - pad.r - tw - 16, ty - 9, tw + 6, 12);  // встрани от точката в края
    ctx.fillStyle = CHART.text;
    ctx.textAlign = 'right';
    ctx.fillText(text, w - pad.r - 13, ty);
  }

  // Лек воал под цената, после линиите.
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

  // Точка в края на цената — с пръстен в цвета на фона.
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

const hud = {
  state: 'boot',

  setState(state) {
    if (!MODES[state]) return;
    // Докато звукът тече, реакторът остава в режим „говоря“.
    if (voice.playing && state !== 'speaking') return;
    this.state = state;
    document.body.dataset.state = state;
    reactor.mode = MODES[state];
    $('state-label').textContent = STATE_LABELS[state];
    $('status-text').textContent = STATUS_TEXT[state];
    $('btn-mic').setAttribute('aria-pressed', String(state === 'listening'));
  },

  addLog(kind, text) {
    log.querySelector('.log-empty')?.remove();
    const li = document.createElement('li');
    li.className = `entry entry--${kind}`;
    const time = document.createElement('time');
    time.textContent = clockTime();
    const who = document.createElement('b');
    who.textContent = WHO[kind] || kind;
    const p = document.createElement('p');
    if (kind === 'claude') p.replaceChildren(...markdownLite(text));
    else p.textContent = text;
    li.append(time, who, p);
    log.append(li);
    li.scrollIntoView({ block: 'end', behavior: reduceMotion ? 'auto' : 'smooth' });
  },

  setSubtitle(text, isUser = false) {
    subtitle.classList.add('is-fading');
    setTimeout(() => {
      subtitle.textContent = text;
      subtitle.classList.toggle('is-user', isUser);
      subtitle.classList.remove('is-fading');
    }, reduceMotion ? 0 : 150);
  },

  say(text) {
    this.addLog('orion', text);
    this.setSubtitle(text);
    refocus();
  },

  heard(text) {
    this.setSubtitle(text, true);
  },

  playAudio(b64) {
    // Гласът е изключен, докато отговорът се е синтезирал — не го пускаме.
    if (!$('sw-voice').checked) { api()?.speech_finished(); return; }
    voice.play(b64);
  },
  stopAudio() { voice.stop(); },

  bootLine(id, label, status, detail) {
    const box = $('boot');
    let li = box.querySelector(`[data-id="${id}"]`);
    if (!li) {
      li = document.createElement('li');
      li.dataset.id = id;
      li.innerHTML = '<span class="label"></span><span class="detail"></span><span class="mark"></span>';
      box.append(li);
    }
    li.className = `is-${status}`;
    li.querySelector('.label').textContent = label;
    li.querySelector('.detail').textContent = detail || '';
    li.querySelector('.mark').textContent = { ok: 'ОК', run: '···', fail: 'ГРЕШКА' }[status] || '';
    li.title = detail || '';
  },

  // При успех списъкът с проверки отстъпва място на субтитрите.
  // При грешка остава на екрана, за да се вижда какво не е наред.
  bootDone(ok) {
    if (ok) setTimeout(() => document.body.classList.add('booted'), 700);
    else this.setState('offline');
  },

  // Какво мисли и прави Орион — показва се в 3D мрежата (mind.js).
  toolStart(name, args, module, label) { mind.taskStart(name, args, module, label); },
  toolDone(name, result, ok) { mind.taskDone(name, result, ok); },
  thought(text) { mind.think(text); },
  setReminders(items) { mind.setReminders(items); },

  // Графиката на пазарния анализ — нов запис в журнала с легенда и стойности при посочване.
  showChart(data) {
    this.addLog('chart', '');
    const li = log.lastElementChild;
    const p = li.querySelector('p');
    const change = data.change >= 0 ? `+${data.change.toFixed(1)}%` : `${data.change.toFixed(1)}%`;
    const frame = { '1h': 'часови', '4h': '4-часови', '1d': 'дневни', '1wk': 'седмични' }[data.timeframe] || data.timeframe;
    p.innerHTML = `
      <span class="chart-title"></span>
      <span class="chart-meta"></span>
      <span class="chart-legend">
        <span><i style="background:${CHART.price}"></i>Цена</span>
        <span><i style="background:${CHART.sma20}"></i>SMA 20</span>
        <span><i class="dashed" style="color:${CHART.sma50}"></i>SMA 50</span>
      </span>
      <span class="chart-box"><canvas></canvas><span class="chart-tip" hidden></span></span>`;
    p.querySelector('.chart-title').textContent = `${data.name} · ${fmtPrice(data.close.at(-1))} ${data.currency || ''}`;
    p.querySelector('.chart-meta').textContent = `${frame} свещи · ${change}`;
    const canvas = p.querySelector('canvas');
    const tip = p.querySelector('.chart-tip');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', `${data.name}: цена ${fmtPrice(data.close.at(-1))}, подкрепа ${fmtPrice(data.support)}, съпротива ${fmtPrice(data.resistance)}`);
    let geometry = drawChart(canvas, data);
    new ResizeObserver(() => { geometry = drawChart(canvas, data); }).observe(canvas);
    canvas.addEventListener('pointermove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const frac = (e.clientX - rect.left - geometry.pad.l) / (geometry.w - geometry.pad.l - geometry.pad.r);
      const i = Math.max(0, Math.min(geometry.n - 1, Math.round(frac * (geometry.n - 1))));
      geometry = drawChart(canvas, data, i);
      tip.hidden = false;
      tip.replaceChildren();
      const rows = [[null, data.time[i]], [CHART.price, `Цена ${fmtPrice(data.close[i])}`],
        [CHART.sma20, `SMA 20 ${fmtPrice(data.sma20[i])}`], [CHART.sma50, `SMA 50 ${fmtPrice(data.sma50[i])}`]];
      for (const [color, text] of rows) {
        const row = document.createElement('span');
        if (color) { const key = document.createElement('i'); key.style.background = color; row.append(key); }
        row.append(text);
        tip.append(row);
      }
      const left = geometry.x(i) + 12;
      tip.style.left = `${Math.min(left, rect.width - tip.offsetWidth - 4)}px`;
    });
    canvas.addEventListener('pointerleave', () => { tip.hidden = true; geometry = drawChart(canvas, data); });
    li.scrollIntoView({ block: 'end' });
  },

  setTelemetry({ model, skills, docs, lessons }) {
    const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;
    $('tele-model').textContent = [model, count(skills, 'умение', 'умения'), `${docs} док.`,
      count(lessons, 'поука', 'поуки')].join(' · ');
  },

  // Код, написан от Орион: показва го и чака решение. При поправка — само разликата.
  showApproval({ kind, title, reason, code, diff, warnings, tools, attempts }) {
    $('approval-kind').textContent = kind === 'create'
      ? `Ново умение · проверено от опит ${attempts}`
      : `Поправка на умение · проверена от опит ${attempts}`;
    $('approval-title').textContent = tools.length ? tools.join(', ') : title;
    $('approval-reason').textContent = reason;

    const list = $('approval-warnings');
    list.replaceChildren(...warnings.map((w) => {
      const li = document.createElement('li');
      li.textContent = `⚠ ${w}`;
      return li;
    }));
    list.hidden = !warnings.length;

    const pre = $('approval-code');
    if (diff) {
      pre.replaceChildren(...diff.replace(/\n$/, '').split('\n').map((line) => {
        const span = document.createElement('span');
        span.textContent = line || ' ';
        span.className = line.startsWith('+') && !line.startsWith('+++') ? 'line add'
          : line.startsWith('-') && !line.startsWith('---') ? 'line del'
          : line.startsWith('@@') ? 'line hunk' : 'line';
        return span;
      }));
    } else {
      pre.textContent = code;
    }
    pre.scrollTop = 0;
    pre.hidden = false;
    $('approval-reason').hidden = false;
    $('approval-accept').textContent = 'Одобри и включи';
    $('approval').classList.remove('approval--confirm');
    $('approval').hidden = false;
    $('approval-accept').focus();
  },

  // Действие, което не може да се върне (изпращане на писмо, изтриване): текстът и бутон.
  showConfirm({ title, summary, body, accept }) {
    $('approval-kind').textContent = title;
    $('approval-title').textContent = summary;
    $('approval-reason').hidden = true;
    $('approval-warnings').hidden = true;
    const pre = $('approval-code');
    pre.textContent = body;
    pre.hidden = !body;
    pre.scrollTop = 0;
    $('approval-accept').textContent = accept;
    $('approval').classList.add('approval--confirm');
    $('approval').hidden = false;
    // Фокусът е на „Откажи“: случайно натиснат Enter не изпраща нищо.
    $('approval-reject').focus();
  },

  hideApproval() {
    $('approval').hidden = true;
    refocus();
  },

  setSwitch(name, value) {
    const input = { wake: $('sw-wake'), voice: $('sw-voice'), test: $('sw-test') }[name];
    if (input) input.checked = Boolean(value);
    if (name === 'test' && !value) this.setTest({ active: false });
  },

  // Тест режим: докъде е стигнала самопроверката (горе, до състоянието).
  setTest({ active, text }) {
    const chip = $('tele-test');
    chip.hidden = !active;
    chip.textContent = active ? `тест · ${text || 'подготвям'}` : '';
  },

  // Рийлове от YouTube: докъде е стигнала фоновата работа.
  setReels({ active, text }) {
    const chip = $('tele-reels');
    chip.hidden = !active;
    chip.textContent = active ? `рийлове · ${text || 'започвам'}` : '';
  },
};
window.hud = hud;

/* --------------------------------------------------------------------------
   Управление: бутони, клавиши, превключватели.
   -------------------------------------------------------------------------- */
// Полето за писане винаги е готово, освен ако потребителят не е избрал друг елемент.
function refocus() {
  const active = document.activeElement;
  if (!active || active === document.body) $('command-input').focus({ preventScroll: true });
}
window.addEventListener('focus', refocus);

function talk() {
  if (voice.playing) { voice.stop(); return; }   // Докосване по време на говор = прекъсване.
  api()?.listen();
}

// Решение за кода, написан от Орион. Прозорецът се скрива веднага; Python продължава.
function decide(approved) {
  if (voice.playing) voice.stop();
  $('approval').hidden = true;
  api()?.resolve_approval(approved);
}
$('approval-accept').addEventListener('click', () => decide(true));
$('approval-reject').addEventListener('click', () => decide(false));

$('reactor-btn').addEventListener('click', talk);
$('btn-mic').addEventListener('click', talk);

$('command').addEventListener('submit', (e) => {
  e.preventDefault();
  const input = $('command-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  if (voice.playing) voice.stop();
  api()?.send_text(text);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'F2') { e.preventDefault(); talk(); }
  if (e.key === 'Escape' && voice.playing) { e.preventDefault(); voice.stop(); }
  else if (e.key === 'Escape' && !$('approval').hidden) { e.preventDefault(); decide(false); }
});

$('sw-wake').addEventListener('change', (e) => api()?.set_always_listen(e.target.checked));
$('sw-voice').addEventListener('change', (e) => {
  if (!e.target.checked && voice.playing) voice.stop();
  api()?.set_muted(!e.target.checked);
});
$('sw-test').addEventListener('change', (e) => api()?.set_test_mode(e.target.checked));

let maximized = false;
const toggleMaximize = () => {
  maximized = !maximized;
  $('btn-max').setAttribute('aria-label', maximized ? 'Нормален размер' : 'Цял екран');
  api()?.window_maximize(maximized);
};
$('btn-min').addEventListener('click', () => api()?.window_minimize());
$('btn-max').addEventListener('click', toggleMaximize);
$('btn-close').addEventListener('click', () => api()?.window_close());
// На цял екран горната лента не мести прозореца (изпълнява се преди обработката на pywebview).
document.querySelector('.topbar').addEventListener('mousedown', (e) => {
  if (maximized && !e.target.closest('.winctl')) e.stopPropagation();
});
document.querySelector('.topbar').addEventListener('dblclick', (e) => {
  if (!e.target.closest('.winctl')) toggleMaximize();
});

/* --------------------------------------------------------------------------
   Старт.
   -------------------------------------------------------------------------- */
const tick = () => { $('tele-clock').textContent = clockTime(new Date(), true); };
tick();
setInterval(tick, 1000);
$('session-start').textContent = `сесия от ${clockTime()}`;

// Анимацията (3D мрежата с реактора в центъра) се пуска от mind.js.

window.addEventListener('pywebviewready', async () => {
  const settings = await api().start();
  hud.setSwitch('wake', settings.alwaysListen);
  hud.setSwitch('voice', !settings.muted);
  hud.setSwitch('test', settings.testMode);
  maximized = Boolean(settings.maximized);
  $('command-input').focus();
});
