import { AnimatePresence, MotionConfig, motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { formatMs, nowLine, phaseSummary } from '../engine/live.js';
import { useStore } from '../store.js';
import { StepDetails } from './StepDetails.jsx';

// heard → understood → thinking → skill → speaking, under the eyes. Click a step for its details.
export function Pipeline() {
  const traces = useStore((s) => s.live.traces);
  const [open, setOpen] = useState(null);
  const trace = traces.at(-1);
  const restore = useRef(null);
  // Escape closes the details; once they are gone, focus returns to the step that opened them.
  useEffect(() => {
    if (open || !restore.current) return;
    document.querySelector(`.pipe-step[data-phase="${restore.current}"]`)?.focus();
    restore.current = null;
  }, [open]);
  const close = () => {
    restore.current = open;
    setOpen(null);
  };
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      restore.current = open;
      setOpen(null);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);
  if (!trace) return null;
  const phases = phaseSummary(trace);
  const now = nowLine(trace);
  return (
    <MotionConfig reducedMotion="user">
    <div className="pipeline">
      <ol className="pipe-steps">
        {phases.map((p, i) => (
          <li key={p.phase}>
            {i > 0 && <span className="pipe-arrow" aria-hidden="true">→</span>}
            <motion.button type="button" data-phase={p.phase} className={`pipe-step is-${p.status}`}
                           aria-expanded={open === p.phase} onClick={() => (open === p.phase ? close() : setOpen(p.phase))}
                           animate={{ scale: p.status === 'run' ? 1.06 : 1 }}
                           transition={{ type: 'spring', stiffness: 420, damping: 24 }}>
              {p.phase}
              {p.ms != null && <small>{formatMs(p.ms)}</small>}
            </motion.button>
          </li>
        ))}
      </ol>
      <p className="pipe-now" aria-live="polite">{now}</p>
      <AnimatePresence>
        {open && <StepDetails key={open} phase={open} steps={phases.find((p) => p.phase === open).steps} onClose={close} />}
      </AnimatePresence>
    </div>
    </MotionConfig>
  );
}
