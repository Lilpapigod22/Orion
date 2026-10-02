import { useEffect } from 'react';
import { decide, refocus, talk } from './actions.js';
import { Console } from './components/Console.jsx';
import { Journal } from './components/Journal.jsx';
import { Stage } from './components/Stage.jsx';
import { TopBar } from './components/TopBar.jsx';
import { voice } from './engine/voice.js';
import { store, useStore } from './store.js';

// The O.R.I.O.N. window: top bar, the 3D network with the journal next to it, the console at the bottom.
export function App() {
  const mode = useStore((s) => s.mode);
  const booted = useStore((s) => s.booted);

  useEffect(() => {
    const keydown = (e) => {
      store.set({ lastActivity: Date.now() });
      if (e.key === 'F2') { e.preventDefault(); talk(); }
      if (e.key === 'Escape' && voice.playing) { e.preventDefault(); voice.stop(); }
      else if (e.key === 'Escape' && store.get().approval) { e.preventDefault(); decide(false); }
    };
    document.addEventListener('keydown', keydown);
    window.addEventListener('focus', refocus);
    return () => {
      document.removeEventListener('keydown', keydown);
      window.removeEventListener('focus', refocus);
    };
  }, []);

  return (
    <div className={`app${booted ? ' booted' : ''}`} data-state={mode}>
      <TopBar />
      <main className="deck">
        <Stage />
        <Journal />
      </main>
      <Console />
    </div>
  );
}
