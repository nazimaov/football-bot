import os
import requests
import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction

# ============================================================
# НАСТРОЙКИ
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY", "")
TAVILY_KEY = os.getenv("TAVILY_KEY", "")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
RAPIDAPI_BASE = f"https://{RAPIDAPI_HOST}"
TAVILY_URL = "https://api.tavily.com/search"

RAPIDAPI_HEADERS = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}


def search_team(team_name: str) -> dict:
    try:
        url = f"{RAPIDAPI_BASE}/football-search?search={requests.utils.quote(team_name)}"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=10)
        if r.status_code == 200:
            suggestions = r.json().get("response", {}).get("suggestions", [])
            for item in suggestions:
                if item.get("type") == "team":
                    name = item.get("teamName") or item.get("name", "")
                    if name.lower() == team_name.lower():
                        return {"id": item.get("teamId") or item.get("id"), "name": name}
            for item in suggestions:
                if item.get("type") == "team":
                    return {"id": item.get("teamId") or item.get("id"),
                            "name": item.get("teamName") or item.get("name", team_name)}
    except Exception as e:
        print(f"[search_team] {e}")
    return {}


def find_upcoming_match(team1_id: int, team2_id: int) -> dict:
    try:
        url = f"{RAPIDAPI_BASE}/football-get-fixtures-between-teams?firstTeamId={team1_id}&secondTeamId={team2_id}"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=15)
        if r.status_code != 200:
            return {}
        matches = r.json().get("response", {}).get("fixtures", [])
        now = datetime.utcnow()
        best, best_delta = None, timedelta(days=999)
        for m in matches:
            if m.get("status") == "FT":
                continue
            try:
                m_date = datetime.fromisoformat(m.get("date", "").replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue
            delta = m_date - now
            if delta > timedelta(hours=-3) and abs(delta) < best_delta:
                best, best_delta = m, abs(delta)
        return best or {}
    except Exception as e:
        print(f"[find_upcoming] {e}")
    return {}


def get_team_recent_matches(team_id: int, team_name: str) -> str:
    try:
        url = f"{RAPIDAPI_BASE}/football-get-all-fixtures-by-teamid?teamid={team_id}&page=1"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=15)
        if r.status_code != 200:
            return f"\nДанные по {team_name} недоступны\n"
        matches = r.json().get("response", {}).get("fixtures", [])
        finished = [m for m in matches if m.get("status") == "FT"][-7:]
        if not finished:
            return f"\nНет матчей {team_name}\n"
        result = f"\nПОСЛЕДНИЕ МАТЧИ {team_name.upper()}:\n"
        gs, gc, w, d, l = [], [], 0, 0, 0
        for m in finished:
            home = m.get("homeTeam", {}).get("name", "?")
            away = m.get("awayTeam", {}).get("name", "?")
            hs, as_ = m.get("homeGoals"), m.get("awayGoals")
            date = m.get("date", "")[:10]
            if hs is not None and as_ is not None:
                venue = "(д)" if m.get("homeTeam", {}).get("id") == team_id else "(в)"
                result += f"  {date} {venue}: {home} {hs}:{as_} {away}\n"
                is_home = m.get("homeTeam", {}).get("id") == team_id
                scored, conceded = (hs, as_) if is_home else (as_, hs)
                gs.append(scored); gc.append(conceded)
                if scored > conceded: w += 1
                elif scored == conceded: d += 1
                else: l += 1
        if gs:
            avg_s, avg_c = sum(gs)/len(gs), sum(gc)/len(gc)
            btts = sum(1 for i in range(len(gs)) if gs[i] > 0 and gc[i] > 0)
            over25 = sum(1 for i in range(len(gs)) if gs[i] + gc[i] > 2)
            result += f"  Форма: {w}В {d}Н {l}П | Среднее: {avg_s:.1f}-{avg_c:.1f} (тотал {avg_s+avg_c:.1f})\n"
            result += f"  ОЗ: {btts}/{len(gs)} | ТБ2.5: {over25}/{len(gs)}\n"
        return result
    except Exception as e:
        return f"\nОшибка {team_name}: {e}\n"


def get_h2h_text(team1_id: int, team2_id: int) -> str:
    try:
        url = f"{RAPIDAPI_BASE}/football-get-fixtures-between-teams?firstTeamId={team1_id}&secondTeamId={team2_id}"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=15)
        if r.status_code != 200:
            return "\nH2H недоступно\n"
        matches = r.json().get("response", {}).get("fixtures", [])
        finished = [m for m in matches if m.get("status") == "FT"][:5]
        if not finished:
            return "\nЛичных встреч нет\n"
        result = f"\nЛИЧНЫЕ ВСТРЕЧИ ({len(finished)}):\n"
        totals = []
        for m in finished:
            home = m.get("homeTeam", {}).get("name", "?")
            away = m.get("awayTeam", {}).get("name", "?")
            hs, as_ = m.get("homeGoals", 0) or 0, m.get("awayGoals", 0) or 0
            result += f"  {m.get('date', '')[:10]}: {home} {hs}:{as_} {away}\n"
            totals.append(hs + as_)
        if totals:
            result += f"  Средний тотал H2H: {sum(totals)/len(totals):.1f}\n"
        return result
    except Exception:
        return "\nH2H недоступно\n"


def get_lineups(match_id) -> str:
    try:
        url = f"{RAPIDAPI_BASE}/football-get-lineups-by-matchid?matchid={match_id}"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=15)
        if r.status_code != 200:
            return "\n[!] Составы ещё не опубликованы\n"
        data = r.json().get("response", {})
        lineups = data.get("lineups", [])
        if not lineups:
            return "\n[!] Составы ещё не опубликованы\n"
        result = "\n=== СТАРТОВЫЕ СОСТАВЫ ===\n"
        for team in lineups[:2]:
            tname = team.get("teamName", "?")
            formation = team.get("formation", "?")
            starters = team.get("starters", []) or team.get("startXI", [])
            result += f"\n{tname} ({formation}):\n"
            for p in starters[:11]:
                pname = p.get("name") or p.get("playerName", "?")
                pos = p.get("position", "")
                result += f"  • {pname} ({pos})\n"
        missing = data.get("missingPlayers", []) or data.get("injuries", [])
        if missing:
            result += "\nТРАВМЫ/ДИСКВ.:\n"
            for p in missing[:10]:
                pname = p.get("name") or p.get("playerName", "?")
                reason = p.get("reason", "травма")
                result += f"  ✗ {pname} ({reason})\n"
        return result
    except Exception as e:
        return f"\nОшибка составов: {e}\n"


def get_referee_info(match_data: dict) -> str:
    referee = match_data.get("referee") or match_data.get("officials", {}).get("referee", "")
    if isinstance(referee, dict):
        referee = referee.get("name", "")
    if not referee:
        return "\n[!] Судья не назначен\n"
    result = f"\n=== СУДЬЯ: {referee} ===\n"
    if TAVILY_KEY:
        try:
            payload = {"api_key": TAVILY_KEY,
                       "query": f"{referee} football referee yellow cards per game statistics",
                       "search_depth": "basic", "max_results": 3}
            r = requests.post(TAVILY_URL, json=payload, timeout=15)
            if r.status_code == 200:
                snippets = [item.get("content", "")[:300] for item in r.json().get("results", [])[:3]]
                snippets = [s for s in snippets if s]
                if snippets:
                    result += "Инфа из веба:\n"
                    for s in snippets:
                        result += f"  • {s}\n"
                else:
                    result += "Статистика не найдена\n"
        except Exception as e:
            result += f"Ошибка поиска: {e}\n"
    else:
        result += "[Tavily не подключён]\n"
    return result


def get_weather(city: str) -> str:
    if not OPENWEATHER_KEY or not city:
        return ""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={requests.utils.quote(city)}&appid={OPENWEATHER_KEY}&units=metric&lang=ru"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return f"\n[!] Погода {city} недоступна\n"
        d = r.json()
        temp = d.get("main", {}).get("temp")
        feels = d.get("main", {}).get("feels_like")
        wind = d.get("wind", {}).get("speed")
        desc = d.get("weather", [{}])[0].get("description", "")
        humidity = d.get("main", {}).get("humidity")
        result = f"\n=== ПОГОДА в {city} ===\n"
        result += f"  {desc.capitalize()} | {temp}°C (ощущ. {feels}°C)\n"
        result += f"  Ветер: {wind} м/с | Влажность: {humidity}%\n"
        warnings = []
        if isinstance(wind, (int, float)) and wind > 8:
            warnings.append("сильный ветер — снижает дальние удары/навесы")
        if isinstance(temp, (int, float)):
            if temp < 3: warnings.append("холодно — выгоднее физически сильным")
            elif temp > 28: warnings.append("жара — спад во 2 тайме")
        if "rain" in desc.lower() or "дожд" in desc.lower():
            warnings.append("дождь — мокрое поле, ошибки")
        if "snow" in desc.lower() or "снег" in desc.lower():
            warnings.append("снег — нестандарт")
        if warnings:
            result += "  ⚠ " + "; ".join(warnings) + "\n"
        return result
    except Exception as e:
        return f"\n[!] Погода: {e}\n"


def gather_all_data(team1_name: str, team2_name: str) -> tuple[str, dict]:
    info = "=== ДАННЫЕ МАТЧА ===\n"
    quality = {"team_stats": False, "lineups": False, "referee": False, "weather": False}
    team1 = search_team(team1_name)
    team2 = search_team(team2_name)
    if team1.get("id"):
        info += get_team_recent_matches(team1["id"], team1.get("name", team1_name))
        quality["team_stats"] = True
    else:
        info += f"\n[!] '{team1_name}' не найдена\n"
    if team2.get("id"):
        info += get_team_recent_matches(team2["id"], team2.get("name", team2_name))
        quality["team_stats"] = True
    else:
        info += f"\n[!] '{team2_name}' не найдена\n"
    match_data = {}
    if team1.get("id") and team2.get("id"):
        info += get_h2h_text(team1["id"], team2["id"])
        match_data = find_upcoming_match(team1["id"], team2["id"])
    if match_data:
        match_id = match_data.get("id") or match_data.get("matchId")
        venue = match_data.get("venue", {})
        city = venue.get("city", "") or venue.get("name", "") if isinstance(venue, dict) else ""
        info += f"\n=== МАТЧ НАЙДЕН ===\nДата: {match_data.get('date', '')}\n"
        info += f"Стадион: {venue if isinstance(venue, str) else venue.get('name', '?')}\n"
        if match_id:
            l = get_lineups(match_id)
            info += l
            if "[!]" not in l: quality["lineups"] = True
        ri = get_referee_info(match_data)
        info += ri
        if "[!]" not in ri: quality["referee"] = True
        if city:
            w = get_weather(city)
            info += w
            if w and "[!]" not in w: quality["weather"] = True
    else:
        info += "\n[!] Предстоящий матч не найден — составы/судья/погода пропущены\n"
    return info, quality


SYSTEM_PROMPT = """Ты профессиональный футбольный аналитик. Работаешь СТРОГО с данными.

ПРИОРИТЕТЫ:
1. СОСТАВЫ — отсутствие ключевых игроков меняет прогноз сильнее всего
2. ФОРМА последних матчей (среднее голов, ОЗ, ТБ2.5)
3. ЛИЧНЫЕ ВСТРЕЧИ — характер матчей
4. ПОГОДА — ветер >8 м/с снижает тотал; дождь = больше ошибок; жара = спад во 2 тайме
5. СУДЬЯ — если есть данные про карточки
6. ДОМ/ВЫЕЗД — +0.3 голу дома обычно

ПРАВИЛА:
- [!] = данных нет → уверенность 40-50%
- Без составов — прогноз "предварительный"
- НЕ выдумывай. Только данные
- 70%+ уверенность ТОЛЬКО при явном перевесе в цифрах
- Угловые/карточки ≤55%

ФОРМАТ:

МАТЧ: [К1] vs [К2]
КАЧЕСТВО ДАННЫХ: [Высокое/Среднее/Низкое] (✓составы ✓погода ✓судья ✓форма)

КЛЮЧЕВЫЕ ФАКТОРЫ:
- [3-5 пунктов из данных]

АНАЛИЗ СОСТАВОВ:
[Кто отсутствует, как влияет. Если нет — "не опубликованы"]

ПОГОДА: [1-2 предл., если нет — пропусти]

СУДЬЯ: [Имя + что известно]

ЦИФРЫ:
- Средний тотал: К1 X.X | К2 X.X
- ОЗ: X/5 vs Y/5
- Форма: WDL vs WDL
- H2H тотал: X.X

РЕКОМЕНДАЦИИ:
ПОБЕДИТЕЛЬ: [...] | [%]
ФОРА: [...] | [%]
ТОТАЛ: [Б/М X.5] | [%]
ОБЕ ЗАБЬЮТ: [Да/Нет] | [%]
УГЛОВЫЕ: [Б/М X.5] | ≤55%
КАРТОЧКИ: [Б/М X.5] | ≤55%

ГЛАВНАЯ СТАВКА: [одна]
Обоснование: [конкретные цифры]

РИСКИ: [что может пойти не так]

Аналитика, не гарантия. Играй ответственно."""


def analyze_sync(match_name: str) -> str:
    separators = [" vs ", " - ", " VS ", " v ", " против "]
    team1, team2 = match_name, ""
    for sep in separators:
        if sep in match_name:
            parts = match_name.split(sep, 1)
            team1, team2 = parts[0].strip(), parts[1].strip()
            break
    if not team2:
        return "Формат: Команда1 vs Команда2"

    info, quality = gather_all_data(team1, team2)
    qs = f"\n[Качество: форма={quality['team_stats']}, составы={quality['lineups']}, судья={quality['referee']}, погода={quality['weather']}]"

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Матч: {match_name}\n\n{info}\n{qs}\n\nДай прогноз СТРОГО по цифрам."}
        ],
        "temperature": 0.3, "max_tokens": 2500
    }
    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "Время истекло."
    except requests.exceptions.HTTPError:
        if r.status_code == 429: return "Слишком много запросов."
        return f"Ошибка Groq: {r.status_code}"
    except Exception as e:
        return f"Ошибка: {e}"


async def analyze(match_name: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, analyze_sync, match_name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ AI Football Analyst v3\n\n"
        "Напиши: Команда1 vs Команда2\n\n"
        "Учитываю:\n"
        "📊 Форму 7 матчей | 👥 Составы | 🤕 Травмы\n"
        "👨‍⚖️ Судья | 🌦 Погода | 📈 H2H\n\n"
        "Лучше всего: за 30-60 мин до матча."
    )

async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Manchester City vs Liverpool\nReal Madrid vs Barcelona")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Напиши матч: Команда1 vs Команда2")

async def analyze_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_name = update.message.text.strip()
    if match_name.startswith("/"): return
    if len(match_name) < 5:
        await update.message.reply_text("Напиши: Команда1 vs Команда2")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    loading = await update.message.reply_text(
        f"🔍 {match_name}\n📊 Форма...\n👥 Составы...\n🌦 Погода...\n👨‍⚖️ Судья...\n⏱ 25-40 сек"
    )
    result = await analyze(match_name)
    try: await loading.delete()
    except: pass
    if len(result) > 4000:
        for part in [result[i:i+4000] for i in range(0, len(result), 4000)]:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(result)
    kb = [[InlineKeyboardButton("🔄 Другой матч", callback_data="new")]]
    await update.message.reply_text("Готово!", reply_markup=InlineKeyboardMarkup(kb))


def main():
    if not all([TELEGRAM_BOT_TOKEN, GROQ_API_KEY, RAPIDAPI_KEY]):
        print("❌ Нет TELEGRAM_BOT_TOKEN/GROQ_API_KEY/RAPIDAPI_KEY")
        return
    if not OPENWEATHER_KEY: print("⚠ OPENWEATHER_KEY не задан — погода пропущена")
    if not TAVILY_KEY: print("⚠ TAVILY_KEY не задан — судья пропущен")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("example", example_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_message))
    print("✅ Бот работает!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
