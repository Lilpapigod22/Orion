import { useEffect, useRef } from 'react';
import { registerInput, send, setSwitch, talk } from '../actions.js';
import { useStore } from '../store.js';

const SWITCHES = [
  { name: 'wake', label: 'Always listen', className: 'switch switch--wake',
    title: 'Orion listens all the time and answers when it hears its name' },
  { name: 'voice', label: 'Voice', className: 'switch', title: 'Answers are read out loud' },
  { name: 'test', label: 'Test mode', className: 'switch switch--test',
    title: 'Orion checks its own skills and whether it understands you, and fixes its mistakes. Tests pause while you talk to it.' },
];

export function Console() {
  const mode = useStore((s) => s.mode);
  const switches = useStore((s) => s.switches);
  const input = useRef(null);
  useEffect(() => {
    registerInput(input.current);
    input.current.focus();
  }, []);

  const submit = (e) => {
    e.preventDefault();
    const text = input.current.value.trim();
    if (!text) return;
    input.current.value = '';
    send(text);
  };

  return (
    <footer className="console">
      <button type="button" className="mic" aria-label="Speak (F2)" title="Speak (F2)"
              aria-pressed={mode === 'listening'} onClick={talk}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
        </svg>
      </button>
      <form className="command" autoComplete="off" onSubmit={submit}>
        <label className="sr-only" htmlFor="command-input">Message to Orion</label>
        <input id="command-input" ref={input} type="text" placeholder="Type to Orion or press F2 to speak" spellCheck={false} />
        <button type="submit">Send</button>
      </form>
      <div className="switches">
        {SWITCHES.map(({ name, label, className, title }) => (
          <label key={name} className={className} title={title}>
            <input type="checkbox" checked={switches[name]} onChange={(e) => setSwitch(name, e.target.checked)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </footer>
  );
}
