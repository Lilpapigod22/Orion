"""
Модул за Мислене (AI ядро).

Свързва се с LLM чрез OpenAI-съвместимо API — работи и с OpenAI, и с локален Ollama.
Цикълът е:
    въпрос -> търсене в знанията -> LLM -> (извикване на умения -> LLM)* -> отговор
"""
import json
import re
from collections import Counter
from datetime import datetime
from typing import Callable

from openai import OpenAI

from . import clock, router
from .knowledge import KnowledgeBase
from .memory import ConversationMemory
from .tools import JarvisTools


# Вътрешна бележка, когато JARVIS се върти в кръг — кара го да спре и да помисли,
# вместо да повтаря едно и също.
REFLECTION = (
    "[Вътрешна бележка за Орион — не е от сър] Умението „{tool}“ не се справя или повтаряш "
    "същото извикване. Спри и помисли: подходящо ли е изобщо това умение за задачата? "
    "Ако липсва способност — създай ново умение с create_skill. Поправяй с improve_skill само "
    "ако умението има истински бъг в това, за което е предназначено. Не повтаряй същото извикване."
)

# Малките модели понякога „казват“, че са отворили програма или проверили пощата, без да
# извикат умение. Такъв отговор не стига до сър — моделът получава шанс да го направи наистина.
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
# „Проверявам пощата…“ без умение е измислица; след check_email е истина.
LOOKUP_CLAIM_RE = re.compile(
    r"(?<!да )\b(проверявам|проверих|търся|потърсих)\b|\b(?:ще|нека)\s+(?:проверя|потърся)\b", re.IGNORECASE)
CLAIM_RE = re.compile(f"{ACTION_CLAIM_RE.pattern}|{LOOKUP_CLAIM_RE.pattern}", re.IGNORECASE)
# Умения, които само четат. Всички останали (и новите, написани от JARVIS) се броят за действия.
READ_ONLY_TOOLS = {
    "get_current_time", "calculate", "get_weather", "days_until_date", "calendar_events", "check_email",
    "read_email", "tasks_list", "list_reminders", "search_web", "read_webpage", "list_lessons", "recent_errors",
    "system_status", "read_clipboard", "find_files", "look_at_screen", "look_at_image", "wikipedia",
    "convert_currency", "convert_units",
}
DEEP_RE = re.compile(
    r"защо|обясни|как да|как мога|сравни|разлик|план|анализ|реши |докажи|помогни ми|предложи|"
    r"какво мислиш|съвет|стратеги|плюсове|минуси|какво би", re.IGNORECASE)
HONEST_FAILURE = "Простете, сър, не успях да го изпълня. Кажете ми го, моля, още веднъж, малко по-конкретно."
FAKE_ACTION = (
    "[Вътрешна бележка за Орион — не е от сър] Написа, че изпълняваш действие, но не извика "
    "умение, така че нищо не се е случило. Извикай подходящото умение сега — или кажи честно, "
    "че не можеш да го направиш. Не е нужно да записваш поука за това."
)
# Молби, за които почти винаги трябва умение: (дума в молбата, кои умения, проста проверка,
# която JARVIS прави сам, ако моделът не я направи и след бележка). USER_TEXT = молбата на сър.
USER_TEXT = object()
INTENT_TOOLS = [
    # Думите са тесни нарочно: „пощенски код“ и „математическа задача“ не са за пощата и задачите.
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
    # „Кажи ми, когато биткойнът стигне…“ — известие, не справка (иначе подсказката води към цените).
    (re.compile(r"кажи ми,? когато|уведоми ме|известие за|известия за цени|\bстигне\b|надмине|падне под",
                re.IGNORECASE),
     "set_price_alert, list_price_alerts или cancel_price_alert", None),
    # „пазарите“, но не „пазарския списък“.
    (re.compile(r"акци|крипт|биткойн|анализ|\bпазар(ите|а|ът)?\b|цената на|курса на|курсът на|графика",
                re.IGNORECASE),
     "market_price, analyze_market, market_overview, crypto_market или analyze_price_file",
     ("market_overview", {})),
    (re.compile(r"брифинг|добро утро|какво ме чака", re.IGNORECASE), "daily_briefing", ("daily_briefing", {})),
    (re.compile(r"\bip\b|айпи", re.IGNORECASE), "my_public_ip или local_network_info", ("my_public_ip", {})),
    (re.compile(r"списък|списъка|бележк", re.IGNORECASE),
     "add_to_list, show_list, remove_from_list, save_note или list_notes", None),
    (re.compile(r"какво можеш|какво умееш|какви умения", re.IGNORECASE), "list_skills", ("list_skills", {})),
    # Факти за хора, места и събития — от Уикипедия, не по памет (малкият модел си измисля).
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
        tools: JarvisTools,
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
        # За модели с режим на мислене: "none" = отговаря веднага, "low"/"high" = мисли преди това.
        self.reasoning_effort = reasoning_effort
        # За сложни въпроси („защо“, „обясни“, „сравни“…) — по-задълбочено мислене.
        self.deep_reasoning_effort = deep_reasoning_effort or reasoning_effort
        # Вика се след всеки отговор с (въпрос, предишен отговор, използвани умения);
        # връща научена поука или None (виж jarvis/self_improve.py -> Reflector).
        self.after_turn = after_turn
        self.model = model
        self.persona = persona
        self.temperature = temperature
        self.max_tool_rounds = max_tool_rounds
        self.tools = tools
        self.knowledge = knowledge
        self.memory = memory
        # Допълнителни правила, които се четат наново при всеки въпрос (напр. научените поуки).
        self.extra_prompt = extra_prompt
        self._on_result: Callable[[str, str], None] | None = None  # задава се от think()
        # Думи за проба при подбора на умения (само тест режимът — виж jarvis/router.py).
        self.route_extra: dict[str, list[str]] | None = None

    def _system_prompt(self, user_text: str) -> str:
        prompt = self.persona
        extra = self.extra_prompt() if self.extra_prompt else ""
        if extra:
            prompt += f"\n\n{extra}"
        # Предишният въпрос също участва в търсенето, за да работят уточнения като
        # „А кой е в екипа?“ след въпрос за конкретен проект.
        context = self.knowledge.build_context(f"{self.memory.last_user_text()} {user_text}")
        if context:
            prompt += f"\n\n{context}"
        # Денят от седмицата се дава наготово — малките модели не могат да го изчислят от датата.
        now = datetime.now()
        return f"{prompt}\n\nСега е {clock.date_text(now)}, часът е {clock.time_text(now)}."

    def _effort_for(self, user_text: str) -> str | None:
        """Колко да мисли моделът: простите молби — бързо, сложните въпроси — задълбочено."""
        if self.reasoning_effort and (DEEP_RE.search(user_text) or len(user_text) > 140):
            return self.deep_reasoning_effort
        return self.reasoning_effort

    def _missed_tool(self, user_text: str, answer: str, used: set[str]) -> str | None:
        """Бележка към модела, ако е отговорил без умение там, където то е нужно (или None)."""
        # „media_control с action pause“ — написал е извикването като текст, вместо да го направи.
        if any(re.search(rf"\b{re.escape(name)}\b", answer) for name in self.tools.names()):
            return FAKE_ACTION
        # Въпросите не са твърдения: „Отварям ли го?“ пита сър, не казва, че е отворил.
        statements = re.sub(r"[^.!?\n]*\?", " ", answer)
        if not used:
            tools = [names for pattern, names, _ in INTENT_TOOLS if pattern.search(user_text)]
            if tools:
                return MISSED_TOOL.format(tools="; ".join(tools))
            return FAKE_ACTION if CLAIM_RE.search(statements) else None
        # Прочел е пощата, но „изпраща отговор“, без да е извикал reply_email — пак е измислица.
        acted = any(name not in READ_ONLY_TOOLS for name in used)
        return FAKE_ACTION if not acted and ACTION_CLAIM_RE.search(statements) else None

    @staticmethod
    def _default_call(user_text: str) -> tuple[str, str] | None:
        """(умение, аргументи) за проста проверка, която JARVIS прави сам, ако моделът не я направи."""
        for pattern, _, default in INTENT_TOOLS:
            if default and pattern.search(user_text):
                name, arguments = default
                arguments = {k: user_text if v is USER_TEXT else v for k, v in arguments.items()}
                return name, json.dumps(arguments, ensure_ascii=False)
        return None

    def _run_calls(self, calls, messages, steps, seen_calls, failures, on_tool, content: str = ""):
        """Изпълнява [(id, умение, аргументи)] и добавя извикването и резултатите в разговора.
        Връща [(умение, повторено ли е, брой грешки)]."""
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
            # В паметта — съкратено: целите писма и страници не са нужни за следващите въпроси.
            steps.append({"role": "tool", "tool_call_id": call_id, "content": result[:600]})
            repeated = (name, arguments) in seen_calls
            seen_calls.add((name, arguments))
            if result.startswith("Грешка"):
                failures[name] += 1
            report.append((name, repeated, failures[name]))
        return report

    def think(self, user_text: str, on_tool: Callable[[str, str], None] | None = None,
              on_result: Callable[[str, str], None] | None = None,
              on_thought: Callable[[str], None] | None = None) -> str:
        """Връща отговора на Орион. Наблюдатели (за 3D мрежата в прозореца):
        `on_tool(name, arguments)` — преди всяко умение, `on_result(name, result)` — след него,
        `on_thought(text)` — разсъжденията на модела, когато мисли."""
        self._on_result = on_result
        # Само уменията, които имат смисъл за тази молба — с по-малко избор моделът греши по-рядко.
        hidden = router.excluded_modules(user_text, self.memory.last_user_text(), self.route_extra)
        messages = [
            {"role": "system", "content": self._system_prompt(user_text)},
            *self.memory.as_messages(),
            {"role": "user", "content": user_text},
        ]
        answer = "Извинете, сър, изглежда се заплетох в собствените си схеми."
        failures: Counter[str] = Counter()
        seen_calls: set[tuple[str, str]] = set()
        steps: list[dict] = []  # извикванията на умения и резултатите им — отиват и в паметта
        reflected: str | bool = False
        reflection_sent = False
        caught_bluff = forced = False
        for round_index in range(self.max_tool_rounds + 1):
            # Наново при всеки кръг: умение, създадено току-що, трябва да е достъпно веднага.
            tool_schemas = self.tools.schemas(hidden)
            # В последния кръг умения не се предлагат — моделът трябва да отговори с това, което има.
            offer_tools = bool(tool_schemas) and round_index < self.max_tool_rounds
            # Мисли само докато решава какво да направи. След резултат от умение отговаря направо:
            # иначе qwen3.5 слага отговора си в „мисленето“ и оставя самия отговор празен.
            effort = (self._effort_for(user_text) if not seen_calls else self.reasoning_effort and "none")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                **({"tools": tool_schemas} if offer_tools else {}),
                **({"reasoning_effort": effort} if effort else {}),
            )
            message = response.choices[0].message
            reasoning = (message.model_extra or {}).get("reasoning")
            if reasoning and on_thought:
                on_thought(reasoning)

            # Моделът не иска умения -> това е крайният отговор.
            if not message.tool_calls or not offer_tools:
                # Моделите с режим на мислене понякога оставят разсъжденията си в текста.
                content = re.sub(r"<think>.*?</think>", "", message.content or "", flags=re.DOTALL)
                content = re.sub(r"</?think>", "", content).strip()  # и самотни етикети
                used = {name for name, _ in seen_calls}
                note = self._missed_tool(user_text, content, used) if offer_tools else None
                if note and not caught_bluff:
                    caught_bluff = True
                    print(f"[Проверка] Отговор без умение: {content}")
                    messages += [{"role": "assistant", "content": content}, {"role": "user", "content": note}]
                    continue
                if note and not used and not forced:
                    # И след бележката — без умение. Простите проверки (поща, задачи…) JARVIS прави сам.
                    forced = True
                    call = self._default_call(user_text)
                    if call:
                        print(f"[Проверка] Сам извиквам {call[0]}")
                        self._run_calls([("forced-1", *call)], messages, steps, seen_calls, failures, on_tool)
                        continue
                if note and CLAIM_RE.search(re.sub(r"[^.!?\n]*\?", " ", content)):
                    content = HONEST_FAILURE  # По-добре честно „не успях“, отколкото измислен резултат.
                answer = content or answer
                break

            # Моделът иска да изпълни едно или повече умения.
            calls = [(c.id, c.function.name, c.function.arguments) for c in message.tool_calls]
            for name, repeated, failed in self._run_calls(calls, messages, steps, seen_calls, failures,
                                                          on_tool, content=message.content or ""):
                if (repeated or failed >= 2) and not reflected:
                    reflected = name

            # След всички резултати от кръга (API-то изисква те да са непосредствено след извикването).
            if reflected and not reflection_sent:
                reflection_sent = True
                messages.append({"role": "user", "content": REFLECTION.format(tool=reflected)})

        previous_answer = self.memory.last_assistant_text()
        # Паметта пази и уменията, които е използвал: иначе в следващите въпроси моделът
        # „подражава“ на стари отговори без умения и започва да си измисля резултатите.
        self.memory.add_turn(user_text, answer, steps)

        # Рефлексия: ако сър е направил забележка, JARVIS извлича поука за следващите разговори.
        if self.after_turn:
            tools_used = [name for name, _ in seen_calls]
            lesson = self.after_turn(user_text, previous_answer, tools_used)
            if lesson and on_tool:
                on_tool("learn_lesson", json.dumps({"lesson": lesson}, ensure_ascii=False))
        return answer
