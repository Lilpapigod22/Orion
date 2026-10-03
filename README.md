# O.R.I.O.N. — a modular voice assistant

**O**perational, **R**easoning, **I**ntelligent, **O**n-duty **N**avigator — a personal AI assistant that
gets things done for you. In Bulgarian the acronym reads *Оперативен, Разумен, Интелигентен, Отговорен
Наместник* ("a deputy who acts on your behalf"). You call it with „Орион, …“ (the old names „Митко“ and
„Джарвис“ still work).

Orion runs locally on your PC: a local language model (Ollama, `qwen3.5:9b`) on the graphics card,
speech recognition (Google + Whisper), a neural voice, and a holographic 3D interface inspired by
J.A.R.V.I.S. The interface and code are in English; **Orion listens and speaks Bulgarian**, so the example
commands below are in Bulgarian with an English translation.

## Starting

**Double-click the Orion icon** on the Desktop (or search for "Orion" in the Start menu).

On start-up Orion checks its systems, starts Ollama if it is not running, downloads the model if it is
missing, loads it onto the graphics card and greets you.

If the icon is missing: `python app.py --install-shortcut` (creates it again).
From a terminal: `python app.py` (window) or `python main.py --text` (console mode).

## Talking to it

| Action | How |
|---|---|
| Type | The box at the bottom + Enter |
| Speak | **F2**, the microphone button, or click the core in the centre |
| Interrupt | **Esc**, or click the core while it is speaking |
| Always on | Turn on **"Always listen"** and say *„Орион, колко е часът?“* (Orion, what time is it?) |
| Mute | Turn off **"Voice"** |
| Close by voice | *„Орион, затвори се“*, *„изключи се“* or *„довиждане“* (close / shut down / goodbye) |

In "Always listen" mode Orion only answers phrases that contain its name — otherwise it would answer
the TV and conversations in the room. Exceptions where the name is not needed:
- one reply right after the start-up greeting (the answer to „С какво мога да помогна?“ — "How can I help?");
- after a spoken answer — up to 3 replies in a row, so you can keep the conversation going.

If it hears a phrase without its name, a tip appears in the journal (at most once every 90 seconds).

**Instant commands.** The time (also in other cities), the date, the day of the week, the weather,
opening programs and websites, Google/YouTube searches and timers are recognised directly
(`orion/reflexes.py`) — without the language model, so they are instant and always correct:
*„Колко е часът в Токио“* (time in Tokyo), *„Кой ден от седмицата е“* (what day is it),
*„Какво е времето във Варна“* (weather in Varna), *„Отвори ми Chrome“* (open Chrome), *„Пусни Steam“*
(start Steam), *„Потърси в Google рецепта за баница“* (search Google), *„Пусни ми Мадона в YouTube“*
(play Madonna on YouTube), *„Таймер за 10 минути“* (10-minute timer). Also everyday requests the small
model used to answer "from its head": *„Хвърли монета“* (flip a coin), *„Хвърли два зара“* (roll two dice),
*„Измисли число от 5 до 20“*, *„Избери между пица, суши и бургер“*, *„Преведи на английски добър вечер“*
(translate), *„Колко километра е от София до Бургас“* (distance), *„Ще вали ли утре“* (will it rain),
*„Кога залязва слънцето“* (sunset), *„Кога е следващият празник“* (next holiday), *„Генерирай парола“*
(password), *„Пусни помодоро“*, *„Прочети какво съм копирал“* (read the clipboard), *„Покажи работния плот“*
(show the desktop), *„Следваща песен“* (next song). Polite beginnings like *„може ли да…“* or *„кажи ми…“*
are fine. Everything else goes to the model.

**Links** in the journal (for example the list of free videos) open in your browser with a click.

**Programs.** Orion opens any program or game with a shortcut in the Start menu or on the Desktop
(Chrome, Steam, Discord, Word…), plus the names in `PROGRAMS` in `orion/apps.py` (calculator, notepad,
settings…). Websites are in `SITES` there.

## What else it can do

| Area | Examples (Bulgarian → English) |
|---|---|
| Web information | *„Какъв е курсът на еврото?“* (euro exchange rate), *„Какви са новините днес?“* (today's news), *„Кой спечели мача на Левски?“* (who won the Levski match) |
| Reminders | *„Напомни ми след 20 минути да изключа фурната“* (remind me in 20 minutes to turn off the oven), *„Напомни ми утре в 9 да платя тока“* |
| Timer | *„Таймер за 10 минути“*, *„Засечи 5 минути“* (10-minute / 5-minute timer) |
| Calendar | *„Какво имам утре?“* (what do I have tomorrow), *„Запиши ми среща със Стефан в петък в 3 следобед“* (meeting with Stefan on Friday at 3 pm) |
| Mail | *„Имам ли нови писма?“* (any new emails), *„Прочети първото“* (read the first), *„Отговори му, че съм съгласен“* (reply that I agree), *„Пиши на Мария, че…“* (write to Maria that…) |
| Tasks | *„Добави купи мляко в задачите“* (add "buy milk"), *„Какво имам да правя?“* (what's on my list), *„Отбележи млякото като свършено“* (mark it done) |
| Sound and music | *„Намали звука“* (volume down), *„Звука на 30“* (volume 30), *„Заглуши“* (mute), *„Пауза“*, *„Следващата песен“* (next song), *„Пусни ми Мадона в YouTube“* |
| The computer | *„Как е компютърът ми?“* (computer status), *„Затвори Chrome“*, *„Заключи компютъра“* (lock), *„Изключи компютъра след 30 минути“* (shut down in 30 minutes), *„Отмени изключването“* (cancel) |
| Vision | *„Какво има на екрана?“* (what is on the screen), *„Прочети ми грешката на екрана“* (read the error), *„Направи снимка на екрана“* (screenshot) |
| Files | *„Отвори свалените файлове“* (open Downloads), *„Намери файла фактура“* (find the invoice file), *„Отвори първия“*, *„Прочети какво съм копирал“* (read the clipboard) |
| Look-ups | *„Кой е Иван Вазов?“* (who is Ivan Vazov), *„Колко са 100 долара в евро?“*, *„Колко километра са 10 мили?“*, *„Ще вали ли утре?“* (will it rain tomorrow) |
| Games | *„Пусни Апекс“*, *„Пусни лол“*, *„Отвори хой“*, *„Какви игри имам?“* (Steam, Riot, Epic and Microsoft Store) |
| Markets | *„Анализирай биткойна“* (analyse bitcoin), *„Анализирай евро долар на 4 часа“* (EUR/USD on 4h), *„Как е Nvidia?“*, *„Какво става на пазарите?“*, *„Кои криптовалути растат?“*, *„Анализирай файла EURUSDH4“* |
| Claude | *„Попитай Claude …“* (ask Claude — Orion reads out the answer), *„Напиши на Claude …“* (opens the Claude app with the text ready) |
| Lists and notes | *„Добави мляко и хляб в списъка“* (add to the shopping list), *„Какво има в списъка?“*, *„Запиши си бележка…“* (take a note) |
| Dates and holidays | *„Кога е следващият празник?“* (next public holiday), *„Кога има имен ден Георги?“* (name day), *„Коя дата е след 100 дни?“*, *„Кога залязва слънцето?“* (sunset) |
| Forecast+ | *„Прогнозата за седмицата“* (weekly forecast), *„Какъв е въздухът в София?“* (air quality) |
| Network | *„Каква е скоростта на интернета?“* (speed test), *„Какъв е моят IP?“*, *„Работи ли abv.bg?“* (is the site up), *„Кой е заел порт 3000?“* (who uses port 3000) |
| Files+ | *„Кои са най-големите ми файлове?“* (largest files), *„Почисти временните файлове“* (clean temp files), *„Прочети ми документа“*, *„Изпразни кошчето“* (empty the Recycle Bin) |
| Windows | *„Кое натоварва компютъра?“* (what is slowing the PC), *„Включи тъмния режим“* (dark mode), *„Отвори настройките на Bluetooth“*, *„Напиши в Word …“* (type into Word) |
| Trading | *„Кажи ми, когато биткойнът стигне 100 хиляди“* (price alert), *„Добави 0.1 биткойна в портфейла“* (portfolio), *„Покажи портфейла“*, *„Индексът страх и алчност“* (Fear & Greed) |
| Calculators | *„Вноската по кредит 100 000 за 20 години при 3%“* (loan payment), *„120 с ДДС колко е без ДДС?“* (VAT), *„Колко ще струва горивото до Варна?“* (fuel cost) |
| Tools | *„Хвърли зар“* (roll a die), *„Генерирай парола“* (password), *„Направи QR код за…“*, *„Преведи на английски…“* (translate) |
| YouTube reels | *„Рийл“* — Orion picks a free video itself and cuts reels; *„Намери видеа без авторски права за космоса“* (find free videos); paste a link into the chat → Orion cuts reels (free videos only); *„Анализирай този клип <link>“* (analyse), *„Направи 5 рийла по 30 секунди от <link>“*, *„Готови ли са рийловете?“* (are they ready), *„Покажи рийловете“* (show them) |
| More | *„Добро утро“* (good morning — a daily briefing), *„Какво можеш?“* (what can you do — all 190+ skills by group) |

**Markets.** Data comes from Yahoo Finance (stocks, indices, crypto, currencies, gold, oil) and
CoinGecko (the crypto market). The indicators — trend, SMA 20/50/200, RSI, MACD, Bollinger bands,
support and resistance, volatility — are computed in code (`orion/markets.py`); Orion explains them in
words and shows a chart in the journal (hover over it for values). It can also analyse CSV files exported
from MetaTrader. This is technical analysis, not investment advice.

**Claude.** "Ask Claude" uses Claude Code (`claude -p`) from your subscription — Claude only gets web
search; it cannot touch files or run commands. The full answer is in the journal and on the clipboard.
"Write to Claude" opens the Claude app with the text ready — you send it yourself with Enter (the app
deliberately asks when text comes from another program).

Closing programs, shutting down, restarting and sleep only happen after a button press in the window.
System programs (and Orion itself) cannot be closed by voice. Vision takes a screenshot for a moment
(Orion's window hides so it does not get in the way) and the **local** model looks at it — the image
never leaves the computer and is not saved.

Reminders are stored in `memory/reminders.json`. If Orion was closed when a reminder was due, it
announces it at the next start.

**Emails are only sent after the "Send" button.** Orion shows the recipient, subject and text;
"Reject" (or Esc) stops the email. The same applies to deleting a calendar event. Names („пиши на
Мария“ — "write to Maria") are looked up in emails you have received or sent.

## Connecting Google (mail, calendar, tasks) — once, about 5 minutes

Say or type **„Орион, свържи Google“** (Orion, connect Google). Orion copies the code of a small
script, opens script.google.com and shows the steps in the journal:

1. Sign in to your Google account if the page asks.
2. Delete the code in the editor (Ctrl+A) and paste the copied code (Ctrl+V). Save with Ctrl+S.
3. On the left, next to **Services**, press **+**, choose **Google Tasks API** → **Add**.
4. Top right: **Deploy → New deployment** → the gear icon → **Web app**.
5. **Execute as: Me**, **Who has access: Anyone** → **Deploy**.
6. **Authorize access** → your account → **Advanced** → **Go to … (unsafe)** → **Allow**.
   Google calls the script "unverified" because it is your own, not one published in the store.
7. Copy the **Web app URL** (ends with `/exec`) and paste it into Orion's input box.

How it is protected: the script runs in your account and only answers requests with a secret key
that is in its code and in `google_settings.json` on this computer. Never share the address or that
file. To revoke access — in script.google.com: **Deploy → Manage deployments → Archive** (or delete
the script).

Colours: **blue** — Orion (speaking/thinking), **amber** — listening to you, **red** — malfunction.

## The eyes and the live board

In the centre are Orion's eyes (3D, `web/src/components/Eyes3D.jsx`; 2D fallback without WebGL). They show
its state: blue and looking around while waiting, amber while listening, squinting while thinking, a voice
wave while speaking, ^ ^ after a finished task, red and tilted after an error, green in test mode and
sleepy after 10 quiet minutes. They follow the mouse and glance at the skill that is running.

Under the eyes the live board shows every request step by step — heard → understood → thinking → skill →
speaking — with the time of each step; click a step to see what exactly happened (both transcripts, which
skills the model saw, its reasoning as it streams, the skill's arguments and result). The top bar shows
the GPU, video memory, processor and memory once a second, the speed of the last answer (tokens/s) and
its total time; test mode, reels and proposals waiting for approval appear next to them.

## The network — how Orion thinks

The left part of the window is a 3D hologram of its mind (`web/src/engine/mind.js`):

- **The eyes** in the centre (see above) — the network orbits around them.
- **The bubbles** around it — its abilities: Mail, Calendar, Tasks, Internet, Apps, Clock, Weather,
  Maths, Reminders, Memory, Evolution, Hearing and Voice, and more.
- **The neurons** behind — they spark quietly, and a storm of pulses runs through them while it thinks.
- **"THOUGHT"** next to the eyes — the model's current reasoning: what it understood and what it will do.
- When it uses a skill, the bubble lights up, a pulse travels from the core to it, and a **task bubble**
  pops up next to it ("searching …"), followed by the result ("5 results · …").
- Pending timers and reminders orbit around "Reminders" with a countdown.

Rotate the network by dragging it with the mouse. Hover over a bubble to see what it can do; click to
pin the description. Click the eyes = speak.

## Reels from YouTube

**Only free videos.** Orion makes reels only from videos whose authors chose the **Creative Commons —
Attribution (CC BY)** licence on YouTube: anyone may reuse them, in their own videos too, as long as the
author is credited. Videos with the standard YouTube licence (all rights reserved) are refused, and so
are "free" videos that look re-uploaded from someone else: "I don't own the rights" in the description,
another company's name in the title (National Geographic, BBC, NFL…), music, films and series,
compilations and match footage. To find suitable videos say *„намери видеа без авторски права за
космоса“* ("find copyright-free videos about space"): Orion searches YouTube with the Creative Commons
filter, checks every result, lists them with links in the journal, and then *„направи рийлове от
номер 2“* ("make reels from number 2") cuts them. `description.txt` contains the ready credit line
the licence requires — paste it into the description of every reel. Orion checks the licence the
author chose; if a video still contains someone else's music or footage, YouTube's Content ID may
recognise it (you would see that in YouTube Studio). `REEL_FREE_ONLY = False` in `config.py` allows
any video (for example your own).

**Just say „Рийл“ ("Reel").** Orion picks the video by itself: it searches free (Creative Commons) videos on
three topics it has not used lately (`REEL_TOPICS` in `config.py`), ranks them by how much interest they
already get (views, views per day, likes, YouTube's "most replayed" data, enough length), lets the
language model choose like a Shorts producer, tells you which video it chose and why, and cuts the reels.
Ready-made Shorts and videos it already made reels from are skipped. *„Рийл за космоса“* ("a reel
about space") picks within a topic; *„направи 2 рийла“* sets the number.

Paste a link to a video into the input box (or say *„направи рийлове от този клип“* — "make
reels from this video" — after an analysis). Orion answers straight away, works in the background and tells you out
loud when it is done. The top of the window shows how far it has got ("reels · listening to moment
2/5"). It takes 1–2 minutes when the video has English subtitles or the graphics card is free, and
3–5 minutes when Whisper transcribes on the processor (the graphics card is busy with Orion and your
open programs).

1. **Signals — which moments people like most.** Every second gets a score from YouTube's
   *"Most replayed"* graph (above the progress bar — where viewers rewind and watch again), **comments
   with a timestamp** ("3:45 I died laughing", weighted by likes; chapter lists are ignored) and — when
   YouTube has no viewing data (a new or small video) — **loudness** (laughter, shouting, music): the
   main signal if there are no timestamped comments either, otherwise a weaker helper. The
   intro and the "ramp" towards the end (credits, looping) are not counted. The strongest spots become
   candidates — two more than the number of reels requested.
2. **Editor.** Orion reads what is said in each candidate (the video's manual subtitles, automatic ones
   only for English, otherwise Whisper) and the language model picks a self-contained clip: it opens
   with a **hook**, ends on a **punchline**, makes sense on its own, is cut at sentence boundaries (never
   mid-word) and gets a **score of 1–10**. The best ones become reels.
3. **Framing (9:16, 1080×1920)** — chosen automatically:
   - **talking person / podcast** — full screen, the frame follows the face in every scene (with two
     people — one of them, not the empty space between them);
   - **gaming video with a webcam in the corner** — the webcam on top, the game below (the streamer
     layout);
   - **games, animation, scenery** — the whole frame over a blurred copy of itself. Black bars are removed.
4. **Clean picture and exact sync.** Only the video and its sound, with no text on top. Picture and
   sound are cut by YouTube's own timestamps, so they stay exactly together (checked to within one
   frame) and each reel starts exactly on the chosen moment. Audio is levelled to YouTube's standard
   (-14 LUFS).
5. **Ready to upload.** A folder `D:\OrionData\reels\<video>\` with the reels, a **cover** for each and
   `description.txt`: where each moment comes from, why it was picked, its score and hook, a **suggested
   title and hashtags** (in the video's own language — nothing is translated; set `REEL_TITLE_LANGUAGE`
   in `config.py` to force one language) and its text.

Default: 3 reels of 45 seconds without text (`REEL_COUNT`, `REEL_SECONDS`, `REEL_SUBTITLES`). Say
„със субтитри“ ("with subtitles") to get word-by-word subtitles (the current word yellow and slightly
larger) and a title in the first seconds.

## Crypto forecasts and trading (Hyperliquid)

Orion forecasts and trades **Bitcoin, Ethereum and Solana** on Hyperliquid — the exchange behind Trust
Wallet's "Perps" tab. Every number comes from code (`orion/trading/`); the language model only reads it out.

- „Какво ще прави биткойнът?“ / „Прогноза за солана“ — direction (or "no signal"), entry, stop, target,
  strength 1–5, and how often that strategy won in the honest check.
- „Сигнали“ — all three coins. „Колко добри са стратегиите?“ — the check, per strategy and coin.
  „Колко позна тази седмица?“ — the real outcomes of Orion's own signals.
- „Отвори лонг на биткойн“, „Затвори етериума“, „Затвори всички позиции“ — every open and close shows an
  approval dialog with every number; nothing happens without „Одобри“.
- „Спри търговията“ / „Пусни търговията“, „Мини на истински пари“ / „Мини на тестовата мрежа“.

**How honest the forecasts are.** Three strategies (trend pullback, breakout, reversal at a crowded extreme)
are replayed on ≈3.4 years of 1h candles with fees, slippage and funding. Numbers are tuned only on the first
70 %; what Orion reports comes from the last 30 %. A strategy is used for a coin only with ≥30 trades, a
positive result after costs and a profit factor ≥1.1. If none passes, Orion says it has no edge.

**Safety.** Hard limits in `trading_settings.json` (default: 2 % of the account at risk per trade, ≤10x,
≤6 % loss per day, ≤3 positions); isolated margin; the stop and target sit on the exchange; a position
without a stop is closed at once. The API key can trade but **cannot withdraw**; it is stored encrypted
(Windows DPAPI) and typed only in its own dialog. Orion never asks for the recovery phrase.

**Connecting (once).** Say „Свържи Hyperliquid“ → open app.hyperliquid-testnet.xyz, connect Trust Wallet, page
API → Generate → approve in Trust Wallet → paste the wallet address and the API key into Orion's dialog.
Start on the testnet; switch to real money only with „Мини на истински пари“ and its warning dialog.

**Test mode** practises trading every round: a $10 000 virtual account takes every signal on live prices, the
strategy lab tries other numbers (promoted only after beating the current ones on unseen history AND in 20
practice trades), and once a day a minimum-size testnet order checks that stops and targets are placed.

## Test mode — Orion checks and fixes itself

Turn it on with the **"Test mode"** switch at the bottom right or by voice: „Орион, включи тест режим“
(„тествай се“, „самопровери се“). „Спри теста“ stops it, and „как мина теста?“ tells you the result.

One round (the first takes about 10–15 minutes):

1. **Skills.** More than 120 checks of the skills with sample data — in a *sandbox*: notes, reminders,
   alerts and the portfolio are temporary copies, nothing opens on screen, the clipboard is restored,
   and every confirmation (email, deletion) is rejected. Dangerous skills (shutdown, email, sound,
   deletion, settings, documents) are never run.
2. **Understanding.** More than 45 ready-made requests plus new ones Orion **invents itself** every round
   for its least-tested skills. They go through the same path as real ones (instant commands → model),
   and the test checks whether it picked the right skill. Actions are not executed — only recorded.
   Invented requests are kept in `memory/self_tests.json` and re-checked every round.
3. **Fixes.**
   - *A misunderstood request* — Orion learns a keyword for skill selection (`memory/learned_routes.json`),
     rewrites the skill's description (only the text changes — it is verified that the code stays the
     same) or records a lesson — a rule in its instructions (at most 10 from test mode). A change is
     kept only if the request is now understood 3 times out of 3 and the older tests still pass. A
     description is reverted with „върни предишната версия на <skill>“, a lesson with „забрави поука
     номер …“.
   - *A broken skill* — Orion writes new code and checks it in the sandbox against all of the file's
     tests. It is enabled **only after "Approve and enable"** — the code runs with full access to the
     computer.
   - Instant commands (reflexes), thinking and listening are the core — it does not touch them; if there
     is a problem there, it goes into the report.
4. **Report** — in the journal (green "▸ test"), out loud, and in `logs/self_test.md`.

While you talk to it, tests wait and any request already sent to the model is cancelled — you never
wait for a test. While test mode is on, the check repeats every 10 minutes with new requests (skills
every 3 rounds). The progress shows at the top, next to the status.

## Structure

```
Orion/
├── app.py               # the windowed application (started from the icon)
├── main.py              # console mode
├── config.py            # ALL settings + the persona (system prompt)
├── requirements.txt
├── orion/
│   ├── brain.py         # Thinking   (LLM + skill calls)
│   ├── reflexes.py      # Instant commands (time, date, opening…) without the LLM
│   ├── apps.py          # Finding and starting programs and websites
│   ├── clock.py         # Date and time in Bulgarian, time zones
│   ├── when.py          # „утре в 3 следобед“, „след 20 минути“ -> date and time
│   ├── web.py           # Web search and reading pages
│   ├── google.py        # Gmail, Calendar and Tasks (through integrations/)
│   ├── reminders.py     # Reminders and timers
│   ├── confirm.py       # Button confirmation before emails and deletions
│   ├── games.py         # Games from Steam, Riot and Epic
│   ├── markets.py       # Market data and technical analysis
│   ├── vision.py        # Vision: the screen and images through the local model
│   ├── router.py        # Which skills the model sees for each request
│   ├── reels.py         # YouTube reels: moment analysis and vertical videos
│   ├── self_test.py     # Test mode: self-check and self-repair
│   ├── self_test_cases.py # the ready-made checks and requests for test mode
│   ├── listener.py      # Listening  (speech_recognition, Google)
│   ├── speech.py        # Whisper speech recognition (graphics card or processor)
│   ├── voice.py         # Speaking   (edge-tts neural voice)
│   ├── speaker.py       # Offline fallback voice (pyttsx3)
│   ├── knowledge.py     # Knowledge  (RAG: search in knowledge/)
│   ├── tools.py         # Skills     (the @orion_tool decorator)
│   ├── memory.py        # Short-term conversation memory
│   └── ollama_manager.py# Automatic set-up of the local model
├── web/                 # the window's source — React + Vite:
│   └── src/             #   components/ (top bar, stage, journal, console), engine/ (3D network,
│                        #   reactor, voice, chart), bridge.js (window.hud — the link with Python)
├── ui/                  # the built window that app.py opens (made by `npm run build` in web/)
├── assets/              # the icon
├── skills/              # ← add new skills here (.py files)
├── knowledge/           # ← add knowledge here (.txt, .md, .pdf)
├── integrations/        # the Google bridge script (copied into script.google.com)
├── google_settings.json # bridge address and secret key (created when connecting — keep it private)
└── logs/orion.log       # application messages and errors
```

## Installation (already done on this computer)

```bash
pip install -r requirements.txt
```

The window is already built in `ui/`, so Orion runs without Node. Only after changing the window's
code in `web/src/` (needs Node.js 20+):

```bash
cd web
npm install      # once
npm run build    # writes the new window to ui/
```

### Option A: Local model (Ollama, free) — the default

1. Install Ollama from https://ollama.com
2. Start Orion — the `qwen3.5:9b` model downloads automatically (~6.6 GB).

Orion creates its own variant `orion-qwen3.5:9b` with a larger "working memory" (16,000 tokens instead
of 4,096) — without using extra disk space. When it closes, it frees the video memory.

qwen3.5 can "think" before answering. Orion lets it think briefly while deciding which skill to use
(`LLM_REASONING_EFFORT = "low"` in `config.py`) and answers directly after the skill's result. The
earlier model `qwen2.5:7b` also works (`LLM_MODEL` in `config.py`), but its Bulgarian is weaker and it
makes things up more often.

On this computer the models are on drive **D:** (`D:\Ollama\models`) because C: is nearly full.
The folder `C:\Users\Gamer\.ollama\models` is a junction to D:, so Ollama finds them whatever folder
is chosen in its settings.

### Option B: OpenAI

```powershell
$env:ORION_PROVIDER = "openai"
$env:OPENAI_API_KEY  = "sk-..."
python app.py
```

## Adding KNOWLEDGE

Just put a file in `knowledge/` — `.txt`, `.md` or `.pdf`. Sub-folders work too. No restart is needed:
Orion checks whether the folder has changed on every question.

An example of telling it about yourself is in `examples/about_me_example.md` — copy it into
`knowledge/` and replace the details with yours. (The example lives outside `knowledge/` because
otherwise Orion took what it says — "My name is Tony" — as the truth and signed your emails "Tony".)

You can also "teach" it by voice: *„Орион, запомни, че паролата на WiFi-то е в чекмеджето.“* (Orion,
remember that the Wi-Fi password is in the drawer.) It saves the fact in `knowledge/remembered_notes.md`
and remembers it after a restart.

Tips:
- While the knowledge is under ~6,000 characters, Orion reads **all** of it for every question.
  Above that it searches for the most relevant pieces by keywords.
- Write one topic per paragraph — the text is split by paragraphs.
- Scanned PDFs (images) contain no text and cannot be read.

## Adding SKILLS

Create a file in `skills/` (or copy `skills/_template.py`):

```python
# skills/spotify.py
from orion import orion_tool

@orion_tool
def play_music(song: str) -> str:
    """Plays a song when sir asks for music.

    Args:
        song: The name of the song or artist.
    """
    import webbrowser
    webbrowser.open(f"https://open.spotify.com/search/{song}")
    return f"Пускам {song}."
```

Close and reopen Orion — that is all. The model decides when to call the skill based on its
**docstring** — so write it clearly ("use when…"). Every skill call shows in the journal on the right
(▸ SKILL). The returned text is what Orion reads out, so it is in Bulgarian.

- Type hints (`str`, `int`, `float`, `bool`) define the parameter types.
- Parameters without a default value are required.
- If the function raises an error, Orion receives it as text and tells you politely.

## Persona and memory

- The persona is `PERSONA` in `config.py` — rules only, no example replies. Small models copy
  examples word for word (they answered „Тридесет и шест“ — "thirty-six" — to every sum), so the tone
  is described in words.
- If the model says "Opening…" without actually calling a skill, Orion sends it back to do it or to
  admit that it cannot (`ACTION_CLAIM_RE` in `orion/brain.py`).
- `MEMORY_MAX_TURNS` sets how many exchanges it remembers. The conversation is saved in
  `memory/conversation.json` and Orion remembers it after a restart — if it is from the last
  `MEMORY_KEEP_HOURS` hours (12).

## How it was made smarter

- **Skill selection** (`orion/router.py`). There are over 190 skills — far too many at once for a small
  model. The core ones are always offered; groups such as mail/calendar, computer, vision and look-ups
  only when the request is about them. With fewer choices the model makes fewer mistakes.
- **Thinks as much as needed.** Simple requests are fast (`LLM_REASONING_EFFORT`); questions with
  „защо“, „обясни“, „сравни“, „помогни ми“ (why, explain, compare, help me) get deeper reasoning
  (`LLM_DEEP_REASONING_EFFORT`).
- **Checks facts.** For people, places, events and dates it uses Wikipedia or the web instead of
  relying on its memory — that is where small models make things up.
- **Does not lie about its actions.** If it says "I turned the volume down" or writes a skill name as
  text without running it, it gets a note and runs it (or honestly says it did not manage).
- **Instant commands** for everything common and unambiguous — time, sound, music, programs, shutdown…
- **A larger "working memory"** — 16,000 tokens (`OLLAMA_CONTEXT`), for long conversations and pages.

## The voice

- It speaks with Microsoft's neural voice **Borislav** (`NEURAL_VOICE` in `config.py`).
  Others: `bg-BG-KalinaNeural` (female), `en-GB-RyanNeural` (British, as in the films).
- The neural voice and speech recognition need the internet. Without it Orion falls back to the
  Windows voice (pyttsx3), which reads Cyrillic with an English accent.

## If something does not work

Look at `logs/orion.log` — everything is recorded there with the time: what the microphone heard
(`[You]`), what was ignored without “Orion”, what you asked (`[Sir]`), which skills were called and with
what result (`[Skill]`), and what Orion answered (`[Orion]`).

**Speech recognition.** Orion listens with Google and Whisper at the same time (a speech AI that runs
on the graphics card, `orion/speech.py`). Google writes Bulgarian words better, Whisper English names
("Steam", "Hearts of Iron"), so the better result is chosen. Whisper only starts if at least 1.5 GB of
video memory is free — otherwise only Google is used and the language model is not slowed down. The
model (1.6 GB) and the graphics-card libraries (2 GB) are on drive D: (`D:\OrionData`). Settings in
`config.py`: `STT_ENGINE` ("auto" or "google").

**Waits for you to finish.** Orion assumes you have finished after 1.5 seconds of silence
(`LISTEN_PAUSE_SECONDS`; it used to be 0.8 and cut you off at every pause for thought), and one
utterance can be up to 30 seconds (`PHRASE_TIME_LIMIT`).

**The microphone.** Orion uses the Windows default microphone, and if that does not open — the next one
(e.g. the webcam's). If a USB microphone is unplugged and plugged back in, Orion reconnects by itself;
"Always listen" only switches off if there is no microphone for ~30 seconds. For tests:
`python app.py --mute --no-mic` (no voice and no microphone — "Microphone" is red at start-up, which is
normal).
