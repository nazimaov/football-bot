import os
import requests
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
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
PORT = int(os.getenv("PORT", "10000"))

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
SOFA_HOST = "sofascore.p.rapidapi.com"
SOFA_BASE = f"https://{SOFA_HOST}"
TAVILY_URL = "https://api.tavily.com/search"

HEADERS = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": SOFA_HOST}


# ============================================================
# KEEP-ALIVE СЕРВЕР (чтобы Render не усыплял)
# ============================================================
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - bot is alive")
    def log_message(self, format, *args):
        pass  # не засоряем логи

def run_keep_alive():
    server = HTTPServer(("0.0.0.0", PORT), PingHandler)
    print(f"🟢 Keep-alive сервер на порту {PORT}")
    server.serve_forever()


# ============================================================
# ПОИСК КОМАНДЫ
# ============================================================
def search_team(team_name: str) -> dict:
    try:
        url = f"{SOFA_BASE}/search"
        params = {"q": team_name, "type": "teams", "page": "0"}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            return {}
        results = r.json().get("results", [])
        football_teams = []
        for item in results:
            if item.get("type") != "team":
                continue
            entity = item.get("entity", {})
            sport = entity.get("sport", {})
            if sport.get("id") == 1 or sport.get("slug") == "football":
                football_teams.append(entity)
        if not football_teams:
            return {}
        for team in football_teams:
            if team.get("name", "").lower() == team_name.lower():
                return {"id": team.get("id"), "name": team.get("name")}
            ru = team.get("fieldTranslations", {}).get("nameTranslation", {}).get("ru", "")
            if ru.lower() == team_name.lower():
                return {"id": team.get("id"), "name": team.get("name")}
        first = football_teams[0]
        return {"id": first.get("id"), "name": first.get("name")}
    except Exception as e:
        print(f"[search_team] {team_name}: {e}")
        return {}


def get_team_last_matches(team_id: int, team_name: str) -> str:
    try:
        url = f"{SOFA_BASE}/teams/get-last-matches"
        params = {"teamId": str(team_id), "page": "0"}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            return f"\nДанные по {team_name} недоступны\n"
        events = r.json().get("events", [])[:7]
        if not events:
            return f"\nНет матчей для {team_name}\n"
        result = f"\nПОСЛЕДНИЕ МАТЧИ {team_name.upper()}:\n"
        gs, gc, w, d, l = [], [], 0, 0, 0
        for m in events:
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            hs = m.get("homeScore", {}).get("current")
            as_ = m.get("awayScore", {}).get("current")
            ts = m.get("startTimestamp", 0)
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
            if hs is None or as_ is None:
                continue
            is_home = home.get("id") == team_id
            venue = "(д)" if is_home else "(в)"
            result += f"  {date} {venue}: {home.get('name','?')} {hs}:{as_} {away.get('name','?')}\n"
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


def get_next_match(team_id: int, opponent_id: int) -> dict:
    try:
        url = f"{SOFA_BASE}/teams/get-next-matches"
        params = {"teamId": str(team_id), "page": "0"}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            return {}
        events = r.json().get("events", [])
        for m in events:
            home_id = m.get("homeTeam", {}).get("id")
            away_id = m.get("awayTeam", {}).get("id")
            if opponent_id in (home_id, away_id):
                return m
        return {}
    except Exception:
        return {}


def split_teams(text: str) -> tuple[str, str]:
    """Умное разделение строки на две команды.
    Поддерживает: vs, -, –, —, /, |, x, против, и (даже без разделителя через поиск)."""
    text = text.strip()
    # Сначала пробуем явные разделители
    separators = [" vs ", " VS ", " v ", " против ", " - ", " – ", " — ", " / ", " | ", " x ", " X "]
    for sep in separators:
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    # Дефис без пробелов: "ямайка-юар"
    for sep in ["-", "–", "—", "/", "|"]:
        if sep in text:
            parts = text.split(sep, 1)
            t1, t2 = parts[0].strip(), parts[1].strip()
            if t1 and t2:
                return t1, t2
    # Нет разделителя — пробуем разделить пополам и проверить поиском
    words = text.split()
    if len(words) >= 2:
        # Пробуем все варианты разделения и берём тот где обе части находятся
        best = None
        for i in range(1, len(words)):
            t1 = " ".join(words[:i])
            t2 = " ".join(words[i:])
            r1 = search_team(t1)
            r2 = search_team(t2)
            if r1.get("id") and r2.get("id"):
                # обе нашлись — возвращаем сразу
                return t1, t2
            if not best and (r1.get("id") or r2.get("id")):
                best = (t1, t2)
        if best:
            return best
        # Fallback: пополам
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return text, ""


def get_h2h_text(match_id: int) -> str:
    try:
        url = f"{SOFA_BASE}/matches/get-h2h-events"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        # DEBUG
        print(f"[DEBUG H2H] status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"[DEBUG H2H] top keys: {list(data.keys())}")
            # Пробуем разные пути к событиям
            events = data.get("events") or data.get("h2h", {}).get("events") or data.get("managerDuel", {}).get("events") or []
            if isinstance(events, list):
                events = events[:5]
            print(f"[DEBUG H2H] events count: {len(events) if isinstance(events, list) else 'not list'}")
            if not events:
                return "\nЛичных встреч не найдено\n"
            result = f"\nЛИЧНЫЕ ВСТРЕЧИ ({len(events)}):\n"
            totals = []
            for m in events:
                home = m.get("homeTeam", {}).get("name", "?")
                away = m.get("awayTeam", {}).get("name", "?")
                hs = (m.get("homeScore") or {}).get("current") if isinstance(m.get("homeScore"), dict) else m.get("homeScore", 0)
                as_ = (m.get("awayScore") or {}).get("current") if isinstance(m.get("awayScore"), dict) else m.get("awayScore", 0)
                hs = hs or 0
                as_ = as_ or 0
                ts = m.get("startTimestamp", 0)
                date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
                result += f"  {date}: {home} {hs}:{as_} {away}\n"
                totals.append(hs + as_)
            if totals:
                result += f"  Средний тотал H2H: {sum(totals)/len(totals):.1f}\n"
            return result
        return "\nH2H недоступно\n"
    except Exception as e:
        print(f"[DEBUG H2H] error: {e}")
        return "\nH2H недоступно\n"


def get_match_detail(match_id: int) -> dict:
    try:
        url = f"{SOFA_BASE}/matches/detail"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            return {}
        return r.json().get("event", {})
    except Exception:
        return {}


def get_lineups(match_id: int) -> str:
    try:
        url = f"{SOFA_BASE}/matches/get-lineups"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            return "\n[!] Составы ещё не опубликованы\n"
        data = r.json()
        if data.get("confirmed") is False:
            return "\n[!] Составы ещё не подтверждены\n"
        home = data.get("home", {})
        away = data.get("away", {})
        if not home and not away:
            return "\n[!] Составы недоступны\n"
        result = "\n=== СТАРТОВЫЕ СОСТАВЫ ===\n"
        for team_data, label in [(home, "Хозяева"), (away, "Гости")]:
            formation = team_data.get("formation", "?")
            players = team_data.get("players", [])
            starters = [p for p in players if not p.get("substitute", False)]
            result += f"\n{label} ({formation}):\n"
            for p in starters[:11]:
                pi = p.get("player", {})
                name = pi.get("name", "?")
                pos = p.get("position", "")
                result += f"  • {name} ({pos})\n"
            missing_list = team_data.get("missingPlayers", []) or []
            if missing_list:
                result += f"  Травмы/диск.:\n"
                for mp in missing_list[:5]:
                    mname = mp.get("player", {}).get("name", "?")
                    reason = mp.get("type", "?")
                    result += f"    ✗ {mname} ({reason})\n"
        return result
    except Exception as e:
        return f"\nОшибка составов: {e}\n"


def get_referee_info(match_detail: dict) -> str:
    referee = match_detail.get("referee", {})
    if isinstance(referee, dict):
        ref_name = referee.get("name", "")
    else:
        ref_name = str(referee) if referee else ""
    if not ref_name:
        return "\n[!] Судья не назначен\n"
    result = f"\n=== СУДЬЯ: {ref_name} ===\n"
    if isinstance(referee, dict):
        yc = referee.get("yellowCards")
        rc = referee.get("redCards")
        games = referee.get("games")
        if games:
            result += f"  Матчей: {games}\n"
        if yc is not None and games:
            result += f"  Жёлтых: {yc} ({yc/games:.1f}/матч)\n"
        if rc is not None:
            result += f"  Красных: {rc}\n"
    if TAVILY_KEY:
        try:
            payload = {"api_key": TAVILY_KEY, "query": f"{ref_name} football referee yellow cards", "search_depth": "basic", "max_results": 2}
            r = requests.post(TAVILY_URL, json=payload, timeout=15)
            if r.status_code == 200:
                snippets = [item.get("content", "")[:250] for item in r.json().get("results", [])[:2]]
                snippets = [s for s in snippets if s]
                if snippets:
                    result += "Из веба:\n"
                    for s in snippets:
                        result += f"  • {s}\n"
        except Exception:
            pass
    return result


def get_weather(city: str) -> str:
    if not OPENWEATHER_KEY or not city:
        return ""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return f"\n[!] Погода для {city} недоступна\n"
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
        if isinstance(wind, (int, float)) and wind > 8: warnings.append("сильный ветер")
        if isinstance(temp, (int, float)):
            if temp < 3: warnings.append("холодно")
            elif temp > 28: warnings.append("жара")
        if "дожд" in desc.lower() or "rain" in desc.lower(): warnings.append("дождь")
        if warnings:
            result += "  ⚠ " + ", ".join(warnings) + "\n"
        return result
    except Exception as e:
        return f"\n[!] Погода: {e}\n"


def extract_venue_city(*sources) -> tuple[str, str]:
    """Ищет stadium и city во всех возможных местах. Возвращает (stadium, city)."""
    stadium = ""
    city = ""
    for src in sources:
        if not isinstance(src, dict):
            continue
        # Пробуем разные пути к venue
        venue = src.get("venue") or src.get("stadium") or {}
        if isinstance(venue, dict):
            # stadium name
            if not stadium:
                stadium = (venue.get("name") or 
                           (venue.get("stadium") or {}).get("name", "") if isinstance(venue.get("stadium"), dict) else venue.get("stadium", "") or
                           "")
            # city
            if not city:
                c = venue.get("city")
                if isinstance(c, dict):
                    city = c.get("name", "")
                elif isinstance(c, str):
                    city = c
                if not city:
                    city = venue.get("cityName", "") or ""
                # Иногда город в country
                if not city:
                    country = venue.get("country", {})
                    if isinstance(country, dict):
                        city = country.get("name", "")
        # Город может быть прямо в матче
        if not city:
            c = src.get("city") or src.get("cityName")
            if isinstance(c, dict):
                city = c.get("name", "")
            elif isinstance(c, str):
                city = c
    return stadium, city


def extract_referee(*sources) -> tuple[str, dict]:
    """Ищет судью во всех возможных местах."""
    for src in sources:
        if not isinstance(src, dict):
            continue
        ref = src.get("referee")
        if isinstance(ref, dict) and ref.get("name"):
            return ref.get("name"), ref
        if isinstance(ref, str) and ref:
            return ref, {}
    return "", {}


def gather_all_data(team1_name: str, team2_name: str) -> tuple[str, dict]:
    info = "=== ДАННЫЕ МАТЧА ===\n"
    quality = {"team_stats": False, "lineups": False, "referee": False, "weather": False, "h2h": False}
    team1 = search_team(team1_name)
    team2 = search_team(team2_name)
    if team1.get("id"):
        info += get_team_last_matches(team1["id"], team1.get("name", team1_name))
        quality["team_stats"] = True
    else:
        info += f"\n[!] '{team1_name}' не найдена\n"
    if team2.get("id"):
        info += get_team_last_matches(team2["id"], team2.get("name", team2_name))
        quality["team_stats"] = True
    else:
        info += f"\n[!] '{team2_name}' не найдена\n"
    if team1.get("id") and team2.get("id"):
        match = get_next_match(team1["id"], team2["id"])
        if match:
            match_id = match.get("id")
            ts = match.get("startTimestamp", 0)
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"
            
            # Берём детали матча — там обычно больше инфы
            detail = get_match_detail(match_id) or {}
            
            # ЛОГИРУЕМ в Render что вернул API (видно в logs)
            print(f"[DEBUG] match keys: {list(match.keys())}")
            print(f"[DEBUG] detail keys: {list(detail.keys())}")
            print(f"[DEBUG] match.venue: {match.get('venue')}")
            print(f"[DEBUG] detail.venue: {detail.get('venue')}")
            print(f"[DEBUG] match.referee: {match.get('referee')}")
            print(f"[DEBUG] detail.referee: {detail.get('referee')}")
            
            # Ищем стадион и город во ВСЕХ возможных местах
            stadium, city = extract_venue_city(match, detail)
            if not stadium: stadium = "?"
            
            info += f"\n=== МАТЧ НАЙДЕН ===\nДата: {date} UTC\nСтадион: {stadium}\nГород: {city or '(не указан)'}\n"
            
            # H2H
            h2h = get_h2h_text(match_id)
            info += h2h
            if "не найдено" not in h2h and "недоступно" not in h2h:
                quality["h2h"] = True
            
            # Судья — ищем во всех источниках
            ref_name, ref_data = extract_referee(match, detail)
            if ref_name:
                ref_text = f"\n=== СУДЬЯ: {ref_name} ===\n"
                if ref_data:
                    yc = ref_data.get("yellowCards")
                    rc = ref_data.get("redCards")
                    games = ref_data.get("games")
                    if games: ref_text += f"  Матчей: {games}\n"
                    if yc is not None and games:
                        ref_text += f"  Жёлтых: {yc} ({yc/games:.1f}/матч)\n"
                    if rc is not None: ref_text += f"  Красных: {rc}\n"
                info += ref_text
                quality["referee"] = True
            else:
                info += "\n[!] Судья не назначен или не указан в API\n"
            
            # Составы
            lineups = get_lineups(match_id)
            info += lineups
            if "[!]" not in lineups:
                quality["lineups"] = True
            
            # Погода — пробуем найти даже если city пустой
            if city:
                w = get_weather(city)
                info += w
                if w and "[!]" not in w:
                    quality["weather"] = True
            else:
                info += "\n[!] Город не определён, погода пропущена\n"
        else:
            info += "\n[!] Ближайший матч не найден через get-next-matches\n"
    return info, quality


SYSTEM_PROMPT = """Ты профессиональный футбольный аналитик. Работаешь СТРОГО с данными.

ПРИОРИТЕТЫ:
1. СОСТАВЫ — отсутствие лидеров меняет прогноз
2. ФОРМА (среднее голов, ОЗ, ТБ2.5)
3. H2H
4. ПОГОДА — ветер >8 м/с снижает тотал
5. СУДЬЯ — если есть стата
6. ДОМ/ВЫЕЗД — +0.3 голу дома

ПРАВИЛА:
- [!] = данных нет → уверенность 40-50%
- НЕ выдумывай. Только данные
- 70%+ ТОЛЬКО при явном перевесе
- Угловые/карточки ≤55%

ФОРМАТ:

МАТЧ: [К1] vs [К2]
КАЧЕСТВО ДАННЫХ: [Высокое/Среднее/Низкое]

КЛЮЧЕВЫЕ ФАКТОРЫ:
- [3-5 пунктов]

АНАЛИЗ СОСТАВОВ: [Кто отсутствует]
ПОГОДА: [1-2 предл.]
СУДЬЯ: [Имя + стата]

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

Аналитика, не гарантия."""


def analyze_sync(match_name: str) -> str:
    team1, team2 = split_teams(match_name)
    if not team2:
        return "Напиши две команды. Например: Реал Мадрид - Барселона"
    info, quality = gather_all_data(team1, team2)
    qs = f"\n[Качество: форма={quality['team_stats']}, H2H={quality['h2h']}, составы={quality['lineups']}, судья={quality['referee']}, погода={quality['weather']}]"
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ AI Football Analyst v7\n\n"
        "Просто напиши две команды любым способом:\n"
        "• Реал Мадрид vs Барселона\n"
        "• Ямайка - Южная Африка\n"
        "• Manchester City Liverpool\n"
        "• Бавария / Дортмунд\n\n"
        "📊 Форма | 👥 Составы | 🤕 Травмы\n"
        "👨‍⚖️ Судья | 🌦 Погода | 📈 H2H\n\n"
        "Лучше за 30-60 мин до матча."
    )

async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Реал Мадрид vs Барселона")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Напиши: Команда1 vs Команда2")

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
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, analyze_sync, match_name)
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
        print("❌ Нет ключей")
        return
    if not OPENWEATHER_KEY: print("⚠ OPENWEATHER_KEY не задан")
    if not TAVILY_KEY: print("⚠ TAVILY_KEY не задан")
    
    # Запускаем keep-alive в отдельном потоке
    keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
    keep_alive_thread.start()
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("example", example_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_message))
    print("✅ Бот работает!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
