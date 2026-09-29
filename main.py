"""
Конзолен режим на JARVIS (за приложението с прозорец вижте app.py).

    python main.py            # гласов режим (микрофон + говор)
    python main.py --text     # пишете от клавиатурата, JARVIS говори
    python main.py --text --mute   # изцяло текстов режим (удобно за тестове)
"""
import argparse

import config
from jarvis import confirm, vision
from jarvis.brain import Brain
from jarvis.knowledge import KnowledgeBase
from jarvis.memory import ConversationMemory
from jarvis.speaker import Speaker
from jarvis.self_improve import forge, lessons, reflector
from jarvis.tools import registry


def prepare_model(progress=lambda message, percent: print(f"[Модел] {message}"
                                                        + (f" {percent:.0f}%" if percent is not None else ""))) -> str:
    """При Ollama: стартира, изтегля и настройва модела. Връща името му за заявките."""
    if config.LLM_PROVIDER != "ollama":
        return config.LLM_MODEL
    from jarvis.ollama_manager import OllamaManager
    manager = OllamaManager(config.LLM_BASE_URL, config.LLM_MODEL, config.OLLAMA_CONTEXT, config.OLLAMA_KEEP_ALIVE)
    return manager.ensure_ready(progress)


def build_brain(model: str | None = None) -> Brain:
    if not registry.names():
        registry.load_skills(config.SKILLS_DIR)
    print(f"[Умения] Налични: {', '.join(registry.names()) or 'няма'}")

    knowledge = KnowledgeBase(config.KNOWLEDGE_DIR, config.KNOWLEDGE_CHUNK_SIZE,
                              config.KNOWLEDGE_TOP_K, config.KNOWLEDGE_FULL_CONTEXT_CHARS)
    knowledge.reload_if_changed()

    brain = Brain(
        registry,
        knowledge,
        ConversationMemory(config.MEMORY_MAX_TURNS, config.MEMORY_FILE, config.MEMORY_KEEP_HOURS),
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        model=model or config.LLM_MODEL,
        persona=config.PERSONA,
        temperature=config.LLM_TEMPERATURE,
        max_tool_rounds=config.MAX_TOOL_ROUNDS,
        extra_prompt=lessons.as_prompt,
        after_turn=reflector.after_turn,
        reasoning_effort=config.LLM_REASONING_EFFORT,
        deep_reasoning_effort=config.LLM_DEEP_REASONING_EFFORT,
    )
    forge.configure(brain.client, brain.model, config.LLM_REASONING_EFFORT)
    vision.configure(brain.client, brain.model)
    return brain


def approve_in_console(proposal) -> bool:
    """Конзолен режим: показва кода и пита сър дали да го включи."""
    print(f"\n===== {proposal.title} =====\n{proposal.reason}")
    if proposal.warnings:
        print("Внимание: " + ", ".join(proposal.warnings))
    print(proposal.diff or proposal.code)
    return input("Одобрявате ли тази промяна? (д/н) ").strip().lower() in ("д", "да", "y", "yes")


def confirm_in_console(title: str, summary: str, body: str, accept: str) -> bool:
    """Конзолен режим: показва писмото/действието и пита сър."""
    print(f"\n===== {title} =====\n{summary}\n{body}")
    return input(f"{accept}? (д/н) ").strip().lower() in ("д", "да", "y", "yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS гласов асистент")
    parser.add_argument("--text", action="store_true", help="въвеждане от клавиатурата вместо микрофон")
    parser.add_argument("--mute", action="store_true", help="без озвучаване на отговорите")
    args = parser.parse_args()

    brain = build_brain(prepare_model())
    forge.approve = approve_in_console
    confirm.handler = confirm_in_console
    speaker = Speaker(config.TTS_VOICE_HINT, config.TTS_RATE, muted=args.mute)

    if args.text:
        def get_input() -> str | None:
            return input("\n[Вие] ").strip() or None
    else:
        from jarvis.listener import Listener  # Импорт тук: текстовият режим не изисква микрофон.
        listener = Listener(config.LANGUAGE, config.LISTEN_TIMEOUT, config.PHRASE_TIME_LIMIT)
        get_input = listener.listen

    print(f"[Система] Модел: {brain.model} ({config.LLM_PROVIDER})")
    speaker.say("На линия съм, сър. С какво мога да помогна?")

    while True:
        try:
            text = get_input()
        except (KeyboardInterrupt, EOFError):
            break
        if not text:
            continue

        lowered = text.lower()
        if config.WAKE_WORD and config.WAKE_WORD not in lowered:
            continue
        if any(phrase in lowered for phrase in config.EXIT_PHRASES):
            break

        try:
            answer = brain.think(text)
        except Exception as e:  # noqa: BLE001 — напр. Ollama не е стартиран
            print(f"[Грешка] {e}")
            answer = "Простете, сър, връзката с изкуствения ми интелект прекъсна."
        speaker.say(answer)

    speaker.say("Довиждане, сър. Ще бъда тук, ако ви потрябвам.")


if __name__ == "__main__":
    main()
