"""
Игрите на сър — от Steam, Riot (League of Legends, VALORANT) и Epic Games.
Пускането става с open_program („пусни Апекс“), тук е списъкът.
"""
from jarvis import games, jarvis_tool

_SOURCES = {"steam": "Steam", "riot": "Riot", "epic": "Epic Games"}


@jarvis_tool
def list_games() -> str:
    """Кои игри са инсталирани на компютъра (Steam, Riot, Epic). За „какви игри имам“."""
    found = games.installed()
    if not found:
        return "Не намирам инсталирани игри в Steam, Riot или Epic Games."
    by_source: dict[str, list[str]] = {}
    for game in found:
        by_source.setdefault(_SOURCES.get(game.source, game.source), []).append(game.name)
    return (f"Инсталирани игри ({len(found)}): "
            + "; ".join(f"{source}: {', '.join(names)}" for source, names in by_source.items())
            + ". Пускат се с „пусни …“.")
