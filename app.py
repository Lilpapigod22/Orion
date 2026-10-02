"""
O.R.I.O.N. — the windowed application.

    python app.py                     # starts Orion
    python app.py --install-shortcut  # creates shortcuts on the Desktop and in the Start menu
    python app.py --mute              # no voice (e.g. for tests)
    python app.py --no-mic            # no microphone (for tests)

Architecture:
    ui/ (React, built)  <-- window.pywebview.api -->  HudApi  -->  Orion (this program)
                        --> window.hud.<fn>(...)  <--  Orion.hud()   ├─ Brain      (thinking)
                                                                    ├─ Listener   (listening)
                                                                    └─ NeuralVoice (speaking)
The window's source is in web/ (React + Vite); `cd web && npm install && npm run build` writes
the finished page to ui/, which is what opens here — Node is not needed to run Orion.
All requests go through one queue and are handled one at a time,
so Orion never speaks and listens at the same time.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class TimedLog:
    """A log file that puts the time in front of every line — so you can see when things happened."""

    def __init__(self, path: Path):
        path.parent.mkdir(exist_ok=True)
        # Above 1 MB a new log is started; the old one is kept as orion.old.log.
        if path.exists() and path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix(".old.log"))
        self._file = open(path, "a", encoding="utf-8", buffering=1)
        self._line_start = True

    def write(self, text: str) -> int:
        stamped = []
        for part in text.splitlines(keepends=True):
            if self._line_start:
                stamped.append(f"{datetime.now():%H:%M:%S} ")
            stamped.append(part)
            self._line_start = part.endswith("\n")
        self._file.write("".join(stamped))
        return len(text)

    def __getattr__(self, name):  # flush, encoding, isatty… — from the real file
        return getattr(self._file, name)


# When started from the icon (pythonw) there is no console -> messages go to logs/orion.log.
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = TimedLog(BASE_DIR / "logs" / "orion.log")
    print(f"===== Orion started · {datetime.now():%d.%m.%Y} =====")
else:
    sys.stdout.reconfigure(errors="replace")

# Lets the voice play without clicking in the window first.
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")

import argparse  # noqa: E402
import base64  # noqa: E402
import json  # noqa: E402
import queue  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import webbrowser  # noqa: E402

import openai  # noqa: E402
import webview  # noqa: E402

import config  # noqa: E402
from orion import alerts, apps, confirm, games, google, reels, reflexes, self_test, speech, vision  # noqa: E402
from orion.memory import tool_steps  # noqa: E402
from orion.reminders import book as reminder_book  # noqa: E402
from orion.self_improve import forge, lessons  # noqa: E402
from orion.tools import registry  # noqa: E402
from orion.voice import NeuralVoice  # noqa: E402
from main import build_brain  # noqa: E402

ICON = BASE_DIR / "assets" / "orion.ico"
MIC_BUSY = object()   # _hear: the microphone is busy with another listen
MIC_ERROR = object()  # _hear: the microphone is not working
SETTINGS_FILE = BASE_DIR / "user_settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def speakable(text: str, limit: int = 600) -> str:
    """Text from Claude to be read aloud: no markdown and no longer than `limit` (to the end of a sentence)."""
    text = re.sub(r"```.*?```", " (код — вижте журнала) ", text, flags=re.DOTALL)
    text = re.sub(r"[*#`_>|]+|^\s*[-•]\s+|^\s*\d+[.)]\s+", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)  # „Рила , а“ -> „Рила, а“ after removing **
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "…")


def describe_tool(name: str, arguments: str) -> str:
    """„get_weather · София“ — a short journal entry."""
    try:
        values = [str(v) for v in json.loads(arguments or "{}").values()]
    except ValueError:
        values = [arguments]
    return " · ".join([name, *values])


class Orion:
    """Connects thinking, listening and speaking with the window."""

    def __init__(self, muted: bool = False, use_mic: bool = True):
        settings = load_settings()
        self.window: webview.Window | None = None
        self.brain = None
        self.ollama = None
        self.ready = False
        self.boot_failed = False
        self.boot_problem = "Все още подготвям езиковия модел."
        self.muted = muted or settings.get("muted", False)
        self.always_listen = settings.get("always_listen", False)
        self._force_muted = muted
        self.use_mic = use_mic

        self.tasks: queue.Queue = queue.Queue()
        self._pending = 0                      # tasks in the queue + the current one
        self._pending_lock = threading.Lock()
        # Held while Orion answers — test mode runs its sandbox tests only without it,
        # so a test and a real request never run at the same time.
        self.work_lock = threading.Lock()
        self.last_activity = 0.0               # when sir last said something to Orion
        self.tester = self_test.SelfTester(self)
        self.speech_done = threading.Event()
        self.mic_lock = threading.Lock()
        self.listener = None
        self.followup_until = 0.0              # until when saying “Orion” is not needed
        self._followups_left = 0               # how many more replies are listened to automatically
        self._wake_thread: threading.Thread | None = None
        self._booted = False
        self.greeted = threading.Event()        # reminders are announced after the greeting
        self.mic_ok = False
        self._was_minimized = False
        self._approval_event: threading.Event | None = None
        self._approval_result = False
        self.start_maximized = False
        self._speech_gen = 0                   # changes at the start and end of every utterance
        self._mic_errors = 0
        self._last_wake_hint = 0.0             # when we last hinted “say Orion”
        self._wake_re = re.compile(
            r"\b(" + "|".join(map(re.escape, config.WAKE_WORDS)) + r")\b[\s,.!?]*", re.IGNORECASE
        )
        self.voice = NeuralVoice(config.NEURAL_VOICE, config.NEURAL_VOICE_RATE, config.NEURAL_VOICE_PITCH)
        self._fallback_speaker = None

    # --- Link to the interface --------------------------------------------------------
    def hud(self, fn: str, *args) -> None:
        """Calls the function `window.hud.<fn>(...)` in the window (web/src/bridge.js)."""
        if not self.window:
            return
        payload = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
        try:
            self.window.run_js(f"window.hud && hud.{fn}({payload})")
        except Exception as e:  # noqa: BLE001 — the window may be closing
            print(f"[UI] {fn}: {e}")

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def _set_idle_state(self) -> None:
        if self.busy:
            return
        if self.boot_failed:
            self.hud("setState", "offline")
        elif not self.ready:
            self.hud("setState", "boot")
        else:
            self.hud("setState", "standby" if self.always_listen and self.ready else "idle")

    # --- Start-up ---------------------------------------------------------------------
    def start(self) -> dict:
        """Called by the interface once it has loaded. Returns the initial settings."""
        if not self._booted:
            self._booted = True
            self.focus_page()
            threading.Thread(target=self._boot, daemon=True, name="boot").start()
            threading.Thread(target=self._worker, daemon=True, name="worker").start()
            threading.Thread(target=self._reminder_loop, daemon=True, name="reminders").start()
        return {"muted": self.muted, "alwaysListen": self.always_listen, "testMode": self.tester.running,
                "wakeWord": config.WAKE_WORDS[0], "maximized": self.start_maximized}

    def _boot(self) -> None:
        line = lambda *a: self.hud("bootLine", *a)  # noqa: E731
        line("core", "Personality core", "ok", "O.R.I.O.N.")

        if not registry.names():
            registry.load_skills(config.SKILLS_DIR)
        brain = build_brain()
        # The game and Store app lists are read up front — “пусни…” is instant.
        threading.Thread(target=lambda: (apps._start_apps(), games.installed()), daemon=True).start()
        line("skills", "Skills", "ok", str(len(registry.names())))
        docs = brain.knowledge.document_count
        line("knowledge", "Knowledge", "ok", f"{docs} {'document' if docs == 1 else 'documents'}")

        voice_name = re.sub(r".*-(\w+?)Neural$", r"\1", config.NEURAL_VOICE)
        line("voice", "Speech synthesis", "ok", voice_name)
        mic_status, mic_name = self._check_microphone() if self.use_mic else ("fail", "off")
        self.mic_ok = mic_status == "ok"
        line("mic", "Microphone", mic_status, mic_name)

        line("model", "Language model", "run", config.LLM_MODEL)
        try:
            brain.model = self._prepare_model(
                lambda msg, pct: line("model", "Language model", "run",
                                      msg + (f" · {pct:.0f}%" if pct is not None else ""))
            )
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.boot_problem = f"Ядрото не е достъпно: {e}"
            self.boot_failed = True
            line("model", "Language model", "fail", str(e))
            self.hud("bootDone", False)
            self.say(f"Внимание, сър. {self.boot_problem}")
            self.greeted.set()
            return

        # Self-improvement: code is written by the same model and approved in the window.
        forge.configure(brain.client, brain.model, config.LLM_REASONING_EFFORT)
        vision.configure(brain.client, brain.model)
        # “Look at the screen”: Orion's window hides for a moment so it does not cover what you are looking at.
        vision.hide_window = lambda: self.window and self.window.hide()
        vision.show_window = lambda: self.window and self.window.show()
        vision.minimize_window = lambda: self.window and self.window.minimize()
        forge.approve = self.request_approval
        forge.progress = lambda message: self.hud("addLog", "evolve", message)
        confirm.handler = self.request_confirmation  # emails, deleting — only with a button press from sir
        # YouTube reels are made in the background: progress in the journal, the end out loud.
        reels.notify = lambda text: (print(f"[Reels] {text}"), self.say(text))
        reels.progress = lambda text: (print(f"[Reels] {text}"), self.hud("addLog", "reels", text))
        reels.state = lambda info: self.hud("setReels", info)  # the indicator at the top: how far it has got
        if self.use_mic:  # Whisper — after the language model, to see how much room is left on the graphics card
            line("stt", "Speech recognition", "run", "loading Whisper")
            threading.Thread(target=self._load_speech, args=(line,), daemon=True, name="speech").start()
        line("lessons", "Lessons learned", "ok", str(len(lessons.all())))

        self.brain = brain
        self.ready = True
        line("model", "Language model", "ok", brain.model)
        self._refresh_telemetry()
        self.hud("bootDone", True)
        self._push_reminders()

        hour = datetime.now().hour
        greeting = "Добро утро" if 5 <= hour < 12 else "Добър ден" if hour < 18 else "Добър вечер"
        # The greeting ends with a question, so afterwards Orion listens to one reply without “Orion”.
        # Only one: otherwise a TV in the background would “chat” with it right from the start.
        if self.mic_ok:
            self._followups_left = 1
        self.say(f"{greeting}, сър. Всички системи работят. С какво мога да помогна?", "voice")
        self.greeted.set()
        if self.always_listen:
            self.set_always_listen(True)

    def _load_speech(self, line) -> None:
        speech.load()
        line("stt", "Speech recognition", "ok", speech.status)
        print(f"[Listening] Recognition: {speech.status}")

    def _refresh_telemetry(self) -> None:
        if self.brain:
            self.hud("setTelemetry", {
                "model": self.brain.model,
                "skills": len(registry.names()),
                "docs": self.brain.knowledge.document_count,
                "lessons": len(lessons.all()),
            })

    # --- Approval of code written by Orion --------------------------------------------------
    def request_approval(self, proposal) -> bool:
        """Shows the code in the window and waits for sir to press “Approve” or “Reject”.
        Called by the skill forge on the worker thread."""
        what = "написах ново умение" if proposal.kind == "create" else "подготвих поправка"
        return self._wait_for_decision("showApproval", {
            "kind": proposal.kind, "title": proposal.title, "reason": proposal.reason,
            "code": proposal.code, "diff": proposal.diff, "warnings": proposal.warnings,
            "tools": proposal.tools, "attempts": proposal.attempts,
        }, f"Сър, {what}. Моля, прегледайте кода и решете дали да го включа.", timeout=900)

    def request_confirmation(self, title: str, summary: str, body: str, accept: str) -> bool:
        """An email to send, an event to delete… — sir decides with a button (see orion/confirm.py)."""
        return self._wait_for_decision(
            "showConfirm", {"title": title, "summary": summary, "body": body, "accept": accept},
            f"Сър, моля, потвърдете: {title.lower()}. Натиснете „{accept}“, ако всичко е наред.", timeout=300)

    def _wait_for_decision(self, show: str, payload: dict, speech: str, timeout: float) -> bool:
        self._approval_event = threading.Event()
        self._approval_result = False
        self.hud(show, payload)
        self._speak(speech)
        self.hud("setState", "approval")
        decided = self._approval_event.wait(timeout=timeout)  # after that — rejected
        self.hud("hideApproval")
        self.hud("setState", "thinking")
        return decided and self._approval_result

    def resolve_approval(self, approved: bool) -> None:
        self._approval_result = bool(approved)
        if self._approval_event:
            self._approval_event.set()

    # --- Test mode (orion/self_test.py) ------------------------------------------------------
    def set_test_mode(self, enabled: bool) -> str:
        """Turns the self-check on/off. Returns what Orion should say."""
        if not enabled:
            was_running = self.tester.running
            self.tester.stop()
            self.hud("setSwitch", "test", False)
            return "Спрях самопроверката, сър." if was_running else "Тест режимът не е включен, сър."
        if not self.ready:
            self.hud("setSwitch", "test", False)
            return "Още подготвям езиковия модел, сър. Включете тест режима след малко."
        self.hud("setSwitch", "test", True)
        if not self.tester.start():
            return "Тест режимът вече работи, сър."
        return ("Включих тест режима, сър. Ще проверя уменията си в пясъчник и дали разбирам молбите, "
                "и ще поправя каквото намеря. Докато говорите с мен, тестовете чакат.")

    def test_idle(self) -> bool:
        """Tests only run while sir is not talking to Orion and nothing is waiting for an answer."""
        approval_open = self._approval_event is not None and not self._approval_event.is_set()
        now = time.time()
        return (self.ready and not self.busy and self.tasks.empty() and not approval_open
                and now - self.last_activity > self_test.IDLE_SECONDS and now > self.followup_until)

    def approve_test_fix(self, proposal) -> bool:
        """Code fixed by test mode — enabled only with “Approve and enable”."""
        approved = self.request_approval(proposal)
        self._set_idle_state()
        return approved

    def refresh(self) -> None:
        self._refresh_telemetry()

    def _prepare_model(self, progress) -> str:
        if config.LLM_PROVIDER != "ollama":
            return config.LLM_MODEL
        from orion.ollama_manager import OllamaManager
        self.ollama = OllamaManager(config.LLM_BASE_URL, config.LLM_MODEL,
                                    config.OLLAMA_CONTEXT, config.OLLAMA_KEEP_ALIVE)
        return self.ollama.ensure_ready(progress)

    @staticmethod
    def _check_microphone() -> tuple[str, str]:
        try:
            import pyaudio
            audio = pyaudio.PyAudio()
            try:
                name = audio.get_default_input_device_info()["name"]
            finally:
                audio.terminate()
            return "ok", re.sub(r"\s*\(.*", "", name)[:28] or "default"
        except Exception:  # noqa: BLE001
            return "fail", "no device"

    # --- Task queue -----------------------------------------------------------------
    def _submit(self, kind: str, text: str, source: str) -> None:
        with self._pending_lock:
            self._pending += 1
        self.tasks.put((kind, text, source))

    def ask(self, text: str, source: str = "text") -> None:
        text = (text or "").strip()
        if text:
            self._submit("ask", text, source)

    def say(self, text: str, source: str = "system") -> None:
        self._submit("say", text, source)

    def _worker(self) -> None:
        while True:
            kind, text, source = self.tasks.get()
            try:
                with self.work_lock:  # waits for a sandbox test already in progress (seconds)
                    if kind == "ask":
                        self._answer(text)
                    else:
                        self._speak(text)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.hud("addLog", "system", f"Error: {e}")
            finally:
                with self._pending_lock:
                    self._pending -= 1
            # First “standing by”, then any follow-up listening — otherwise “standing by”
            # might arrive after “listening” and the interface would show the wrong state.
            self._set_idle_state()
            if source == "voice":
                self._continue_conversation()

    def _answer(self, text: str) -> None:
        self.last_activity = time.time()
        self.hud("addLog", "user", text)
        print(f"[Sir] {text}")
        # Time, date, opening programs… — instant and error-free, even before the model is ready.
        reflex = reflexes.respond(text)
        if reflex:
            answer = self._run_reflex(text, reflex)
        elif not self.ready:
            answer = f"Моля за момент търпение, сър. {self.boot_problem}"
        else:
            answer = self._think(text)
        print(f"[Orion] {answer}")
        self._push_reminders()  # it may have added or removed a reminder
        self._speak(answer)
        if reflex and reflex.action == "close" and self.window:
            self.window.destroy()

    def _run_reflex(self, text: str, reflex: reflexes.Reflex) -> str:
        answer = reflex.answer
        steps = []
        self.hud("thought", "Known command — running it straight away, no thinking needed.")
        if reflex.tool:
            self.hud("setState", "thinking")
            self._log_tool(reflex.tool, reflex.arguments_json)
            result = registry.call(reflex.tool, reflex.arguments_json)
            print(f"[Skill] {reflex.tool}({reflex.arguments_json}) -> {result[:300]!r}")
            self._tool_done(reflex.tool, result)
            steps = tool_steps("reflex-1", reflex.tool, reflex.arguments_json, result)
            if result.startswith("Грешка"):
                answer = f"Не успях, сър: {result.split(': ', 2)[-1]}"
            elif reflex.tool == "get_weather":
                answer = reflexes.weather_answer(result)
            elif reflex.tool == "ask_claude" and result.startswith("Отговорът на Claude"):
                full = getattr(sys.modules.get("skills.claude_skills"), "last_answer", "") or result
                answer = "Claude казва: " + speakable(full) + " Целият отговор е в журнала и е копиран."
            else:
                answer = answer or result
        elif reflex.action == "google_setup":
            answer = self._google_setup()
        elif reflex.action == "google_connect":
            answer = self._google_connect(reflex.arguments["url"])
        elif reflex.action in ("test_on", "test_off"):
            answer = self.set_test_mode(reflex.action == "test_on")
        elif reflex.action == "test_report":
            answer = self.tester.summary()
        elif not reflex.action:  # time, date, day — lights up “Clock”
            self.hud("toolStart", "get_current_time", {})
            self.hud("toolDone", "get_current_time", answer, True)
        if self.brain:  # So follow-ups like „А утре?“ are understood after a reflex.
            self.brain.memory.add_turn(text, answer, steps)
        return answer

    # --- Google connection ------------------------------------------------------------------
    def _google_setup(self) -> str:
        """Copies the bridge code, opens Apps Script and shows the steps in the journal."""
        code_file = BASE_DIR / "logs" / "google_bridge_code.gs"
        code_file.write_text(google.bridge_code(), encoding="utf-8")
        copied = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Content -Raw -Encoding UTF8 -LiteralPath '{code_file}' | Set-Clipboard"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        ).returncode == 0
        code_file.unlink(missing_ok=True)  # Contains the secret key — do not leave it on disk.
        webbrowser.open("https://script.google.com/create")
        for step in google.SETUP_STEPS:
            self.hud("addLog", "guide", step)
        if not copied:
            self.hud("addLog", "guide", "Could not copy the code — say “свържи Google” again.")
        return ("Отворих Google Apps Script и копирах кода, сър. Следвайте стъпките в журнала "
                "и накрая поставете адреса тук.")

    def _google_connect(self, url: str) -> str:
        self.hud("setState", "thinking")
        try:
            info = google.connect(url)
        except google.GoogleError as e:
            return f"Не успях да се свържа, сър. {e}"
        return (f"Свързах се с Google акаунта {info.get('email') or ''}, сър. Вече мога да проверявам "
                f"пощата, календара и задачите Ви.")

    # --- Reminders -----------------------------------------------------------------------------
    def _reminder_loop(self) -> None:
        """Announces reminders when they are due. Missed ones (while Orion was
        closed) are announced right after start-up."""
        self.greeted.wait()
        last_alert_check = 0.0
        while True:
            # Test mode swaps the data files for a moment (sandbox) — reminders wait until then.
            with self_test.sandbox_lock:
                if time.time() - last_alert_check > 180:  # price alerts — every 3 minutes
                    last_alert_check = time.time()
                    try:
                        for message in alerts.triggered():
                            print(f"[Alert] {message}")
                            self.say(message)
                    except Exception as e:  # noqa: BLE001 — no connection: next time
                        print(f"[Alert] {e}")
                due = reminder_book.pop_due()
            for item in due:
                late = datetime.now() - datetime.fromisoformat(item["due"]) > timedelta(minutes=2)
                if item["kind"] == "timer":
                    message = f"Сър, таймерът за {item['text']} изтече."
                else:
                    text = item["text"]
                    message = (f"Сър, напомням Ви {text}." if text.startswith("да ")
                               else f"Сър, напомням Ви: {text}.")
                if late:
                    message = f"Докато бях изключен, пропуснахте напомняне за {item['due'][11:16]}. " + message
                print(f"[Reminder] {message}")
                self.say(message)
                with self_test.sandbox_lock:
                    self._push_reminders()
            time.sleep(5)

    def _think(self, text: str) -> str:
        self.hud("setState", "thinking")
        try:
            answer = self.brain.think(text, on_tool=self._log_tool, on_result=self._tool_done,
                                      on_thought=self._thought)
        except openai.APIConnectionError:
            answer = "Изгубих връзка с езиковия модел, сър. Уверете се, че Ollama работи."
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            answer = f"Възникна техническа неизправност, сър. {e}"
        self._refresh_telemetry()  # It may have learned a lesson or a new skill.
        if self.ollama:  # Keeps the model in video memory for longer.
            threading.Thread(target=self._touch_model, daemon=True).start()
        return answer or "Нямам какво да добавя, сър."

    def _log_tool(self, name: str, arguments: str) -> None:
        try:
            args = json.loads(arguments or "{}")
        except ValueError:
            args = {}
        if name == "learn_lesson":
            self.hud("addLog", "evolve", f"lesson learned · {args.get('lesson', arguments)}")
        else:
            self.hud("addLog", "tool", describe_tool(name, arguments))
        tool = registry._tools.get(name, {})
        description = tool.get("schema", {}).get("function", {}).get("description", name)
        label = re.split(r"[.:—(\n]", description)[0].strip()[:42]  # “Creates a strong random password”
        self.hud("toolStart", name, args if isinstance(args, dict) else {}, tool.get("module", ""), label)

    def _tool_done(self, name: str, result: str) -> None:
        """The skill's result — shown next to its bubble in the 3D network."""
        ok = not result.startswith("Грешка")
        hits = re.findall(r"^\d+\. (.+?) \(", result, flags=re.MULTILINE)
        if not ok:
            shown = result.split(": ", 2)[-1]
        elif name == "search_web" and hits:  # instead of the instruction to the model — what was found
            shown = f"{len(hits)} results · {hits[0]}"
        elif name == "ask_claude" and ok:
            shown = "answered"
        else:
            shown = result.splitlines()[0] if result.strip() else "done"
        self.hud("toolDone", name, shown[:200], ok)
        # The market analysis chart and Claude's full answer — in the journal.
        skills = sys.modules
        if ok and name in ("analyze_market", "analyze_price_file"):
            chart = getattr(skills.get("skills.market_skills"), "last_chart", None)
            if chart:
                self.hud("showChart", chart)
        if ok and name == "ask_claude":
            full = getattr(skills.get("skills.claude_skills"), "last_answer", None)
            if full:
                self.hud("addLog", "claude", full)

    def _thought(self, reasoning: str) -> None:
        """The model's reasoning (without markdown) — appears next to the core as “THOUGHT”."""
        text = re.sub(r"[*#`_>]+|^\s*[-•\d.)]+\s+", " ", reasoning, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            print(f"[Thought] {text[:300]}")
            self.hud("thought", text[:320])

    def _push_reminders(self) -> None:
        self.hud("setReminders", [{"text": i["text"], "due": i["due"], "kind": i["kind"]}
                                  for i in reminder_book.pending()])

    def _touch_model(self) -> None:
        try:
            self.ollama.touch()
        except Exception:  # noqa: BLE001
            pass

    # --- Speaking ----------------------------------------------------------------------
    def _speak(self, text: str) -> None:
        self.hud("say", text)
        if self.muted:
            return
        # Anything the microphone records while Orion speaks is its own voice — _hear discards it.
        self._speech_gen += 1
        try:
            self.hud("setState", "thinking")  # while the voice is being synthesised
            self.speech_done.clear()
            audio = self.voice.synthesize(text)
            if self.muted:  # Voice was switched off while it was being synthesised.
                return
            if audio:
                self.hud("playAudio", base64.b64encode(audio).decode("ascii"))
                # The interface reports when the audio ends or is interrupted.
                self.speech_done.wait(timeout=30 + len(text) * 0.12)
            else:
                self.hud("setState", "speaking")
                self._speak_offline(text)
        finally:
            self._speech_gen += 1

    def _speak_offline(self, text: str) -> None:
        """Fallback voice without internet (pyttsx3 / Windows SAPI)."""
        try:
            import comtypes
            comtypes.CoInitialize()
            if self._fallback_speaker is None:
                from orion.speaker import Speaker
                self._fallback_speaker = Speaker(config.TTS_VOICE_HINT, config.TTS_RATE)
            self._fallback_speaker.say(text)
        except Exception as e:  # noqa: BLE001
            print(f"[Voice] The fallback voice does not work either: {e}")

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)
        if not self._force_muted:
            save_settings({**load_settings(), "muted": self.muted})
        if self.muted:
            self.speech_done.set()

    # --- Listening ---------------------------------------------------------------------
    def _get_listener(self):
        if not self.use_mic:
            return None
        if self.listener is None:
            try:
                from orion.listener import Listener
                self.hud("setState", "calibrating")
                self.listener = Listener(config.LANGUAGE, config.LISTEN_TIMEOUT, config.PHRASE_TIME_LIMIT)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                # “Always listen” is not stopped at once: _wake_loop retries and gives up
                # only after several failures in a row (e.g. the USB microphone reconnecting).
                if self._mic_errors == 0:
                    self.hud("addLog", "system", f"No working microphone found — check that it is plugged in. ({e})")
                self._mic_errors += 1
                self._set_idle_state()
                return None
        return self.listener

    def _hear(self, state: str, timeout: float, wait: float = 0):
        """Records and recognises one phrase.

        Returns the text, None (nothing heard), MIC_BUSY (another listen holds the microphone)
        or MIC_ERROR. The microphone is released before the online recognition.
        """
        acquired = self.mic_lock.acquire(timeout=wait) if wait else self.mic_lock.acquire(blocking=False)
        if not acquired:
            return MIC_BUSY
        try:
            if self.busy:  # Orion is already answering — do not listen while it speaks.
                return None
            listener = self._get_listener()
            if listener is None:
                return MIC_ERROR
            self.hud("setState", state)
            speech_gen = self._speech_gen
            audio = listener.capture(timeout)
            self._mic_errors = 0
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            # The microphone is unplugged or busy — the next attempt searches again (for another one too).
            self.listener = None
            self._mic_errors += 1
            if self._mic_errors == 1:  # One message per run of failures, not a flood in the journal.
                self.hud("addLog", "system", f"The microphone stopped working ({e}). Trying to reconnect.")
            return MIC_ERROR
        finally:
            self.mic_lock.release()
            self._set_idle_state()

        # Whatever was recorded while Orion was speaking or starting to answer is its own voice.
        if audio is None or self._speech_gen != speech_gen or self.busy:
            return None
        text = listener.recognize(audio)
        if not text or self._speech_gen != speech_gen:
            return None
        self.hud("heard", text)
        return text

    def listen_once(self) -> None:
        """The microphone button (or F2)."""
        if self.busy:
            return
        self._followups_left = config.FOLLOWUP_TURNS
        # The next phrase is accepted without “Orion”, even if the “Always listen” loop catches it.
        self.followup_until = time.time() + config.LISTEN_TIMEOUT
        if self.always_listen and self._wake_thread and self._wake_thread.is_alive():
            self.hud("setState", "listening")
            return
        threading.Thread(target=self._listen_and_ask, daemon=True).start()

    def _listen_and_ask(self, timeout: float | None = None) -> None:
        # Waits for the microphone if a just-disabled “Always listen” is still finishing a recording.
        text = self._hear("listening", timeout or config.LISTEN_TIMEOUT, wait=config.PHRASE_TIME_LIMIT + 10)
        if isinstance(text, str):
            self.ask(text, "voice")

    def _continue_conversation(self) -> None:
        """After a spoken question Orion also listens to your next reply — like a real conversation.
        At most FOLLOWUP_TURNS times in a row, so it does not “chat” forever with background noise."""
        if self._followups_left <= 0:
            self.followup_until = 0.0  # The conversation is over — “Orion” is needed again.
            return
        self._followups_left -= 1
        self.followup_until = time.time() + config.FOLLOWUP_SECONDS
        if not self.always_listen and self.tasks.empty():
            threading.Thread(target=self._listen_and_ask, args=(6,), daemon=True).start()

    def set_always_listen(self, enabled: bool) -> None:
        self.always_listen = bool(enabled)
        save_settings({**load_settings(), "always_listen": self.always_listen})
        if self.always_listen and self.ready and not (self._wake_thread and self._wake_thread.is_alive()):
            self._wake_thread = threading.Thread(target=self._wake_loop, daemon=True, name="wake")
            self._wake_thread.start()
        self._set_idle_state()

    def _wake_loop(self) -> None:
        """“Always listen” mode: reacts to phrases that contain “Orion”."""
        errors = 0
        while self.always_listen:
            if self.busy:
                time.sleep(0.2)
                continue
            direct = time.time() < self.followup_until
            text = self._hear("listening" if direct else "standby", timeout=5)
            if text is MIC_BUSY:
                time.sleep(0.3)
                continue
            if text is MIC_ERROR:
                errors += 1
                if errors >= 8:  # ~30 seconds — enough for a USB microphone to reconnect
                    self.always_listen = False
                    self.hud("setSwitch", "wake", False)
                    self.hud("addLog", "system", "Turned off “Always listen”: the microphone is not responding.")
                    self._set_idle_state()
                    return
                time.sleep(min(5.0, 0.5 * 2 ** errors))
                continue
            errors = 0
            if not text:
                continue
            direct = direct or time.time() < self.followup_until
            has_wake_word = bool(self._wake_re.search(text))
            if not (direct or has_wake_word) or not (self.always_listen or direct):
                # The conversation is not addressed to Orion (or listening was switched off meanwhile).
                print(f"[Ignored — no “Orion”] {text}")
                if self.always_listen and time.time() - self._last_wake_hint > 90:
                    self._last_wake_hint = time.time()
                    self.hud("addLog", "guide", f"Heard “{text}” without “Orion”. Start with "
                                                 f"“Орион, …” or press F2 and speak.")
                continue
            if has_wake_word:
                self._followups_left = config.FOLLOWUP_TURNS
            command = self._wake_re.sub(" ", text).strip(" ,.!?") if has_wake_word else text
            if command:
                self.ask(command, "voice")
            else:
                self.hud("addLog", "user", text)
                self.say("Да, сър?", "voice")

    # --- Window ------------------------------------------------------------------------
    def on_minimized(self) -> None:
        self._was_minimized = True

    def on_restored(self) -> None:
        """Works around a frameless-window bug: after minimising, the embedded browser
        stays offset by ~32000 px (the coordinates of a minimised window) and the window
        looks black. WinForms “thinks” the position is right, so it is moved directly."""
        if not self._was_minimized:
            return
        self._was_minimized = False
        time.sleep(0.15)  # Waits for Windows to finish restoring.
        try:
            import ctypes
            from System import Action  # pythonnet — comes with pywebview
            form = self.window.native

            def relayout():
                size = form.ClientSize
                for control in form.Controls:
                    ctypes.windll.user32.SetWindowPos(
                        control.Handle.ToInt64(), None, 0, 0, size.Width, size.Height,
                        0x0004 | 0x0010,  # SWP_NOZORDER | SWP_NOACTIVATE
                    )
                    control.Focus()

            form.Invoke(Action(relayout))
        except Exception as e:  # noqa: BLE001
            print(f"[UI] Relayout after restore failed: {e}")

    def focus_page(self) -> None:
        """Gives keyboard focus to the page so you can type straight away."""
        try:
            from System import Action
            form = self.window.native
            form.Invoke(Action(lambda: [c.Focus() for c in form.Controls]))
        except Exception as e:  # noqa: BLE001
            print(f"[UI] Focus: {e}")

    def shutdown(self) -> None:
        self.always_listen = False
        self.tester.stop()
        self.resolve_approval(False)  # Closing during an approval = rejection.
        if self.ollama:
            # Frees video memory (e.g. for games) — on a separate thread so it does not block
            # closing; non-daemon so it finishes even after the window has gone.
            threading.Thread(target=self._unload_model, daemon=False).start()

    def _unload_model(self) -> None:
        try:
            self.ollama.touch(keep_alive="0", timeout=30)
        except Exception:  # noqa: BLE001
            pass


class HudApi:
    """The methods here are called from the window (web/src) via window.pywebview.api.<method>()."""

    def __init__(self, app: Orion):
        self._app = app  # With “_” so it is not exposed to JavaScript.

    def start(self):
        return self._app.start()

    def send_text(self, text: str):
        self._app.ask(text, "text")

    def listen(self):
        self._app.listen_once()

    def speech_finished(self):
        self._app.speech_done.set()

    def set_always_listen(self, enabled: bool):
        self._app.set_always_listen(enabled)

    def set_muted(self, muted: bool):
        self._app.set_muted(muted)

    def set_test_mode(self, enabled: bool):
        self._app.say(self._app.set_test_mode(enabled))

    def resolve_approval(self, approved: bool):
        self._app.resolve_approval(approved)

    def report_error(self, message: str):
        print(f"[UI error] {message}")

    def window_minimize(self):
        self._app.window.minimize()

    def window_maximize(self, maximize: bool):
        if maximize:
            self._app.window.maximize()
        else:
            self._app.window.restore()

    def window_close(self):
        self._app.window.destroy()

    def open_link(self, url: str):
        """A link clicked in the journal — opens in the default browser. Only web addresses."""
        if isinstance(url, str) and re.fullmatch(r"https?://[^\s\"'<>]+", url, re.IGNORECASE):
            webbrowser.open(url)


# --- Installing shortcuts ------------------------------------------------------------------
def install_shortcuts() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    env = {
        **os.environ,
        "J_TARGET": str(pythonw if pythonw.exists() else Path(sys.executable)),
        "J_APP": str(BASE_DIR / "app.py"),
        "J_DIR": str(BASE_DIR),
        "J_ICON": str(ICON),
        # Cyrillic names go through environment variables — PowerShell loses them in the command text.
        "J_NAME": "Orion.lnk",
        "J_OLD": "Митко.lnk",  # previous names — their shortcuts are removed
        "J_OLD2": "Орион.lnk",
    }
    script = r"""
$shell = New-Object -ComObject WScript.Shell
$folders = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($folder in $folders) {
    Remove-Item -LiteralPath (Join-Path $folder 'JARVIS.lnk') -ErrorAction SilentlyContinue  # old names
    Remove-Item -LiteralPath (Join-Path $folder $env:J_OLD2) -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $folder $env:J_OLD) -ErrorAction SilentlyContinue
    # WScript.Shell cannot save files with Cyrillic names — save with a Latin name, then rename.
    $tmp = Join-Path $folder 'Orion-shortcut.lnk'
    $link = $shell.CreateShortcut($tmp)
    $link.TargetPath = $env:J_TARGET
    $link.Arguments = '"' + $env:J_APP + '"'
    $link.WorkingDirectory = $env:J_DIR
    $link.IconLocation = $env:J_ICON
    $link.Description = 'O.R.I.O.N. - personal AI assistant'
    $link.Save()
    $final = Join-Path $folder $env:J_NAME
    Move-Item -Force -LiteralPath $tmp -Destination $final
    Write-Output $final
}
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            env=env, capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip())


def window_size() -> tuple[int, int, bool]:
    """1180×760, but no larger than the free part of the screen (without the taskbar).
    If the screen is too small, the window opens full screen."""
    try:
        import ctypes
        import ctypes.wintypes
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        free_w, free_h = rect.right - rect.left, rect.bottom - rect.top
    except Exception:  # noqa: BLE001
        return 1180, 760, False
    width, height = min(1180, free_w - 40), min(760, free_h - 40)
    if width < 880 or height < 600:
        return 1180, 760, True
    return width, height, False


def already_running() -> bool:
    """Allows only one Orion (otherwise two windows would fight over the microphone)."""
    if os.name != "nt":
        return False
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "Orion.SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    parser = argparse.ArgumentParser(description="O.R.I.O.N.")
    parser.add_argument("--install-shortcut", action="store_true", help="create shortcuts on the Desktop and in Start")
    parser.add_argument("--mute", action="store_true", help="no voice")
    parser.add_argument("--no-mic", action="store_true", help="no microphone")
    parser.add_argument("--debug", action="store_true", help="developer tools in the window")
    args = parser.parse_args()

    if args.install_shortcut:
        install_shortcuts()
        return

    if already_running():
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "Orion is already running, sir.", "O.R.I.O.N.", 0x40)
        return

    if os.name == "nt":  # Its own taskbar icon (instead of Python's).
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Orion.Assistant")

    app = Orion(muted=args.mute, use_mic=not args.no_mic)
    width, height, app.start_maximized = window_size()
    app.window = webview.create_window(
        "O.R.I.O.N.",
        str(BASE_DIR / "ui" / "index.html"),
        js_api=HudApi(app),
        width=width, height=height, min_size=(880, 600), maximized=app.start_maximized,
        frameless=True, easy_drag=False,
        background_color="#04090F",
    )
    app.window.events.closing += app.shutdown
    app.window.events.minimized += app.on_minimized
    app.window.events.restored += app.on_restored
    app.window.events.maximized += app.on_restored
    webview.start(debug=args.debug, icon=str(ICON))


if __name__ == "__main__":
    main()
