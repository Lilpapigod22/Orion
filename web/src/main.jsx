import { createRoot } from 'react-dom/client';
import './styles.css';
import './bridge.js';   // window.hud — before anything is drawn, so no call from Python is lost
import { App } from './App.jsx';

createRoot(document.getElementById('root')).render(<App />);
