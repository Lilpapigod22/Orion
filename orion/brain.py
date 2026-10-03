"""
Thinking module (the AI core).

Talks to the LLM through an OpenAI-compatible API — works with both OpenAI and a local Ollama.
The loop is:
    question -> knowledge search -> LLM -> (skill calls -> LLM)* -> answer
"""
import json
import re
import time
from collections import Counter
from datetime import datetime
from typing import Callable

from openai import OpenAI

from . import clock, router, streaming
from .knowledge import KnowledgeBase
from .memory import ConversationMemory
from .tools import OrionTools


# An internal note for when Orion goes round in circles — makes it stop and think
# instead of repeating the same thing.
REFLECTION = (
    "[Вътрешна бележка за Орион — не е от сър] Умението „{tool}“ не се справя или повтаряш "
    "същото извикване. Спри и помисли: подходящо ли е изобщо това умение за задачата? "
    "Ако липсва способност — създай ново умение с create_skill. Поправяй с improve_skill само "
    "ако умението има истински бъг в това, за което е предназначено. Не повтаряй същото извикване."
)

# Small models sometimes “say” they opened a program or checked the mail without
# calling a skill. Such an answer never reaches sir — the model gets a chance to really do it.
ACTION_CLAIM_RE = re.compile(
    r"(?<!да )\b(отварям|отворих|отворен[аио]?|стартирам|стартирах|стартиран[аио]?|пускам|пуснах|"
    r"пуснат[аио]?|включвам|включих|включен[аио]?|затварям|затворих|запомн(?:их|ям|ен[аио]?)|"
    r"запис(?:ах|вам|ан[аио]?)|добавям|добавих|добавен[аио]?|поставям|поставих|изпращам|изпратих|"
    r"изпратен[аио]?|изпълнявам|изпълних|отговорих|намалих|намалявам|увеличих|усилих|заглуших|"
    r"заключих|заключвам|спрях|спирам|копирах|копирам|намалях|увеличах|усилях|насрочих|насрочен[аио]?|"
    r"поставен[аио]?|пуснат[аио]?|затворен[аио]?|заключен[аио]?)\b"
    r"|\b(?:ще|нека)\s+(?:Ви\s+)?(?:добавя|запиша|поставя|отворя|пусна|изпратя|напомня|сложа|отговоря)\b",
    re.IGNORECASE,
)
# „Проверявам пощата…“ (checking the mail) without a skill is made up; after check_email it is true.
LOOKUP_CLAIM_RE = re.compile(
    r"(?<!да )\b(проверявам|проверих|търся|потърсих)\b|\b(?:ще|нека)\s+(?:проверя|потърся)\b", re.IGNORECASE)
CLAIM_RE = re.compile(f"{ACTION_CLAIM_RE.pattern}|{LOOKUP_CLAIM_RE.pattern}", re.IGNORECASE)
# Read-only skills. All others (including new ones written by Orion) count as actions.
READ_ONLY_TOOLS = {
    "get_current_time", "calculate", "get_weather", "days_until_date", "calendar_events", "check_email",
    "read_email", "tasks_list", "list_reminders", "search_web", "read_webpage", "list_lessons", "recent_errors",
    "system_status", "read_clipboard", "find_files", "look_at_screen", "look_at_image", "wikipedia",
    "convert_currency", "convert_units",
    "crypto_forecast", "crypto_signals", "strategy_report", "forecast_record", "trading_positions", "trading_account",
    "demo_status", "simulate_history",
}
DEEP_RE = re.compile(
    r"\bзащо\b|обясни|как да\b|как мога|сравни|разлик|план|анализ|реши |докажи|помогни ми|предложи|"
    r"какво мислиш|съвет|стратеги|плюсове|минуси|какво би", re.IGNORECASE)
HONEST_FAILURE = "Простете, сър, не успях да го изпълня. Кажете ми го, моля, още веднъж, малко по-конкретно."
FAKE_ACTION = (
    "[Вътрешна бележка за Орион — не е от сър] Написа, че изпълняваш действие, но не извика "
    "умение, така че нищо не се е случило. Извикай подходящото умение сега — или кажи честно, "
    "че не можеш да го направиш. Не е нужно да записваш поука за това."
)
# Requests that almost always need a skill: (word in the request, which skills, a simple check
# Orion runs itself if the model still does not after a note). USER_TEXT = sir's request.
USER_TEXT = object()
INTENT_TOOLS = [
    # Forecasts and trades of BTC/ETH/SOL — before the general market and search entries below.
    (re.compile(r"(?:прогноз|сигнал|какво ще (?:прави|направи)|накъде|лонг|шорт)\w*.*?"
                r"(?:биткойн|биткоин|bitcoin|btc|етериум|етер|ethereum|eth|солан|solana)|"
                r"(?:биткойн|биткоин|bitcoin|btc|етериум|етер|ethereum|eth|солан|solana)\w*.*?"
                r"(?:прогноз|сигнал|какво ще прави|накъде|лонг|шорт)", re.IGNORECASE),
     "crypto_forecast, crypto_signals, open_trade или close_trade", ("crypto_forecast", {"coin": USER_TEXT})),
    # Demo accounts and the simulation — the model used to say it cannot manage any account.
    (re.compile(r"\bдемо(?:то|та)?\b|симулаци|симулир|тренировъчн\w*\s+сметк|виртуалн\w*\s+сметк|тренира\w*.*сметк", re.IGNORECASE),
     "create_demo_account, demo_status, simulate_history или set_demo_test", ("demo_status", {})),
    # The words are narrow on purpose: „пощенски код“ (postcode) and „математическа задача“ (maths problem) are not about mail and tasks.
    (re.compile(r"писм|\bпоща(?:та)?\b|имейл|\bмейл|gmail", re.IGNORECASE),
     "check_email, read_email, send_email или reply_email", ("check_email", {})),
    (re.compile(r"календар|\bсрещ[аи]\s+(?:ми\b|с)|събити|ангажимент", re.IGNORECASE),
     "calendar_events или calendar_add_event", ("calendar_events", {"day": "днес", "days": 7})),
    (re.compile(r"\bзадач(?:и|ите|ата)\b|(?:добави|запиши|нова)\s+задача|имам да правя|to-?do", re.IGNORECASE),
     "tasks_list, tasks_add или tasks_complete", ("tasks_list", {})),
    (re.compile(r"напомн|събуди ме", re.IGNORECASE),
     "set_reminder, list_reminders или cancel_reminder", None),
    (re.compile(r"таймер|засечи", re.IGNORECASE), "set_timer", None),
    (re.compile(r"новин|курс[ъа]?\b|цена|цени|резултат|потърси|провери в интернет|какво става", re.IGNORECASE),
     "search_web", ("search_web", {"query": USER_TEXT})),
    # „Кажи ми, когато биткойнът стигне…“ — an alert, not a look-up (otherwise the hint points to prices).
    (re.compile(r"кажи ми,? когато|уведоми ме|известие за|известия за цени|\bстигне\b|надмине|падне под",
                re.IGNORECASE),
     "set_price_alert, list_price_alerts или cancel_price_alert", None),
    # „пазарите“ (the markets), but not „пазарския списък“ (the shopping list).
    (re.compile(r"акци|крипт|биткойн|анализ|\bпазар(ите|а|ът)?\b|цената на|курса на|курсът на|графика",
                re.IGNORECASE),
     "market_price, analyze_market, market_overview, crypto_market или analyze_price_file",
     ("market_overview", {})),
    (re.compile(r"брифинг|добро утро|какво ме чака", re.IGNORECASE), "daily_briefing", ("daily_briefing", {})),
    (re.compile(r"\bip\b|айпи", re.IGNORECASE), "my_public_ip или local_network_info", ("my_public_ip", {})),
    (re.compile(r"списък|списъка|бележк", re.IGNORECASE),
     "add_to_list, show_list, remove_from_list, save_note или list_notes", None),
    (re.compile(r"какво можеш|какво умееш|какви умения", re.IGNORECASE), "list_skills", ("list_skills", {})),
    # Facts about people, places and events — from Wikipedia, not from memory (the small model makes things up).
    (re.compile(r"\bкой е\b|\bкоя е\b|\bкои са\b|\bкога (е|са)\b|къде се намира|разкажи ми за|"
                r"колко (жители|души|висок|голям)", re.IGNORECASE),
     "wikipedia или search_web", ("wikipedia", {"topic": USER_TEXT})),
    (re.compile(r"звук|пауза|следващ(ата|ия) (песен|клип)|предишн|изключи компютъра|рестартирай|"
                r"приспи|заключи компютъра|затвори (програмата|chrome|steam|\w+)", re.IGNORECASE),
     "set_volume, change_volume, mute_sound, media_control, close_program или power_action", None),
]
MISSED_TOOL = (
    "[Вътрешна бележка за Орион — не е от сър] Отговори, без да извикаш умение, а молбата на сър "
    "изглежда изисква {tools}. Ако е така — извикай умението сега и отговори с истинския му резултат. "
    "Ако молбата не е за това, отговори отново без умение. Никога не казвай, че си направил нещо, "
    "което не си."
)


class Brain:
    def __init__(
        self,
        tools: OrionTools,
        knowledge: KnowledgeBase,
        memory: ConversationMemory,
        *,
        base_url: str,
        api_key: str,
        model: str,
        persona: str,
        temperature: float = 0.4,
        max_tool_rounds: int = 5,
        extra_prompt: Callable[[], str] | None = None,
        after_turn: Callable[[str, str, list[str]], str | None] | None = None,
        reasoning_effort: str | None = None,
        deep_reasoning_effort: str | None = None,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        # For models with a thinking mode: "none" = answers at once, "low"/"high" = thinks first.
        self.reasoning_effort = reasoning_effort
        # For complex questions („защо“, „обясни“, „сравни“… — why, explain, compare) — deeper thinking.
        self.deep_reasoning_effort = deep_reasoning_effort or reasoning_effort
        # Called after every answer with (question, previous answer, skills used);
        # returns a learned lesson or None (see orion/self_improve.py -> Reflector).
        self.after_turn = after_turn
        self.model = model
        self.persona = persona
        self.temperature = temperature
        self.max_tool_rounds = max_tool_rounds
        self.tools = tools
        self.knowledge = knowledge
        self.memory = memory
        # Extra rules re-read on every question (e.g. the learned lessons).
        self.extra_prompt = extra_prompt
        self._on_result: Callable[[str, str], None] | None = None  # set by think()
        # Trial words for skill selection (test mode only — see orion/router.py).
        self.route_extra: dict[str, list[str]] | None = None
        # Model answers arrive piece by piece (live board). Test mode's client streams by itself -> False.
        self.stream = True

    def _system_prompt(self, user_text: str) -> str:
        prompt = self.persona
        extra = self.extra_prompt() if self.extra_prompt else ""
        if extra:
            prompt += f"\n\n{extra}"
        # The previous question also takes part in the search so that follow-ups like
        # „А кой е в екипа?“ (and who is on the team?) work after a question about a project.
        context = self.knowledge.build_context(f"{self.memory.last_user_text()} {user_text}")
        if context:
            prompt += f"\n\n{context}"
        # The day of the week is given ready-made — small models cannot work it out from the date.
        now = datetime.now()
        return f"{prompt}\n\nСега е {clock.date_text(now)}, часът е {clock.time_text(now)}."

    def _effort_for(self, user_text: str) -> str | None:
        """How much the model should think: simple requests — quickly, complex questions — in depth."""
        if self.reasoning_effort and (DEEP_RE.search(user_text) or len(user_text) > 140):
            return self.deep_reasoning_effort
        return self.reasoning_effort

    def _missed_tool(self, user_text: str, answer: str, used: set[str]) -> str | None:
        """A note to the model if it answered without a skill where one was needed (or None)."""
        # „media_control with action pause“ — it wrote the call as text instead of making it.
        if any(re.search(rf"\b{re.escape(name)}\b", answer) for name in self.tools.names()):
            return FAKE_ACTION
        # Questions are not claims: „Отварям ли го?“ (shall I open it?) asks sir, it does not say it opened it.
        statements = re.sub(r"[^.!?\n]*\?", " ", answer)
        if not used:
            tools = [names for pattern, names, _ in INTENT_TOOLS if pattern.search(user_text)]
            if tools:
                return MISSED_TOOL.format(tools="; ".join(tools))
            return FAKE_ACTION if CLAIM_RE.search(statements) else None
        # It read the mail but “sends a reply” without calling reply_email — still made up.
        acted = any(name not in READ_ONLY_TOOLS for name in used)
        return FAKE_ACTION if not acted and ACTION_CLAIM_RE.search(statements) else None

    @staticmethod
    def _default_call(user_text: str) -> tuple[str, str] | None:
        """(skill, arguments) for a simple check Orion runs itself if the model does not."""
        for pattern, _, default in INTENT_TOOLS:
            if default and pattern.search(user_text):
                name, arguments = default
                arguments = {k: user_text if v is USER_TEXT else v for k, v in arguments.items()}
                return name, json.dumps(arguments, ensure_ascii=False)
        return None

    def _complete(self, on_delta: Callable[[str, str], None] | None, **kwargs):
        if self.stream:
            return streaming.create_streamed(self.client, on_delta=on_delta, **kwargs)
        return self.client.chat.completions.create(**kwargs)

    def _run_calls(self, calls, messages, steps, seen_calls, failures, on_tool, content: str = ""):
        """Runs [(id, skill, arguments)] and adds the call and the results to the conversation.
        Returns [(skill, whether repeated, error count)]."""
        request = {"role": "assistant", "content": content, "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
            for call_id, name, arguments in calls]}
        messages.append(request)
        steps.append(request)
        report = []
        for call_id, name, arguments in calls:
            if on_tool:
                on_tool(name, arguments)
            result = self.tools.call(name, arguments)
            print(f"[Умение] {name}({arguments}) -> {result[:300]!r}")
            if self._on_result:
                self._on_result(name, result)
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            # Shortened in memory: whole emails and pages are not needed for later questions.
            steps.append({"role": "tool", "tool_call_id": call_id, "content": result[:600]})
            repeated = (name, arguments) in seen_calls
            seen_calls.add((name, arguments))
            if result.startswith("Грешка"):
                failures[name] += 1
            report.append((name, repeated, failures[name]))
        return report

    def think(self, user_text: str, on_tool: Callable[[str, str], None] | None = None,
              on_result: Callable[[str, str], None] | None = None,
              on_thought: Callable[[str], None] | None = None,
              on_delta: Callable[[str, str], None] | None = None,
              on_step: Callable[[str, dict], None] | None = None) -> str:
        """Returns Orion's answer. Observers (for the window): `on_tool(name, arguments)` — before each
        skill, `on_result(name, result)` — after it, `on_thought(text)` — the model's whole reasoning,
        `on_delta(kind, text)` — each streamed piece („reasoning“/„content“), `on_step(kind, info)` —
        „route“ (which skill groups the model sees), „model_start“/„model_end“ for each model round."""
        self._on_result = on_result
        # Only the skills that make sense for this request — with fewer choices the model errs less.
        hidden = router.excluded_modules(user_text, self.memory.last_user_text(), self.route_extra)
        def step(kind: str, info: dict) -> None:
            if on_step:
                try:
                    on_step(kind, info)
                except Exception as e:  # noqa: BLE001 — an observer must never break the answer
                    print(f"[Brain] on_step: {e}")

        step("route", {"hidden": sorted(hidden), "shown": sorted(m for m in router.GROUPS if m not in hidden)})
        messages = [
            {"role": "system", "content": self._system_prompt(user_text)},
            *self.memory.as_messages(),
            {"role": "user", "content": user_text},
        ]
        answer = "Извинете, сър, изглежда се заплетох в собствените си схеми."
        failures: Counter[str] = Counter()
        seen_calls: set[tuple[str, str]] = set()
        steps: list[dict] = []  # skill calls and their results — they also go into memory
        reflected: str | bool = False
        reflection_sent = False
        caught_bluff = forced = False
        for round_index in range(self.max_tool_rounds + 1):
            # Again on every round: a skill created just now must be available at once.
            tool_schemas = self.tools.schemas(hidden)
            # No skills are offered in the last round — the model must answer with what it has.
            offer_tools = bool(tool_schemas) and round_index < self.max_tool_rounds
            # It only thinks while deciding what to do. After a skill result it answers directly:
            # otherwise qwen3.5 puts its answer into the “thinking” and leaves the answer itself empty.
            effort = (self._effort_for(user_text) if not seen_calls else self.reasoning_effort and "none")
            step("model_start", {"round": round_index, "effort": effort or "default"})
            pieces = [0]
            stamps: list[float] = []  # monotonic time of the first and of the last piece
            started = time.monotonic()

            def delta(kind: str, text: str) -> None:
                pieces[0] += 1
                now = time.monotonic()
                if not stamps:
                    stamps.append(now)
                    stamps.append(now)
                else:
                    stamps[1] = now
                if on_delta:
                    on_delta(kind, text)

            response = self._complete(
                delta,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                **({"tools": tool_schemas} if offer_tools else {}),
                **({"reasoning_effort": effort} if effort else {}),
            )
            seconds = time.monotonic() - started
            # Speed counts from the first piece — the wait for it is the prompt being read, not generation.
            tps = 0.0
            if pieces[0] > 1 and stamps[1] > stamps[0]:
                tps = round((pieces[0] - 1) / (stamps[1] - stamps[0]), 1)
            step("model_end", {"round": round_index, "seconds": round(seconds, 2), "tokens": pieces[0],
                               "tps": tps, "first_ms": round((stamps[0] - started) * 1000) if stamps else None})
            message = response.choices[0].message
            reasoning = (message.model_extra or {}).get("reasoning")
            if reasoning and on_thought:
                on_thought(reasoning)

            # The model wants no skills -> this is the final answer.
            if not message.tool_calls or not offer_tools:
                # Models with a thinking mode sometimes leave their reasoning in the text.
                content = re.sub(r"<think>.*?</think>", "", message.content or "", flags=re.DOTALL)
                content = re.sub(r"</?think>", "", content).strip()  # and stray tags
                used = {name for name, _ in seen_calls}
                note = self._missed_tool(user_text, content, used) if offer_tools else None
                if note and not caught_bluff:
                    caught_bluff = True
                    print(f"[Проверка] Отговор без умение: {content}")
                    messages += [{"role": "assistant", "content": content}, {"role": "user", "content": note}]
                    continue
                if note and not used and not forced:
                    # Still no skill after the note. Simple checks (mail, tasks…) Orion runs itself.
                    forced = True
                    call = self._default_call(user_text)
                    if call:
                        print(f"[Проверка] Сам извиквам {call[0]}")
                        self._run_calls([("forced-1", *call)], messages, steps, seen_calls, failures, on_tool)
                        continue
                if note and CLAIM_RE.search(re.sub(r"[^.!?\n]*\?", " ", content)):
                    content = HONEST_FAILURE  # Better an honest “I did not manage” than a made-up result.
                answer = content or answer
                break

            # The model wants to run one or more skills.
            calls = [(c.id, c.function.name, c.function.arguments) for c in message.tool_calls]
            for name, repeated, failed in self._run_calls(calls, messages, steps, seen_calls, failures,
                                                          on_tool, content=message.content or ""):
                if (repeated or failed >= 2) and not reflected:
                    reflected = name

            # After all the round's results (the API requires them right after the call).
            if reflected and not reflection_sent:
                reflection_sent = True
                messages.append({"role": "user", "content": REFLECTION.format(tool=reflected)})

        previous_answer = self.memory.last_assistant_text()
        # Memory also keeps the skills it used: otherwise in later questions the model
        # “imitates” old answers without skills and starts making up results.
        self.memory.add_turn(user_text, answer, steps)

        # Reflection: if sir made a remark, Orion extracts a lesson for future conversations.
        if self.after_turn:
            tools_used = [name for name, _ in seen_calls]
            lesson = self.after_turn(user_text, previous_answer, tools_used)
            if lesson and on_tool:
                on_tool("learn_lesson", json.dumps({"lesson": lesson}, ensure_ascii=False))
                if self._on_result:
                    self._on_result("learn_lesson", lesson)
        return answer
