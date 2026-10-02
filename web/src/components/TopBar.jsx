import { useEffect, useRef, useState } from 'react';
import { toggleMaximize } from '../actions.js';
import { store, useStore } from '../store.js';
import { api, clockTime, STATUS_TEXT } from '../util.js';
import { Gauges } from './Gauges.jsx';
import { Jobs } from './Jobs.jsx';

const DRAG = 'pywebview-drag-region';

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  return <span className={`tele-clock ${DRAG}`}>{clockTime(now, true)}</span>;
}

export function TopBar() {
  const mode = useStore((s) => s.mode);
  const telemetry = useStore((s) => s.telemetry);
  const maximized = useStore((s) => s.maximized);
  const bar = useRef(null);

  // In full screen the top bar does not move the window. A native listener on the bar itself
  // runs before pywebview's, which listens on the whole document.
  useEffect(() => {
    const element = bar.current;
    const down = (e) => {
      if (store.get().maximized && !e.target.closest('.winctl')) e.stopPropagation();
    };
    element.addEventListener('mousedown', down);
    return () => element.removeEventListener('mousedown', down);
  }, []);

  return (
    <header className="topbar" ref={bar} onDoubleClick={(e) => { if (!e.target.closest('.winctl')) toggleMaximize(); }}>
      <div className={`brand ${DRAG}`}>O.R.I.O.N.</div>
      <div className={`drag-fill ${DRAG}`} />
      <div className={`telemetry ${DRAG}`} aria-label="System status">
        <span className={`status ${DRAG}`}><i className="dot" /><span>{STATUS_TEXT[mode]}</span></span>
        <Jobs />
        <span className={`tele-model ${DRAG}`}>{telemetry}</span>
        <Gauges />
        <Clock />
      </div>
      <div className="winctl">
        <button type="button" aria-label="Minimize" title="Minimize" onClick={() => api()?.window_minimize()}>
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5h8" /></svg>
        </button>
        <button type="button" aria-label={maximized ? 'Normal size' : 'Full screen'} title="Full screen" onClick={toggleMaximize}>
          <svg viewBox="0 0 12 12" aria-hidden="true"><rect x="2.5" y="2.5" width="7" height="7" /></svg>
        </button>
        <button type="button" className="btn-close" aria-label="Close Orion" title="Close" onClick={() => api()?.window_close()}>
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 2.5l7 7M9.5 2.5l-7 7" /></svg>
        </button>
      </div>
    </header>
  );
}
