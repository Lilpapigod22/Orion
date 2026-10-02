import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CHART, drawChart, fmtPrice } from '../engine/chart.js';
import { useStore } from '../store.js';
import { api, clockTime, reduceMotion, WHO } from '../util.js';

const SESSION_START = clockTime();

// Web addresses in the journal can be clicked — they open in the browser (Python checks the address).
const URL_RE = /(https?:\/\/[^\s"'<>„“]+[^\s"'<>„“.,;:!?)\]])/g;
function linkify(text, keyPrefix = '') {
  return text.split(URL_RE).map((part, i) => (i % 2
    ? (
      <a key={`${keyPrefix}${i}`} href={part} title="Open in the browser"
         onClick={(e) => { e.preventDefault(); api()?.open_link(part); }}>{part}</a>
    )
    : part));
}

// Claude's answers come with markdown: **bold**, `code`, # headings. They are shown as text
// with bold parts — React escapes everything, so nothing in the answer is executed.
function markdownLite(text) {
  const clean = text.replace(/^#{1,6}\s+/gm, '').replace(/^\s*[-*]\s+/gm, '• ');
  return clean.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>;
    return linkify(part, `${i}-`);
  });
}

const FRAMES = { '1h': 'hourly', '4h': '4-hour', '1d': 'daily', '1wk': 'weekly' };

// The market analysis chart with a legend and values on hover.
function Chart({ data }) {
  const canvas = useRef(null);
  const tip = useRef(null);
  const geometry = useRef(null);
  const hoverRef = useRef(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const element = canvas.current;
    const draw = () => { geometry.current = drawChart(element, data, hoverRef.current); };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(element);
    return () => observer.disconnect();
  }, [data]);

  useLayoutEffect(() => {
    hoverRef.current = hover;
    geometry.current = drawChart(canvas.current, data, hover);
    if (hover == null || !tip.current) return;
    const width = canvas.current.getBoundingClientRect().width;
    tip.current.style.left = `${Math.min(geometry.current.x(hover) + 12, width - tip.current.offsetWidth - 4)}px`;
  }, [hover, data]);

  const move = (e) => {
    const g = geometry.current;
    const rect = canvas.current.getBoundingClientRect();
    const frac = (e.clientX - rect.left - g.pad.l) / (g.w - g.pad.l - g.pad.r);
    setHover(Math.max(0, Math.min(g.n - 1, Math.round(frac * (g.n - 1)))));
  };

  const last = data.close.at(-1);
  const change = data.change >= 0 ? `+${data.change.toFixed(1)}%` : `${data.change.toFixed(1)}%`;
  const rows = hover == null ? [] : [
    [null, data.time[hover]], [CHART.price, `Price ${fmtPrice(data.close[hover])}`],
    [CHART.sma20, `SMA 20 ${fmtPrice(data.sma20[hover])}`], [CHART.sma50, `SMA 50 ${fmtPrice(data.sma50[hover])}`],
  ];
  return (
    <div className="chart">
      <span className="chart-title">{`${data.name} · ${fmtPrice(last)} ${data.currency || ''}`}</span>
      <span className="chart-meta">{`${FRAMES[data.timeframe] || data.timeframe} candles · ${change}`}</span>
      <span className="chart-legend">
        <span><i style={{ background: CHART.price }} />Price</span>
        <span><i style={{ background: CHART.sma20 }} />SMA 20</span>
        <span><i className="dashed" style={{ color: CHART.sma50 }} />SMA 50</span>
      </span>
      <span className="chart-box">
        <canvas
          ref={canvas} role="img" onPointerMove={move} onPointerLeave={() => setHover(null)}
          aria-label={`${data.name}: price ${fmtPrice(last)}, support ${fmtPrice(data.support)}, resistance ${fmtPrice(data.resistance)}`}
        />
        {hover != null && (
          <span className="chart-tip" ref={tip}>
            {rows.map(([color, text]) => (
              <span key={text}>{color && <i style={{ background: color }} />}{text}</span>
            ))}
          </span>
        )}
      </span>
    </div>
  );
}

function Entry({ entry }) {
  const { kind, time, text, chart } = entry;
  let body;
  if (kind === 'chart') body = <Chart data={chart} />;
  else body = <p>{kind === 'claude' ? markdownLite(text) : linkify(text)}</p>;
  return (
    <li className={`entry entry--${kind}`}>
      <time>{time}</time>
      <b>{WHO[kind] || kind}</b>
      {body}
    </li>
  );
}

export function Journal() {
  const log = useStore((s) => s.log);
  const list = useRef(null);
  useEffect(() => {
    // A chart is tall — it is shown at once; text slides in.
    const smooth = !reduceMotion && log.at(-1)?.kind !== 'chart';
    list.current?.lastElementChild?.scrollIntoView({ block: 'end', behavior: smooth ? 'smooth' : 'auto' });
  }, [log.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <aside className="journal" aria-label="Conversation journal">
      <div className="journal-head">
        <span>Journal</span>
        <span>session since {SESSION_START}</span>
      </div>
      <ol className="log" aria-live="polite" ref={list}>
        {log.length === 0
          ? <li className="log-empty">The conversation will appear here. Type a question below or press F2 and speak.</li>
          : log.map((entry) => <Entry key={entry.id} entry={entry} />)}
      </ol>
    </aside>
  );
}
