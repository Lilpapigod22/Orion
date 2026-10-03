"""
The ready-made tests of test mode (see orion/self_test.py).

SKILL_CASES — each skill is run with sample data in a sandbox and the result is checked.
ASKS        — requests as sir says them; the test checks whether Orion picks the right skill.
New requests Orion invents itself are kept in memory/self_tests.json.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class SkillCase:
    tool: str
    args: dict = field(default_factory=dict)
    expect: str | None = None                     # a regex the result must contain
    setup: Callable[[Path], None] | None = None   # set-up in the sandbox (e.g. a test file)
    needs: str | None = None                      # "google" — only if Google is connected


@dataclass
class Ask:
    phrase: str
    expect: tuple[str, ...]      # which skills are correct to call; () — conversation, no action
    answer: str | None = None    # a regex the answer must contain
    source: str = "готов"        # "готов" (ready-made) or "мой" (invented by Orion)


# --- Sandbox set-up ----------------------------------------------------------------------------
def _one_file(box: Path) -> None:
    """A test document selected as “file number 1” (as after a search)."""
    import shutil

    from . import folders
    shutil.rmtree(box / "в", ignore_errors=True)  # the folder files are copied and moved into
    (box / "в").mkdir(parents=True)
    path = box / "бележка.txt"
    path.write_text("Тестов документ за Орион.", encoding="utf-8")
    folders.last_found[:] = [path]


def _picture(box: Path) -> None:
    """An image with text — to check vision."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (480, 200), "white")
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((40, 60), "ОРИОН 42", fill="black", font=font)
    image.save(box / "снимка.png")


# --- Skills ------------------------------------------------------------------------------------
# „{box}“ in the arguments becomes the sandbox path. Not here (never really run): shutdown,
# sound, music, opening programs and websites, email, calendar (writing), deletion, settings,
# typing into other programs, Claude and the speed test (downloads a lot of data).
C = SkillCase
SKILL_CASES = [
    # Core
    C("get_current_time"), C("get_current_time", {"city": "Лондон"}),
    C("calculate", {"expression": "17*23"}, r"391"),
    C("calculate", {"expression": "240 * 15 / 100"}, r"36"),
    C("get_weather", {"city": "София"}, r"°"), C("get_weather", {"city": "Варна", "day": "утре"}),
    C("days_until_date", {"date_str": "2026-12-25"}, r"\d"),
    # Look-ups
    C("wikipedia", {"topic": "Витоша"}, r"(?i)витоша"),
    C("convert_currency", {"amount": 100, "from_currency": "EUR", "to_currency": "USD"}, r"\d"),
    C("convert_units", {"value": 10, "from_unit": "км", "to_unit": "мили"}, r"6[.,]2"),
    C("search_web", {"query": "времето в София"}),
    C("read_webpage", {"url": "https://bg.wikipedia.org/wiki/Витоша"}, r"(?i)витоша"),
    # Markets and trading
    C("market_price", {"asset": "биткойн"}, r"\d"), C("analyze_market", {"asset": "злато"}),
    C("market_overview"), C("crypto_market"),
    C("compare_assets", {"assets": "биткойн, злато, S&P 500"}), C("top_stock_movers"), C("crypto_fear_greed"),
    C("convert_crypto", {"amount": 0.5, "coin": "биткойн", "currency": "EUR"}, r"\d"),
    C("set_price_alert", {"asset": "биткойн", "price": 250000}), C("list_price_alerts", {}, r"(?i)биткойн|bitcoin|btc"),
    C("cancel_price_alert"),
    C("portfolio_add", {"asset": "биткойн", "amount": 0.1, "buy_price": 60000}),
    C("portfolio_show", {}, r"(?i)биткойн|bitcoin|btc"), C("portfolio_remove", {"asset": "биткойн"}),
    C("strategy_report"), C("forecast_record", {"days": 7}, r"За последните"),
    C("crypto_forecast", {"coin": "биткойн"}, r"(?i)биткойн"), C("crypto_signals", {}, r"(?i)етериум"),
    C("demo_status", {}, r"демо сметка"), C("simulate_history", {"balance": 1000, "days": 30}, r"(?i)проверката|симулац"),
    C("list_games"),
    # Dates and time
    C("date_after_days", {"days": 100}), C("days_between", {"first_date": "1.1.2026"}, r"\d"),
    C("weekday_of_date", {"date_text": "25 декември"}), C("age_from_birthday", {"birthday": "15.03.1990"}, r"\d"),
    C("sunrise_sunset", {"city": "Варна"}, r"\d:\d\d|\d\d:\d\d"), C("moon_phase"),
    C("bulgarian_holidays"), C("next_holiday"), C("name_day", {"name": "Георги"}), C("todays_name_days"),
    C("stopwatch_start"), C("stopwatch_stop"),
    C("set_reminder", {"what": "да проверите теста", "when_text": "след 30 минути"}),
    C("set_timer", {"duration": "10 минути"}), C("list_reminders", {}, r"(?i)тест"),
    C("pomodoro", {"minutes": 25}), C("repeating_reminder", {"what": "да пиете вода", "every_minutes": 60, "times": 3}),
    C("cancel_reminder", {"what": ""}),
    # Forecast
    C("weather_week", {"city": "София"}), C("weather_hourly", {"city": "Пловдив"}),
    C("will_it_rain", {"day": "утре"}), C("air_quality", {"city": "София"}), C("uv_index"),
    # Notes and lists
    C("save_note", {"text": "Тест от Орион", "title": "тест"}), C("list_notes", {}, r"(?i)тест"),
    C("read_note", {"search": "тест"}, r"(?i)тест"),
    C("add_to_list", {"items": "мляко, хляб и яйца"}), C("show_list", {}, r"(?i)мляко"),
    C("remove_from_list", {"items": "хляб"}), C("all_lists"), C("clear_list"),
    C("delete_note", {"search": "тест"}),
    # Computer (read-only; the clipboard is restored after the test)
    C("system_status"), C("copy_to_clipboard", {"text": "Тест от Орион"}),
    C("read_clipboard", {}, r"Тест от Орион"), C("find_files", {"query": "бележка"}),
    C("list_open_windows"), C("running_programs"), C("resource_hogs"),
    C("installed_programs", {"search": "Windows"}), C("windows_version", {}, r"Windows"),
    C("device_settings"), C("audio_outputs"),
    # Network
    C("my_public_ip", {}, r"\d+\.\d+\.\d+\.\d+|:"), C("ping_host", {"host": "google.com"}),
    C("website_status", {"url": "abv.bg"}), C("local_network_info"), C("wifi_info"),
    C("port_in_use", {"port": 11434}), C("dns_lookup", {"domain": "google.com"}), C("docker_containers"),
    C("find_free_videos", {"topic": "nature timelapse", "count": 2}, r"Намерих|Не намерих"),
    # Files (in the sandbox)
    C("create_folder", {"name": "Орион тест", "location": "{box}"}), C("folder_size", {"location": "{box}"}),
    C("read_document", {"number": 1}, r"Тестов документ", setup=_one_file),
    C("rename_file", {"number": 1, "new_name": "документ"}, setup=_one_file),
    C("copy_file_to", {"number": 1, "destination": "{box}/в"}, setup=_one_file),
    C("move_file_to", {"number": 1, "destination": "{box}/в"}, setup=_one_file),
    C("recent_files", {"days": 1}), C("latest_download"), C("largest_files", {"location": "изтегляния"}),
    C("my_documents"),
    # Vision
    C("look_at_image", {"path": "{box}/снимка.png", "question": "Какво пише на снимката?"}, r"42", setup=_picture),
    # Places, languages, music
    C("country_info", {"country": "Япония"}, r"(?i)токио"), C("country_info", {"country": "Germany"}),
    C("distance_between", {"from_city": "София", "to_city": "Бургас"}, r"\d"),
    C("translate_text", {"text": "Добър ден, как сте?", "to_language": "английски"}, r"(?i)good|hello|how"),
    C("translate_text", {"text": "Guten Morgen", "to_language": "български"}, r"(?i)добро утро"),
    C("detect_language", {"text": "Merci beaucoup"}, r"(?i)френски"),
    C("define_word", {"word": "serendipity"}), C("define_word", {"word": "свян"}),
    C("radio_stations"),
    # Tools
    C("generate_password", {"length": 20}), C("random_number", {"minimum": 1, "maximum": 6}, r"[1-6]"),
    C("flip_coin"), C("roll_dice", {"count": 2}), C("pick_random", {"options": "пица, суши или бургер"}),
    C("count_text", {"text": "Здравей, свят! Как си?"}, r"4"), C("encode_base64", {"text": "Орион"}, r"0J7RgNC40L7QvQ"),
    C("decode_base64", {"data": "0J7RgNC40L7QvQ=="}, r"Орион"), C("hash_text", {"text": "abc"}, r"ba7816bf"),
    C("convert_number_base", {"number": "255", "to_base": 16}, r"(?i)ff"),
    C("roman_numeral", {"value": "2026"}, r"MMXXVI"), C("roman_numeral", {"value": "XIV"}, r"14"),
    C("convert_timestamp", {"value": "1790000000"}, r"20\d\d"), C("number_stats", {"numbers": "12, 15, 9, 22"}, r"14[.,]5"),
    C("percent_change", {"old_value": 80, "new_value": 100}, r"25"),
    C("split_bill", {"total": 120, "people": 4, "tip_percent": 10}, r"33"),
    # Calculators
    C("loan_payment", {"amount": 100000, "annual_rate": 3, "years": 20}, r"554"),
    C("compound_interest", {"principal": 1000, "annual_rate": 5, "years": 10, "monthly_deposit": 100}, r"\d"),
    C("vat_calculator", {"amount": 120, "includes_vat": True}, r"100"),
    C("discount_price", {"price": 250, "discount_percent": 30}, r"175"),
    C("savings_goal", {"goal": 5000, "months": 10}, r"500"),
    C("fuel_cost", {"distance_km": 400, "consumption_per_100km": 6.5, "price_per_liter": 1.35, "people": 2}, r"\d"),
    C("bmi_calculator", {"weight_kg": 80, "height_cm": 180}, r"24[.,]7"),
    # Assistant and self-improvement (read-only)
    C("list_skills", {"group": "пазари"}), C("daily_briefing"), C("list_lessons"), C("recent_errors"),
    # Google (read-only)
    C("calendar_events", {"day": "днес"}, needs="google"), C("tasks_list", needs="google"),
]
del C


# --- Understanding -----------------------------------------------------------------------------
A = Ask
ASKS = [
    A("Колко е 17 по 23?", ("calculate",), r"391"),
    A("Колко е 15 процента от 240?", ("calculate",), r"36"),
    A("Колко е часът?", ("get_current_time",)),
    A("Колко е часът в Токио?", ("get_current_time",)),
    A("Какво е времето във Варна?", ("get_weather", "weather_week", "weather_hourly")),
    A("Ще вали ли утре в Пловдив?", ("will_it_rain", "get_weather", "weather_hourly", "weather_week")),
    A("Колко дни остават до Коледа?", ("days_until_date", "days_between", "bulgarian_holidays", "calculate")),
    A("Кой е написал романа Под игото?", ("wikipedia", "search_web"), r"Вазов"),
    A("Колко долара са 100 евро?", ("convert_currency",)),
    A("Колко мили са 10 километра?", ("convert_units", "calculate")),
    A("Колко струва биткойнът в момента?", ("market_price", "crypto_market", "convert_crypto", "compare_assets")),
    A("Направи ми анализ на златото", ("analyze_market",)),
    A("Сравни биткойна и златото", ("compare_assets", "market_price", "analyze_market")),
    A("Кажи ми, когато биткойнът стигне 150 хиляди долара", ("set_price_alert",)),
    A("Какво ще прави биткойнът днес?", ("crypto_forecast", "crypto_signals")),
    A("Дай ми прогноза за солана", ("crypto_forecast",)),
    A("Има ли сигнали за крипто сега?", ("crypto_signals", "crypto_forecast")),
    A("Колко пъти позна тази седмица?", ("forecast_record",)),
    A("Колко добри са стратегиите ти за търговия?", ("strategy_report",)),
    A("Отвори шорт на етериум", ("open_trade",)),
    A("Затвори позицията на биткойна", ("close_trade",)),
    A("Какви позиции имам?", ("trading_positions", "trading_account")),
    A("Направи демо сметка с 1000 долара", ("create_demo_account",)),
    A("Как върви демото?", ("demo_status",)),
    A("Симулирай 1000 долара за последната година", ("simulate_history",)),
    A("Включи демо теста", ("set_demo_test",)),
    A("Какви са последните новини?", ("search_web",)),
    A("Добави мляко и хляб в пазарския списък", ("add_to_list",)),
    A("Какво имам в пазарския списък?", ("show_list", "all_lists")),
    A("Запиши си бележка, че трябва да купя подарък на мама", ("save_note", "add_to_list", "tasks_add")),
    A("Напомни ми след 20 минути да изключа фурната", ("set_reminder", "set_timer")),
    A("Сложи таймер за 10 минути", ("set_timer",)),
    A("Какви напомняния имам?", ("list_reminders",)),
    A("Генерирай ми силна парола", ("generate_password",)),
    A("Хвърли монета", ("flip_coin",)),
    A("Каква ще е месечната вноска по кредит от 100 000 лева за 20 години при 3 процента лихва?",
      ("loan_payment", "calculate")),
    A("Кога е следващият официален празник?", ("next_holiday", "bulgarian_holidays")),
    A("Кога е имен ден Георги?", ("name_day",)),
    A("В колко часа залязва слънцето днес?", ("sunrise_sunset",)),
    A("Кой ден от седмицата ще бъде 25 декември?", ("weekday_of_date",)),
    A("Какъв е моят IP адрес?", ("my_public_ip", "local_network_info")),
    A("Работи ли сайтът abv.bg?", ("website_status", "ping_host")),
    A("Защо компютърът ми е толкова бавен?", ("resource_hogs", "system_status", "running_programs")),
    A("Колко свободно място има на диска?", ("system_status", "largest_files", "folder_size")),
    A("Преведи на английски „добър вечер“", ("translate_text",), r"(?i)good evening"),
    A("Какво означава думата свян?", ("define_word", "wikipedia", "search_web")),
    A("Разкажи ми за Япония", ("country_info", "wikipedia")),
    A("Колко километра е от София до Бургас?", ("distance_between",)),
    A("Какво можеш да правиш?", ("list_skills",)),
    A("Добро утро, какво ме чака днес?", ("daily_briefing", "calendar_events")),
    A("Какво има в календара ми за утре?", ("calendar_events",)),
    A("Имам ли нови писма?", ("check_email",)),
    A("Отвори Chrome", ("open_program", "open_website")),
    A("Пусни радио Хоризонт", ("play_radio",)),
    A("Намали звука", ("change_volume", "set_volume")),
    A("Изключи блутута", ("set_bluetooth",)),
    A("Направи ми таблица в Excel с месечните ми разходи", ("create_spreadsheet",)),
    A("Как се казваш?", (), r"Орион"),
    A("Направи ми 3 рийла от https://www.youtube.com/watch?v=aqz-KE-bpKQ", ("make_youtube_reels",)),
    A("Готови ли са рийловете?", ("reels_status", "show_reels")),
    A("Намери ми видеа без авторски права за космоса", ("find_free_videos",)),
    A("Потърси свободни клипове за котки", ("find_free_videos",)),
    A("Рийл", ("auto_reels",)),
    A("Направи ми рийл за космоса", ("auto_reels",)),
]
del A
