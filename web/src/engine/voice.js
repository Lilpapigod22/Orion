/* The voice — plays the MP3 from Python and gives its frequencies to the reactor. */
import { store } from '../store.js';
import { api } from '../util.js';

export const voice = {
  el: document.createElement('audio'),
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
      .then(() => store.set({ mode: 'speaking' }))
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

voice.el.preload = 'auto';
voice.el.addEventListener('ended', () => voice.finish());
voice.el.addEventListener('error', () => voice.finish());
