/* ==========================================================================
   Мрежата на Орион — 3D холограма на мисленето му.

   В центъра е ядрото (реакторът, който пулсира с гласа). Около него —
   балончета за всяка способност, свързани с ядрото, и облак от неврони.
   Когато Орион използва умение, импулс тръгва от ядрото към балончето и до
   него изскача балонче-задача с това, което прави, после — с резултата.
   Мислите на модела се появяват до ядрото. Мрежата се върти с мишката.

   Всичко е нарисувано в canvas с перспективна проекция — без библиотеки.
   ========================================================================== */
'use strict';

const TAU = Math.PI * 2;

// Способностите на Орион. `tools` — кои умения светят това балонче.
const NODES = [
  { id: 'ear', label: 'Слух', about: 'Чува Ви, когато кажете „Орион“ или натиснете F2.' },
  { id: 'voice', label: 'Глас', about: 'Гласът, с който Ви отговаря.' },
  { id: 'clock', label: 'Часовник', tools: ['get_current_time', 'days_until_date'],
    about: 'Час, дата, ден от седмицата и часът по света.' },
  { id: 'weather', label: 'Прогноза', tools: ['get_weather'], about: 'Времето навън във всеки град.' },
  { id: 'calc', label: 'Сметки', tools: ['calculate', 'convert_units', 'convert_currency'],
    about: 'Точни изчисления, мерни единици и валути по днешния курс.' },
  { id: 'apps', label: 'Програми', tools: ['open_program', 'open_website', 'list_games'],
    about: 'Отваря програми, игри (Steam, Riot, Epic) и сайтове.' },
  { id: 'markets', label: 'Пазари', tools: ['market_price', 'analyze_market', 'analyze_price_file', 'market_overview', 'crypto_market'],
    about: 'Акции, крипто, валути, злато — цени и технически анализ с графика. Не е инвестиционен съвет.' },
  { id: 'claude', label: 'Claude', tools: ['ask_claude', 'send_to_claude_app'],
    about: 'Пита Claude за сложни задачи или му пише в приложението.' },
  { id: 'tools', label: 'Инструменти', about: 'Пароли, зар и монета, QR кодове, кодиране, статистика, проценти.' },
  { id: 'net', label: 'Мрежа', about: 'Скорост на интернета, IP, пинг, работи ли сайт, портове, Docker.' },
  { id: 'places', label: 'Места', about: 'Държави, разстояния, маршрути и „какво има наблизо“ в Google Maps.' },
  { id: 'web', label: 'Интернет', tools: ['search_web', 'read_webpage', 'wikipedia'],
    about: 'Търси в интернет, чете страници и проверява фактите в Уикипедия.' },
  { id: 'media', label: 'Музика', tools: ['play_on_youtube', 'media_control', 'set_volume', 'change_volume', 'mute_sound'],
    about: 'Пуска песни в YouTube, пауза и следваща песен, силата на звука. Реже рийлове от клипове.' },
  { id: 'system', label: 'Система', tools: ['system_status', 'close_program', 'power_action'],
    about: 'Състоянието на компютъра, затваряне на програми, заключване и изключване.' },
  { id: 'screen', label: 'Зрение', tools: ['look_at_screen', 'look_at_image', 'take_screenshot', 'read_clipboard', 'copy_to_clipboard'],
    about: 'Гледа екрана и снимки, чете копирания текст. Снимките остават на компютъра.' },
  { id: 'files', label: 'Файлове', tools: ['open_folder', 'find_files', 'open_file'],
    about: 'Намира и отваря файлове и папки.' },
  { id: 'mail', label: 'Поща', tools: ['check_email', 'read_email', 'send_email', 'reply_email'],
    about: 'Gmail: чете, отговаря и изпраща — само след Вашето „Изпрати“.' },
  { id: 'calendar', label: 'Календар', tools: ['calendar_events', 'calendar_add_event', 'calendar_delete_event'],
    about: 'Google Календар: срещи и събития.' },
  { id: 'tasks', label: 'Задачи', tools: ['tasks_list', 'tasks_add', 'tasks_complete'],
    about: 'Google Задачи: какво имате да свършите.' },
  { id: 'reminders', label: 'Напомняния', tools: ['set_reminder', 'set_timer', 'list_reminders', 'cancel_reminder'],
    about: 'Напомняния и таймери — казва ги на глас.' },
  { id: 'memory', label: 'Памет', tools: ['remember', 'learn_lesson', 'list_lessons', 'forget_lesson'],
    about: 'Запомня факти за Вас и поуки от грешките си.' },
  { id: 'evolve', label: 'Развитие', tools: ['create_skill', 'improve_skill', 'undo_skill_change', 'recent_errors'],
    about: 'Пише и поправя собствените си умения — след Вашето одобрение.' },
];

// Групите умения (модулите в skills/) -> балончето, което светва за тях.
const MODULE_NODES = {
  'skills.util_skills': 'tools', 'skills.finance_skills': 'calc', 'skills.notes_skills': 'memory',
  'skills.time_skills': 'clock', 'skills.weather_skills': 'weather', 'skills.net_skills': 'net',
  'skills.file_skills': 'files', 'skills.windows_skills': 'system', 'skills.places_skills': 'places',
  'skills.media_skills': 'media', 'skills.trading_skills': 'markets', 'skills.language_skills': 'web',
  'skills.assistant_skills': 'memory', 'skills.reels_skills': 'media',
};

const shortUrl = (url = '') => url.replace(/^https?:\/\/(www\.)?/, '').split(/[/?#]/)[0];
const quoted = (s = '') => `„${String(s).slice(0, 34)}${String(s).length > 34 ? '…' : ''}“`;

// Какво прави умението — надписът на балончето-задача.
const TASK_TEXT = {
  get_current_time: (a) => (a.city ? `часът в ${a.city}` : 'точният час'),
  days_until_date: (a) => `дни до ${a.date_str}`,
  get_weather: (a) => (a.city ? `времето в ${a.city}` : 'времето навън'),
  calculate: (a) => a.expression,
  make_youtube_reels: (a) => `рийлове · ${a.count || 3} × ${a.seconds || 45} с`,
  analyze_youtube_video: () => 'най-гледаните моменти',
  open_program: (a) => `отварям ${a.name}`,
  open_website: (a) => `отварям ${shortUrl(a.url)}`,
  search_web: (a) => `търся ${quoted(a.query)}`,
  read_webpage: (a) => `чета ${shortUrl(a.url)}`,
  check_email: (a) => (a.search ? `писма: ${a.search}` : 'нови писма'),
  read_email: (a) => `чета писмо ${a.number || 1}`,
  send_email: (a) => `писмо до ${a.to}`,
  reply_email: (a) => `отговор на писмо ${a.number}`,
  calendar_events: (a) => `календар · ${a.day || 'днес'}`,
  calendar_add_event: (a) => `записвам ${quoted(a.title)}`,
  calendar_delete_event: (a) => `изтривам ${quoted(a.title)}`,
  tasks_list: () => 'списъкът със задачи',
  tasks_add: (a) => `задача ${quoted(a.title)}`,
  tasks_complete: (a) => `свършено: ${a.title}`,
  set_reminder: (a) => `напомняне ${a.when_text}`,
  set_timer: (a) => `таймер ${a.duration}`,
  list_reminders: () => 'чакащи напомняния',
  cancel_reminder: (a) => `отменям ${a.what || 'всички'}`,
  remember: () => 'запомням',
  learn_lesson: () => 'уча поука',
  list_lessons: () => 'поуките ми',
  forget_lesson: () => 'забравям поука',
  create_skill: () => 'пиша ново умение',
  improve_skill: (a) => `поправям ${a.tool_name || 'умение'}`,
  undo_skill_change: () => 'връщам промяна',
  recent_errors: () => 'последните грешки',
  wikipedia: (a) => `Уикипедия: ${a.topic}`,
  convert_units: (a) => `${a.value} ${a.from_unit} → ${a.to_unit}`,
  convert_currency: (a) => `${a.amount} ${a.from_currency} → ${a.to_currency}`,
  play_on_youtube: (a) => `пускам ${quoted(a.query)}`,
  media_control: (a) => ({ play: 'пусни', pause: 'пауза', next: 'следваща', previous: 'предишна', stop: 'стоп' }[a.action] || a.action),
  set_volume: (a) => `звук ${a.level}%`,
  change_volume: (a) => `звук ${a.amount > 0 ? '+' : ''}${a.amount}%`,
  mute_sound: (a) => (a.mute === false ? 'звукът обратно' : 'заглушавам'),
  system_status: () => 'състояние на компютъра',
  close_program: (a) => `затварям ${a.name}`,
  power_action: (a) => ({ lock: 'заключвам', sleep: 'приспивам', shutdown: 'изключване', restart: 'рестарт', cancel: 'отменям изключването' }[a.action] || a.action),
  look_at_screen: () => 'гледам екрана',
  look_at_image: () => 'гледам снимката',
  take_screenshot: () => 'снимка на екрана',
  read_clipboard: () => 'чета копираното',
  copy_to_clipboard: () => 'копирам',
  open_folder: (a) => `папка ${a.name}`,
  find_files: (a) => `търся файл ${quoted(a.query)}`,
  open_file: (a) => `отварям файл ${a.number || 1}`,
  list_games: () => 'игрите ми',
  market_price: (a) => `цена: ${a.asset}`,
  analyze_market: (a) => `анализ ${a.asset} · ${a.timeframe || '1d'}`,
  analyze_price_file: (a) => `анализ на ${a.file_name}`,
  market_overview: () => 'пазарите днес',
  crypto_market: () => 'крипто пазарът',
  ask_claude: (a) => `питам Claude: ${quoted(a.question)}`,
  send_to_claude_app: () => 'пиша в Claude',
};

// Възпроизводим „случаен“ генератор — мрежата изглежда еднакво при всяко пускане.
function seeded(seed) {
  return () => {
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Равномерно разпределени точки по сфера (спирала на Фибоначи).
function sphere(n, radius, { jitter = 0, squash = 1, rand = Math.random } = {}) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  return Array.from({ length: n }, (_, i) => {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const k = radius * (1 + (rand() - 0.5) * jitter);
    return [Math.cos(golden * i) * r * k, y * k * squash, Math.sin(golden * i) * r * k];
  });
}

const mind = {
  canvas: $('mind'),
  ctx: $('mind').getContext('2d'),
  w: 0, h: 0, dpr: 1, R: 100, cx: 0, cy: 0, coreSize: 0,
  yaw: 0.35, pitch: 0.34, spin: 0, drag: null, hover: null, pinned: null,
  t: 0, last: performance.now(), build: 0,
  nodes: [], neurons: [], links: [], signals: [], pulses: [], tasks: [], reminders: [], thought: null,
  proj: new Map(),

  init() {
    const rand = seeded(7);
    // Балончетата са като корона около ядрото: в кръг, редуващо се по-горе и по-долу —
    // така не се застъпват и мрежата изглежда като орбита.
    this.nodes = NODES.map((node, i) => {
      const a = (i / NODES.length) * TAU;
      const r = (i % 2 ? 1.04 : 1.3) + (rand() - 0.5) * 0.08;  // два пръстена — надписите не се застъпват
      const y = (i % 2 ? 0.3 : -0.26) + (rand() - 0.5) * 0.1;
      return { ...node, pos: [Math.cos(a) * r, y, Math.sin(a) * r], act: 0, lastDone: -99, index: i };
    });
    this.toolNode = new Map();
    for (const node of this.nodes) for (const tool of node.tools || []) this.toolNode.set(tool, node);

    this.neurons = sphere(200, 1.75, { jitter: 0.2, squash: 0.72, rand });
    // Всеки неврон се свързва с най-близките си съседи — така се получава мрежата.
    const seen = new Set();
    this.neurons.forEach((a, i) => {
      this.neurons
        .map((b, j) => [j, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])])
        .filter(([j, d]) => j !== i && d < 0.46)
        .sort((x, y) => x[1] - y[1])
        .slice(0, 3)
        .forEach(([j]) => {
          const key = i < j ? `${i}-${j}` : `${j}-${i}`;
          if (!seen.has(key)) { seen.add(key); this.links.push([i, j]); }
        });
    });

    this.bindPointer();
    this.resize();
    new ResizeObserver(() => this.resize()).observe(document.querySelector('.stage'));
    requestAnimationFrame((now) => this.frame(now));
  },

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.dpr = window.devicePixelRatio || 1;
    this.w = rect.width;
    this.h = rect.height;
    this.canvas.width = Math.round(this.w * this.dpr);
    this.canvas.height = Math.round(this.h * this.dpr);
    // Долу остава място за надписа и субтитрите.
    this.R = Math.max(90, Math.min(this.w * 0.27, (this.h - 160) * 0.4));
    this.cx = this.w / 2;
    this.cy = Math.max(this.R * 1.05, (this.h - 170) / 2 + 22);  // горните балончета да не излизат
    this.coreSize = this.R * 0.86;
    reactor.resize(this.coreSize);
    const hit = $('reactor-btn').style;
    hit.width = hit.height = `${this.coreSize * 0.62}px`;
    hit.left = `${this.cx}px`;
    hit.top = `${this.cy}px`;
  },

  // --- 3D ----------------------------------------------------------------------------------
  project([x, y, z]) {
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const x1 = x * cy - z * sy;
    const z1 = x * sy + z * cy;
    const y2 = y * cp - z1 * sp;
    const z2 = y * sp + z1 * cp;
    const f = 3.4 / (3.4 + z2);
    return { x: this.cx + x1 * f * this.R, y: this.cy + y2 * f * this.R, s: f, z: z2 };
  },

  // По-далечното е по-бледо: z е от -1.7 (най-близо) до 1.7 (най-далеч).
  depthAlpha: (z) => Math.max(0.12, Math.min(1, 0.62 - z * 0.33)),

  // --- Кадър ----------------------------------------------------------------------------------
  frame(now) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    this.t += dt;
    reactor.frame(now, dt);
    this.build = Math.min(1, this.build + dt / 2.4);

    const motion = reduceMotion ? 0 : 1;
    if (!this.drag) {
      this.spin *= 1 - Math.min(1, dt * 2.5);
      const idle = this.hover ? 0 : 0.045 + reactor.spin * 0.02;
      this.yaw += (idle * motion + this.spin) * dt;
    }
    this.update(dt, motion);
    this.draw();
    requestAnimationFrame((n) => this.frame(n));
  },

  update(dt, motion) {
    const state = reactor.mode;
    const thinking = state === MODES.thinking;
    for (const node of this.nodes) {
      let target = this.tasks.some((task) => task.node === node && task.state === 'run') ? 1
        : this.t - node.lastDone < 1.4 ? 0.55 : 0;
      if (node.id === 'ear') target = state === MODES.listening || state === MODES.calibrating ? 1
        : state === MODES.standby ? 0.3 : 0;
      if (node.id === 'voice') target = voice.playing ? 0.45 + reactor.level * 0.55 : 0;
      if (node.id === 'reminders' && this.reminders.length) target = Math.max(target, 0.3);
      node.act += (target - node.act) * Math.min(1, dt * 6);
    }

    // Искри по мрежата: когато мисли — буря, иначе — тих фон.
    const rate = (thinking ? 34 : voice.playing ? 10 : 3) * (motion || 0.3);
    for (let n = rate * dt + Math.random() - 0.5; n > 0.5; n--) {
      this.signals.push({ link: this.links[(Math.random() * this.links.length) | 0], t: 0, v: 0.8 + Math.random() * 1.6 });
    }
    this.signals = this.signals.filter((s) => (s.t += dt * s.v) < 1);

    // Импулси ядро -> балонче, докато умението работи.
    for (const task of this.tasks) {
      if (task.state === 'run' && this.t - (task.lastPulse || 0) > 0.28) {
        task.lastPulse = this.t;
        this.pulses.push({ node: task.node, t: 0, dir: 1 });
      }
    }
    this.pulses = this.pulses.filter((p) => (p.t += dt * 1.6) < 1);
    this.tasks = this.tasks.filter((task) => task.state === 'run' || this.t - task.doneAt < 9);
  },

  draw() {
    const { ctx, dpr, build } = this;
    const [r, g, b] = reactor.color.map(Math.round);
    const rgba = (a) => `rgba(${r},${g},${b},${a})`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    const P = (p) => this.project(p);

    // 1. Невронният облак — линии в четири слоя по дълбочина (по-малко рисуване = по-бързо).
    const pts = this.neurons.map(P);
    const shown = Math.floor(this.links.length * build);
    ctx.lineWidth = 0.7;
    for (let layer = 0; layer < 4; layer++) {
      ctx.beginPath();
      for (let i = 0; i < shown; i++) {
        const [a, c] = this.links[i];
        const z = (pts[a].z + pts[c].z) / 2;
        if (Math.min(3, Math.floor((z + 1.8) / 0.9)) !== 3 - layer) continue;
        ctx.moveTo(pts[a].x, pts[a].y);
        ctx.lineTo(pts[c].x, pts[c].y);
      }
      ctx.strokeStyle = rgba(0.035 + layer * 0.03);
      ctx.stroke();
    }
    for (let i = 0; i < pts.length * build; i++) {
      const p = pts[i];
      ctx.fillStyle = rgba(this.depthAlpha(p.z) * 0.55);
      ctx.fillRect(p.x - 0.8 * p.s, p.y - 0.8 * p.s, 1.6 * p.s, 1.6 * p.s);
    }

    // 2. Искрите по мрежата.
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const s of this.signals) {
      const a = pts[s.link[0]], c = pts[s.link[1]];
      const x = a.x + (c.x - a.x) * s.t, y = a.y + (c.y - a.y) * s.t;
      const tail = Math.max(0, s.t - 0.25);
      ctx.strokeStyle = rgba(0.7 * Math.sin(s.t * Math.PI) * this.depthAlpha((a.z + c.z) / 2));
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(a.x + (c.x - a.x) * tail, a.y + (c.y - a.y) * tail);
      ctx.lineTo(x, y);
      ctx.stroke();
    }
    ctx.restore();

    // 3. Орбитите (задната половина — преди ядрото).
    this.drawRings(rgba, 'back');

    // 4. Връзките ядро -> балонче и импулсите по тях.
    const nodes = this.nodes.map((node) => ({ node, p: P(node.pos) }));
    this.proj = new Map(nodes.map(({ node, p }) => [node, p]));
    for (const { node, p } of nodes) {
      const grow = Math.max(0, Math.min(1, build * 2 - node.index / NODES.length));
      if (!grow) continue;
      const from = this.coreEdge(p, 0.34);
      ctx.strokeStyle = rgba((0.08 + node.act * 0.5) * this.depthAlpha(p.z) * grow);
      ctx.lineWidth = 0.8 + node.act * 0.8;
      ctx.setLineDash(node.act > 0.2 ? [] : [2, 5]);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(from.x + (p.x - from.x) * grow, from.y + (p.y - from.y) * grow);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const pulse of this.pulses) {
      if (pulse.t < 0) continue;                          // още чака реда си
      const p = this.proj.get(pulse.node);
      const from = this.coreEdge(p, 0.34);
      const k = pulse.dir > 0 ? pulse.t : 1 - pulse.t;
      const x = from.x + (p.x - from.x) * k, y = from.y + (p.y - from.y) * k;
      const glow = ctx.createRadialGradient(x, y, 0, x, y, 7);
      glow.addColorStop(0, `rgba(255,255,255,${0.9 * Math.sin(pulse.t * Math.PI)})`);
      glow.addColorStop(1, rgba(0));
      ctx.fillStyle = glow;
      ctx.fillRect(x - 7, y - 7, 14, 14);
    }
    ctx.restore();

    // 5. Балончетата отзад, ядрото, орбитите отпред, балончетата отпред.
    const sorted = [...nodes].sort((a, c) => c.p.z - a.p.z);
    for (const item of sorted) if (item.p.z > 0) this.drawNode(item, rgba);
    ctx.drawImage(reactor.canvas, this.cx - this.coreSize / 2, this.cy - this.coreSize / 2, this.coreSize, this.coreSize);
    this.drawRings(rgba, 'front');
    for (const item of sorted) if (item.p.z <= 0) this.drawNode(item, rgba);

    // 6. Надписите — винаги най-отгоре.
    this.drawReminders();
    this.drawTasks(rgba);
    this.drawThought(rgba);
    const hovered = this.pinned || this.hover;
    if (hovered) this.drawAbout(hovered, rgba);
  },

  // Точка по ръба на ядрото в посока към p — линиите не минават през реактора.
  coreEdge(p, k) {
    const dx = p.x - this.cx, dy = p.y - this.cy;
    const d = Math.hypot(dx, dy) || 1;
    const r = Math.min(this.coreSize * k, d);
    return { x: this.cx + (dx / d) * r, y: this.cy + (dy / d) * r };
  },

  drawRings(rgba, half) {
    const { ctx } = this;
    const rings = [
      { r: 0.52, tilt: [1.15, 0, 0.25], speed: 0.25, dash: 18 },
      { r: 0.66, tilt: [-0.35, 0, 0.55], speed: -0.14, dash: 5 },
      { r: 1.2, tilt: [0.06, 0, 0], speed: 0.05, dash: 0, ticks: true },
    ];
    for (const ring of rings) {
      const turn = this.t * ring.speed * (1 + reactor.spin * 2);
      const steps = 120;
      const pts = [];
      for (let i = 0; i <= steps; i++) {
        const a = (i / steps) * TAU * this.build + turn;
        let x = Math.cos(a) * ring.r, y = 0, z = Math.sin(a) * ring.r;
        const [ax, , az] = ring.tilt;                     // наклон около X, после около Z
        [y, z] = [y * Math.cos(ax) - z * Math.sin(ax), y * Math.sin(ax) + z * Math.cos(ax)];
        [x, y] = [x * Math.cos(az) - y * Math.sin(az), x * Math.sin(az) + y * Math.cos(az)];
        pts.push({ ...this.project([x, y, z]), i });
      }
      for (let i = 0; i < steps; i++) {
        const a = pts[i], c = pts[i + 1];
        const front = (a.z + c.z) / 2 <= 0;
        if ((half === 'front') !== front) continue;
        if (ring.dash && Math.floor(i / ring.dash) % 2) continue;
        ctx.strokeStyle = rgba((ring.ticks ? 0.16 : 0.34) * this.depthAlpha((a.z + c.z) / 2));
        ctx.lineWidth = ring.ticks ? 0.8 : 1.4;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(c.x, c.y);
        ctx.stroke();
        if (ring.ticks && i % 4 === 0) {                  // чертички по външната орбита
          const dx = a.x - this.cx, dy = a.y - this.cy, d = Math.hypot(dx, dy) || 1;
          const len = (i % 20 === 0 ? 7 : 3) * a.s;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(a.x + (dx / d) * len, a.y + (dy / d) * len);
          ctx.stroke();
        }
      }
    }
  },

  drawNode({ node, p }, rgba) {
    const { ctx } = this;
    const grow = Math.max(0, Math.min(1, this.build * 2 - node.index / NODES.length - 0.2));
    if (!grow) return;
    const listening = node.id === 'ear' && node.act > 0.05;
    const tone = listening ? (a) => `rgba(255,181,71,${a})` : rgba;
    const act = node.act;
    const alpha = this.depthAlpha(p.z) * grow;
    const radius = this.R * 0.085 * p.s * (0.6 + grow * 0.4) * (1 + act * 0.18);
    const hovered = node === this.hover || node === this.pinned;

    if (act > 0.02) {                                     // сияние около активното балонче
      const glow = ctx.createRadialGradient(p.x, p.y, radius * 0.5, p.x, p.y, radius * 2.8);
      glow.addColorStop(0, tone(0.32 * act));
      glow.addColorStop(1, tone(0));
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius * 2.8, 0, TAU);
      ctx.fill();
    }
    // Стъкленото тяло: ръбът е по-ярък от средата — затова изглежда като балонче.
    const body = ctx.createRadialGradient(p.x - radius * 0.3, p.y - radius * 0.35, radius * 0.1, p.x, p.y, radius);
    body.addColorStop(0, tone((0.06 + act * 0.3) * alpha));
    body.addColorStop(0.75, tone((0.05 + act * 0.12) * alpha));
    body.addColorStop(1, tone((0.26 + act * 0.45) * alpha));
    ctx.fillStyle = body;
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius, 0, TAU);
    ctx.fill();
    ctx.strokeStyle = tone((0.45 + act * 0.55 + (hovered ? 0.3 : 0)) * alpha);
    ctx.lineWidth = hovered ? 1.6 : 1;
    ctx.stroke();
    ctx.strokeStyle = `rgba(255,255,255,${0.45 * alpha})`;  // отблясък
    ctx.lineWidth = Math.max(1, radius * 0.08);
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius * 0.7, Math.PI * 1.08, Math.PI * 1.38);
    ctx.stroke();
    if (act > 0.3) {                                      // вълна от активното балонче
      const wave = (this.t * 1.4) % 1;
      ctx.strokeStyle = tone(0.5 * (1 - wave) * act);
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius * (1 + wave * 1.3), 0, TAU);
      ctx.stroke();
    }

    ctx.font = `600 ${Math.round(9.5 + p.s * 2.2)}px Jura, sans-serif`;
    ctx.letterSpacing = '2px';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = act > 0.3 || hovered ? `rgba(216,246,255,${alpha})` : tone(0.75 * alpha);
    ctx.fillText(node.label.toUpperCase(), p.x, p.y + radius + 5);
    ctx.letterSpacing = '0px';
  },

  // Балончета-задачи: изскачат до способността, докато тя работи, после показват резултата.
  drawTasks(rgba) {
    const { ctx } = this;
    const perNode = new Map();
    for (const task of this.tasks) {
      const p = this.proj.get(task.node);
      if (!p) continue;
      const slot = perNode.get(task.node) || 0;
      perNode.set(task.node, slot + 1);
      const age = this.t - task.born;
      const fade = task.state === 'run' ? 1 : Math.max(0, Math.min(1, (9 - (this.t - task.doneAt)) / 1.2));
      const pop = Math.min(1, age * 4);
      const side = p.x >= this.cx ? 1 : -1;
      const radius = this.R * 0.085 * p.s;
      ctx.font = '500 11.5px "JetBrains Mono", monospace';
      const textW = Math.max(ctx.measureText(task.text).width, task.result ? ctx.measureText(task.result).width : 0);
      let bx = p.x + side * (radius + 26 + slot * 10) * pop;
      // Балонче зад ядрото: задачата излиза встрани от реактора, за да не го закрива.
      const clear = this.coreSize * 0.45 + 12;
      if (Math.abs(p.y - this.cy) < this.coreSize * 0.5) bx = side > 0 ? Math.max(bx, this.cx + clear) : Math.min(bx, this.cx - clear);
      // Надписът не бива да излиза от сцената: ако не се побира, балончето се отмества навътре.
      const overflow = side > 0 ? bx + 20 + textW + 8 - this.w : 8 - (bx - 20 - textW);
      if (overflow > 0) bx -= side * overflow;
      const by = p.y - radius - 20 - slot * 34;
      const color = task.ok === false ? (a) => `rgba(255,90,78,${a})` : rgba;

      ctx.globalAlpha = fade;
      ctx.strokeStyle = color(0.5);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(p.x + side * radius * 0.7, p.y - radius * 0.7);
      ctx.lineTo(bx, by);
      ctx.lineTo(bx + side * 14, by);
      ctx.stroke();

      const r = 6 * pop;
      const bubble = ctx.createRadialGradient(bx - r * 0.3, by - r * 0.3, 0, bx, by, r);
      bubble.addColorStop(0, 'rgba(255,255,255,0.9)');
      bubble.addColorStop(0.5, color(task.state === 'run' ? 0.6 : 0.35));
      bubble.addColorStop(1, color(0.15));
      ctx.fillStyle = bubble;
      ctx.beginPath();
      ctx.arc(bx, by, r, 0, TAU);
      ctx.fill();
      if (task.state === 'run') {                         // въртящ се пръстен — „работи“
        ctx.strokeStyle = color(0.9);
        ctx.beginPath();
        ctx.arc(bx, by, r + 4, this.t * 5, this.t * 5 + 1.6);
        ctx.stroke();
      }

      ctx.textAlign = side > 0 ? 'left' : 'right';
      ctx.textBaseline = 'middle';
      const x = bx + side * 20;
      this.backdrop(side > 0 ? x - 4 : x - textW - 4, by - (task.result ? 15 : 9), textW + 8, task.result ? 31 : 18);
      ctx.fillStyle = `rgba(216,246,255,${0.95 * fade})`;
      ctx.fillText(task.text, x, by - (task.result ? 7 : 0));
      if (task.result) {
        ctx.fillStyle = task.ok === false ? 'rgba(255,179,172,0.9)' : color(0.8);
        ctx.fillText(task.result, x, by + 8);
      }
      ctx.globalAlpha = 1;
    }
  },

  // Напомнянията и таймерите чакат като кехлибарени балончета около „Напомняния“.
  drawReminders() {
    const node = this.nodes.find((n) => n.id === 'reminders');
    const p = this.proj.get(node);
    if (!p || !this.reminders.length) return;
    const { ctx } = this;
    const now = Date.now();
    this.reminders.slice(0, 4).forEach((item, i) => {
      const a = this.t * 0.5 + (i / Math.min(4, this.reminders.length)) * TAU;
      const orbit = this.R * 0.085 * p.s * 2.1;
      const x = p.x + Math.cos(a) * orbit, y = p.y + Math.sin(a) * orbit * 0.55;
      const left = Math.max(0, Math.round((item.due - now) / 1000));
      const label = item.kind === 'timer'
        ? `${String(Math.floor(left / 60)).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}`
        : clockTime(new Date(item.due));
      ctx.fillStyle = 'rgba(255,181,71,0.85)';
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, TAU);
      ctx.fill();
      ctx.font = '500 10px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(241,221,184,0.85)';
      ctx.fillText(label, x + 7, y);
    });
  },

  // Мисълта на модела — надпис с изнесена линия, като в холограмите от филма.
  drawThought(rgba) {
    const thought = this.thought;
    if (!thought) return;
    const age = this.t - thought.born;
    const fade = Math.max(0, Math.min(1, (14 - age) / 1.5));
    if (!fade) { this.thought = null; return; }
    const { ctx } = this;
    const anchor = { x: this.cx - this.coreSize * 0.33, y: this.cy - this.coreSize * 0.33 };
    const elbow = { x: anchor.x - 34, y: anchor.y - 34 };
    const width = Math.min(330, elbow.x - 20);
    if (width < 140) return;
    const end = { x: elbow.x - width, y: elbow.y };
    const drawn = Math.min(1, age * 3);

    ctx.globalAlpha = fade;
    ctx.strokeStyle = rgba(0.55);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(anchor.x, anchor.y);
    ctx.lineTo(elbow.x, elbow.y);
    ctx.lineTo(elbow.x + (end.x - elbow.x) * drawn, end.y);
    ctx.stroke();
    ctx.fillStyle = rgba(0.9);
    ctx.fillRect(end.x - 1, end.y - 3, 3, 6);

    ctx.font = '600 10px Jura, sans-serif';
    ctx.letterSpacing = '3px';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = rgba(0.8);
    ctx.fillText('МИСЪЛ', end.x, end.y + 16);
    ctx.letterSpacing = '0px';

    // Изписва се буква по буква над линията — отдолу нагоре.
    ctx.font = '400 12px "JetBrains Mono", monospace';
    const visible = thought.text.slice(0, Math.floor(age * 140));
    const lines = this.wrap(visible, width, 4);
    this.backdrop(end.x - 6, end.y - 8 - lines.length * 17, width + 8, lines.length * 17 + 4);
    ctx.fillStyle = `rgba(216,246,255,0.92)`;
    lines.forEach((line, i) => ctx.fillText(line, end.x, end.y - 8 - (lines.length - 1 - i) * 17));
    ctx.globalAlpha = 1;
  },

  // Какво може способността — при посочване с мишката.
  drawAbout(node, rgba) {
    const p = this.proj.get(node);
    if (!p) return;
    const { ctx } = this;
    const side = p.x >= this.cx ? 1 : -1;
    const radius = this.R * 0.085 * p.s;
    const width = 230;
    const start = { x: p.x + side * radius, y: p.y + radius * 0.4 };
    const elbow = { x: start.x + side * 22, y: start.y + 22 };
    const end = { x: elbow.x + side * width, y: elbow.y };
    ctx.strokeStyle = rgba(0.6);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(elbow.x, elbow.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
    const x = side > 0 ? elbow.x + 4 : end.x;
    this.backdrop(x - 4, elbow.y - 20, width, 72);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.font = '600 11px Jura, sans-serif';
    ctx.letterSpacing = '2px';
    ctx.fillStyle = 'rgba(216,246,255,0.95)';
    ctx.fillText(node.label.toUpperCase(), x, elbow.y - 6);
    ctx.letterSpacing = '0px';
    ctx.font = '400 12px "IBM Plex Sans", sans-serif';
    ctx.fillStyle = rgba(0.85);
    this.wrap(node.about, width - 8, 3).forEach((line, i) => ctx.fillText(line, x, elbow.y + 17 + i * 16));
  },

  // Лек тъмен фон зад надпис — за да се чете върху светещата мрежа.
  backdrop(x, y, w, h) {
    const { ctx } = this;
    ctx.save();
    ctx.globalAlpha *= 0.72;
    ctx.fillStyle = '#04090F';
    ctx.fillRect(x, y, w, h);
    ctx.restore();
  },

  wrap(text, width, maxLines) {
    const words = text.split(/\s+/);
    const lines = [];
    let line = '';
    for (const word of words) {
      const next = line ? `${line} ${word}` : word;
      if (this.ctx.measureText(next).width > width && line) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line) lines.push(line);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      lines[maxLines - 1] = `${lines[maxLines - 1].replace(/\s*\S*$/, '')}…`;
    }
    return lines;
  },

  // --- Мишка: въртене, посочване, клик върху ядрото = говорете ------------------------------------
  bindPointer() {
    const c = this.canvas;
    c.addEventListener('pointerdown', (e) => {
      this.drag = { x: e.clientX, y: e.clientY, yaw: this.yaw, pitch: this.pitch, moved: false, vx: 0, lx: e.clientX };
      c.setPointerCapture(e.pointerId);
    });
    c.addEventListener('pointermove', (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      if (this.drag) {
        const dx = e.clientX - this.drag.x, dy = e.clientY - this.drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) this.drag.moved = true;
        this.yaw = this.drag.yaw + dx * 0.007;
        this.pitch = Math.max(-0.6, Math.min(1.2, this.drag.pitch + dy * 0.005));
        this.drag.vx = (e.clientX - this.drag.lx) * 0.4;
        this.drag.lx = e.clientX;
        return;
      }
      this.hover = this.nodeAt(mx, my);
      const onCore = Math.hypot(mx - this.cx, my - this.cy) < this.coreSize * 0.32;
      c.style.cursor = this.hover || onCore ? 'pointer' : 'grab';
    });
    c.addEventListener('pointerup', (e) => {
      const drag = this.drag;
      this.drag = null;
      if (!drag) return;
      if (drag.moved) { this.spin = drag.vx; return; }
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      if (Math.hypot(mx - this.cx, my - this.cy) < this.coreSize * 0.32) { talk(); return; }
      const node = this.nodeAt(mx, my);
      this.pinned = node && node !== this.pinned ? node : null;  // клик закача описанието
    });
    c.addEventListener('pointerleave', () => { this.hover = null; });
  },

  nodeAt(x, y) {
    let best = null, bestD = Infinity;
    for (const [node, p] of this.proj) {
      const d = Math.hypot(x - p.x, y - p.y);
      if (d < this.R * 0.085 * p.s * 1.5 + 8 && d < bestD) { best = node; bestD = d; }
    }
    return best;
  },

  // --- Събития от Python (през hud) ----------------------------------------------------------------
  taskStart(name, args, module = '', label = '') {
    const byModule = this.nodes.find((n) => n.id === MODULE_NODES[module]);
    const node = this.toolNode.get(name) || byModule || this.nodes.find((n) => n.id === 'evolve');
    const text = (TASK_TEXT[name] || (() => label || name))(args || {});
    this.tasks = this.tasks.filter((t) => t.node !== node || t.state === 'run' || this.t - t.doneAt < 3);
    // Тест режимът пуска десетки проверки в минута — на екрана остават само последните три.
    if (name.startsWith('test:')) {
      const tests = this.tasks.filter((t) => t.name.startsWith('test:'));
      const drop = new Set(tests.slice(0, Math.max(0, tests.length - 2)));
      this.tasks = this.tasks.filter((t) => !drop.has(t));
    }
    this.tasks.push({ node, name, text: String(text).slice(0, 46), state: 'run', born: this.t, doneAt: 0 });
  },

  taskDone(name, result, ok) {
    const task = this.tasks.find((t) => t.name === name && t.state === 'run');
    if (!task) return;
    task.state = 'done';
    task.ok = ok;
    task.doneAt = this.t;
    task.result = String(result || '').replace(/\s+/g, ' ').slice(0, 52) + (String(result || '').length > 52 ? '…' : '');
    task.node.lastDone = this.t;
    for (let i = 0; i < 4; i++) this.pulses.push({ node: task.node, t: -i * 0.12, dir: -1 });  // обратно към ядрото
  },

  think(text) {
    this.thought = { text: String(text), born: this.t };
  },

  setReminders(items) {
    this.reminders = items.map((i) => ({ ...i, due: new Date(i.due).getTime() }));
  },
};

mind.init();
