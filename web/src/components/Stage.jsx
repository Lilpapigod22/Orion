import { useEffect, useRef, useState } from 'react';
import { decide, talk } from '../actions.js';
import { Eyes } from './Eyes.jsx';
import { mind } from '../engine/mind.js';
import { Pipeline } from './Pipeline.jsx';
import { useStore } from '../store.js';
import { reduceMotion, STATE_LABELS } from '../util.js';

// The subtitle fades out, changes and fades back in.
function Subtitle() {
  const subtitle = useStore((s) => s.subtitle);
  const [shown, setShown] = useState(subtitle);
  const [fading, setFading] = useState(false);
  useEffect(() => {
    if (subtitle.n === shown.n) return undefined;
    setFading(true);
    const timer = setTimeout(() => { setShown(subtitle); setFading(false); }, reduceMotion ? 0 : 150);
    return () => clearTimeout(timer);
  }, [subtitle]); // eslint-disable-line react-hooks/exhaustive-deps
  const classes = ['subtitle', shown.user && 'is-user', fading && 'is-fading'].filter(Boolean).join(' ');
  return <p className={classes} aria-live="polite">{shown.text}</p>;
}

// System check at start-up — takes the place of the subtitles.
const MARK = { ok: 'OK', run: '···', fail: 'ERROR' };
function BootList() {
  const lines = useStore((s) => s.bootLines);
  return (
    <ol className="boot" aria-label="System check">
      {lines.map((line) => (
        <li key={line.id} className={`is-${line.status}`} title={line.detail}>
          <span className="label">{line.label}</span>
          <span className="detail">{line.detail}</span>
          <span className="mark">{MARK[line.status] || ''}</span>
        </li>
      ))}
    </ol>
  );
}

// A fix is shown as a difference: added, removed and position lines.
function diffLines(diff) {
  return diff.replace(/\n$/, '').split('\n').map((line, i) => {
    const kind = line.startsWith('+') && !line.startsWith('+++') ? 'line add'
      : line.startsWith('-') && !line.startsWith('---') ? 'line del'
      : line.startsWith('@@') ? 'line hunk' : 'line';
    return <span key={i} className={kind}>{line || ' '}</span>;
  });
}

// Code written by Orion (approve / reject) or an action that cannot be undone (send / reject).
function Approval() {
  const approval = useStore((s) => s.approval);
  const accept = useRef(null);
  const reject = useRef(null);
  const code = useRef(null);
  useEffect(() => {
    if (!approval) return;
    if (code.current) code.current.scrollTop = 0;
    // For an action to confirm, focus is on “Reject”: an accidental Enter sends nothing.
    (approval.confirm ? reject : accept).current?.focus();
  }, [approval]);
  if (!approval) return null;
  const { confirm, kind, title, reason, warnings, diff } = approval;
  return (
    <div className={`approval${confirm ? ' approval--confirm' : ''}`} role="dialog" aria-labelledby="approval-title">
      <p className="approval-kind">{kind}</p>
      <h2 className="approval-title" id="approval-title">{title}</h2>
      {!confirm && <p className="approval-reason">{reason}</p>}
      {!confirm && warnings.length > 0 && (
        <ul className="approval-warnings">{warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}</ul>
      )}
      {(!confirm || approval.code) && (
        <pre className="approval-code" tabIndex={0} ref={code}>{diff ? diffLines(diff) : approval.code}</pre>
      )}
      <div className="approval-actions">
        <button type="button" className="btn-reject" ref={reject} onClick={() => decide(false)}>Reject</button>
        <button type="button" className="btn-accept" ref={accept} onClick={() => decide(true)}>{approval.accept}</button>
      </div>
    </div>
  );
}

// The stage: the 3D network with the core, the state, the subtitles and the dialogs.
export function Stage() {
  const mode = useStore((s) => s.mode);
  const stage = useRef(null);
  const canvas = useRef(null);
  const [core, setCore] = useState(null);
  useEffect(() => {
    mind.attach(canvas.current, stage.current, setCore);
    return () => mind.detach();
  }, []);
  return (
    <section className="stage" aria-label="Orion" ref={stage}>
      <Eyes layout={core} />
      <canvas className="mind" ref={canvas} aria-hidden="true" />
      {/* Invisible button over the core — for the keyboard. The mouse clicks straight into the network. */}
      <button
        type="button" className="core-hit" aria-label="Talk to Orion (F2)" onClick={talk}
        style={core ? { width: core.core * 0.9, height: core.core * 0.9, left: core.x, top: core.y } : undefined}
      />
      <Pipeline />
      <p className="state-label">{STATE_LABELS[mode]}</p>
      <Subtitle />
      <BootList />
      <Approval />
    </section>
  );
}
