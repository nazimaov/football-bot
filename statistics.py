"""Статистика команд (форма, средние голы, ОЗ, ТБ2.5) и очные встречи (H2H) через RapidAPI."""
import logging
from datetime import datetime

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def get_team_last_matches(team_id: int, team_name: str) -> str:
    """Текстовый блок: последние матчи команды + форма/среднее голов/ОЗ/ТБ2.5."""
    try:
        url = f"{SOFA_BASE}/teams/get-last-matches"
        params = {"teamId": str(team_id), "page": "0"}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("get_team_last_matches(%s): статус %s", team_name, r.status_code)
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
        logger.exception("Ошибка get_team_last_matches(%s)", team_name)
        return f"\nОшибка {team_name}: {e}\n"


def get_h2h_text(match_id: int) -> str:
    """Текстовый блок: личные встречи команд (H2H) по matchId."""
    try:
        url = f"{SOFA_BASE}/matches/get-h2h-events"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        logger.debug("H2H status=%s", r.status_code)
        if r.status_code == 200:
            data = r.json()
            events = data.get("events") or data.get("h2h", {}).get("events") or data.get("managerDuel", {}).get("events") or []
            if isinstance(events, list):
                events = events[:5]
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
        logger.warning("get_h2h_text(%s): статус %s", match_id, r.status_code)
        return "\nH2H недоступно\n"
    except Exception:
        logger.exception("Ошибка get_h2h_text(%s)", match_id)
        return "\nH2H недоступно\n"
