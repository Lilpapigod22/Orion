# Orion — 3D eyes and live board (sub-project 1)

Date: 2026-10-02 · Status: approved in conversation, awaiting review of this document

## Goal

Sir wants to *see what Orion is doing at every moment* and wants Orion to look alive. The reactor in the
centre of the window becomes a pair of glowing 3D eyes with expressions that follow Orion's real state,
and a live board shows each step of every request with its timing, plus gauges and background jobs.

This is sub-project 1 of a larger request. Later sub-projects (separate specs): 2 — voice recognition of
sir and a conversation mode (no need to say „Орион“); 3 — device control (more ready-made settings, any
setting through an approved command, mouse/screen control); 4 — several AI models, automated test
suite, more interactivity.

## Decisions (sir's choices)

| Question | Choice |
|---|---|
| Face style | B — robot eyes (two large glowing rounded eyes, voice as a bar wave below) |
| Layout | B — big eyes in the centre, step pipeline directly under them, journal on the right, gauges in the top bar |
| Technology | 3D with effects (WebGL): three.js through React Three Fiber, bloom post-processing |

Measured with the prototype on the RTX 3080: GPU utilisation +6–7 points, +80 MB video memory at 30 fps.

## What sir sees

### Eyes (replace the reactor)

The eyes sit in the centre of the existing 2D skill network (`web/src/engine/mind.js` keeps drawing the
network and the skill bubbles; the reactor drawing is removed). Expressions map to Orion's real state:

| State (source) | Eyes |
|---|---|
| idle | look around slowly, blink every 2–5 s |
| standby / listening / calibrating | amber, 15 % larger, lean towards sir |
| thinking | squint (55 % open), look up and to the side; the network spins faster |
| speaking | bars under the eyes follow the real voice (existing Web Audio analyser in `engine/voice.js`) |
| task finished successfully | happy arcs ^ ^ for ~1.5 s |
| skill error / offline | confused: reddish tint, one eye smaller, head tilt |
| test mode running | green tint |
| no activity for 10 min | sleepy (eyes half closed); wake on voice, mouse move or key |

Interaction: the eyes follow the mouse; clicking the eyes = talk (as the core does now); when a skill
starts, the gaze moves to its bubble for ~1 s (bubble screen positions come from `mind.proj`). Motion
uses springs (target → value with velocity), never instant jumps.

### Live board

- **Pipeline under the eyes:** `heard → understood → thinking → skill → speaking`. The current step is
  highlighted; finished steps show their duration. Under the pipeline: what Orion is thinking or saying
  right now (one line, typed out).
- **Step details (click a step):**
  - heard — Google's text, Whisper's text, which one was chosen;
  - understood — quick command (reflex) or model; which skill groups were shown to the model;
  - thinking — the model's reasoning streamed live, tokens per second;
  - skill — name, arguments, result, duration (several skills listed in order);
  - speaking — the spoken text and its duration.
- **Gauges in the top bar (every second):** model name, GPU %, video memory used/total, CPU %, RAM %,
  tokens per second of the last answer, total time of the last answer. A gauge whose source is missing is
  hidden.
- **Background jobs (always visible, small chips/list):** reels (stage), test mode (what it checks or
  fixes), skill proposals waiting for approval. Existing chips `setTest` / `setReels` become part of this.
- **Journal:** unchanged, plus a duration badge on skill entries.

All visible text in English (window rule); spoken answers stay Bulgarian.

## How it works

### Python

- **`orion/live.py` (new) — step recorder.** One request = one *trace* (`id`, start time). API:
  `live.begin(text, source)`, `live.step(phase, label, detail=None)` (closes the previous open step of
  the same phase or opens a new one), `live.end(ok)`. Every call forwards a compact event to the window
  through a sink set by the app (`live.sink = lambda event: app.hud("live", event)`). Event shape:
  `{"trace": int, "phase": "heard|understood|thinking|skill|speaking|done", "state": "start|update|end",
  "label": str, "detail": dict | None, "t": float (seconds since trace start), "ms": int | None}`.
  The recorder never raises: a failing sink is logged once and ignored.
- **Instrumentation points:** `app._hear` (heard, with both transcripts from `listener.last_heard`),
  `app._answer` (understood: reflex or model + `router.excluded_modules` result), `Brain.think`
  callbacks (thinking deltas, skill start/end with duration), `app._speak` (speaking start/end).
- **Streaming in the brain:** the stream aggregator now inside `self_test.StoppableClient._create` moves to
  `orion/streaming.py` as `create_streamed(client, on_delta=None, check=None, **kwargs)` and returns the
  same message shape (content, tool_calls, reasoning). `Brain` calls it with `on_delta` so reasoning and
  text reach the board while they are generated; tokens per second are measured from the deltas.
  `StoppableClient` reuses the same function (behaviour unchanged). Tokens per second = streamed pieces
  per second (Ollama sends about one token per piece). Test mode's brain keeps `stream = False` because
  its client already streams.
- **`orion/telemetry.py` (new):** a daemon thread, once per second while the window is visible (not
  minimised): GPU %, memory used/total from one `nvidia-smi --query-gpu=…` call (CREATE_NO_WINDOW,
  2 s timeout); CPU % and RAM % from `psutil`; sends `hud.setGauges({...})`. If `nvidia-smi` fails three
  times in a row, GPU fields are dropped and polling of it stops.

### Window (web/, React)

- New dependencies: `three`, `@react-three/fiber`, `@react-three/postprocessing`, `motion`; dev:
  `vitest`, `@testing-library/react`, `jsdom`. Build output stays one classic IIFE script (file://).
- **`components/Eyes3D.jsx`:** R3F `<Canvas frameloop="demand">` driven by our own 30 fps ticker;
  rounded-box eyes, arc eyes for „happy“, voice bars; `Bloom` (strength ~0.7, radius ~0.3); DPR ≤ 1.5;
  ticker stops when `document.hidden` or the window is minimised. Wrapped in an error boundary; on
  WebGL failure renders **`components/Eyes2D.jsx`** (canvas 2D version of the same eyes).
- **`engine/expression.js`:** pure function `(mode, events, now) → expression` (open, colour, look target,
  shape) — unit-testable without WebGL.
- **Store slices:** `live` (current trace with its steps, last 20 traces), `gauges`, `jobs`.
  `bridge.js` gains `hud.live(event)`, `hud.setGauges(g)`; `hud.toolDone` gets a 4th argument `ms`.
  Background jobs are derived from the existing `test`, `reels` and `approval` state (no new call).
- **Components:** `Pipeline.jsx`, `StepDetails.jsx` (popover), `Gauges.jsx` (top bar),
  `Jobs.jsx`. Motion handles the step highlight and popover transitions; reduced-motion is respected.
- `mind.js` stops drawing the reactor and exposes the bubble positions for the gaze; `reactor.js` is
  removed (its colour/state logic moves into `expression.js`).

## Errors and safety

- Nothing on the board can block or slow an answer: emitters are fire-and-forget, wrapped in try/except.
- 3D: 30 fps cap, paused when hidden, error boundary with 2D fallback.
- Telemetry only while visible; no new network access; `nvidia-smi` runs without a window.
- Existing safety rules are untouched (confirm buttons, code approval, sandbox in test mode).

## Testing

- **pytest (`tests/`, new):** `live` event order, durations and the sink-failure path; `telemetry`
  parsing of `nvidia-smi` output and the „missing GPU“ path; `streaming.create_streamed` with a fake
  stream returns exactly what the non-streamed call returned (content, tool calls, reasoning) and calls
  `on_delta` in order.
- **Vitest (`web/`):** `expression.js` for every state; `Pipeline` highlights and durations from a list
  of events; `StepDetails` content; `Gauges` hides missing values; bridge functions update the store.
- **Browser harness (existing `uitest/interact.html`, extended):** the 29 current checks plus live events,
  gauges and jobs; screenshots of each eye state.
- **Performance:** GPU % and video memory before/after with the real window (target: ≤ +10 points,
  ≤ +150 MB); answer time for the same question before/after must not grow by more than 5 %.
- **Real window:** typed and spoken questions, a skill, a reel job, test mode on/off; zero `[UI error]`.
- Regression: sandbox skill tests (119), quick-command checks, reels sync test.

## Acceptance criteria

1. The eyes replace the reactor and show every state in the table above in the real window.
2. For a typed question that uses a skill, the pipeline shows all five steps with durations, and each
   step's details open with a click.
3. Gauges update every second; reels and test-mode progress appear under background jobs.
4. All automated tests pass; GPU and answer-time targets are met; no regression in the existing suites.
