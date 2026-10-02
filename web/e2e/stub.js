// pywebview stand-in: records calls, answers start()
window.calls = [];
window.pywebview = { api: new Proxy({}, { get: (_, name) => (...args) => {
  window.calls.push([name, ...args]);
  if (name === 'start') return Promise.resolve({ muted: false, alwaysListen: true, testMode: false, maximized: false });
  return Promise.resolve(null);
} }) };
