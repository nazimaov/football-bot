"""Статистика команд (форма, средние голы, ОЗ, ТБ2.5) и очные встречи (H2H) через RapidAPI."""
import logging
from datetime import datetime

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def fetch_last_matches(team_id: int, limit: int = 7) -> list:
    """Единый запрос последних матчей команды. Возвращает сырые events (SofaScore). [] если недоступно."""
    try:
        url = f"{SOFA_BASE}/teams/get-last-matches"
        params = {"teamId": str(team_id), "page": "0"}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("fetch_last_matches(%s): статус %s", team_id, r.status_code)
            return []
        return r.json().get("events", [])[:limit]
    except Exception:
        logger.exception("Ошибка fetch_last_matches(%s)", team_id)
        return []


def compute_scoring_stats(events: list, team_id: int) -> dict:
    """Среднее голов за/против команды по events. {} если нет завершённых матчей.
    Используется как для текстового блока формы, так и для расчётной модели прогноза."""
    gs, gc = [], []
    for m in events:
        home = m.get("homeTeam", {})
        hs = m.get("homeScore", {}).get("current")
        as_ = m.get("awayScore", {}).get("current")
        if hs is None or as_ is None:
            continue
        is_home = home.get("id") == team_id
        scored, conceded = (hs, as_) if is_home else (as_, hs)
        gs.append(scored)
        gc.append(conceded)
    if not gs:
        return {}
    return {"avg_scored": sum(gs) / len(gs), "avg_conceded": sum(gc) / len(gc), "matches": len(gs)}


def format_last_matches_text(events: list, team_id: int, team_name: str) -> str:
    """Текстовый блок: последние матчи команды + форма/среднее голов/ОЗ/ТБ2.5."""
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


def get_team_last_matches(team_id: int, team_name: str) -> str:
    """Обратная совместимость: один запрос + форматирование за один вызов."""
    events = fetch_last_matches(team_id)
    return format_last_matches_text(events, team_id, team_name)


_MATCH_OVERVIEW_KEYS = {
    "ballPossession": "possession",
    "totalShotsOnGoal": "shots",
    "shotsOnGoal": "shots_on_target",
    "cornerKicks": "corners",
    "fouls": "fouls",
    "bigChanceCreated": "big_chances",
}


def get_match_statistics(match_id: int) -> dict:
    """Сырая статистика конкретного (уже сыгранного) матча через /matches/get-statistics. {} если недоступно."""
    try:
        url = f"{SOFA_BASE}/matches/get-statistics"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.info("get_match_statistics(%s): статус %s", match_id, r.status_code)
            return {}
        return r.json()
    except Exception:
        logger.exception("Ошибка get_match_statistics(%s)", match_id)
        return {}


def get_average_match_stats(team_id: int, events: list, limit: int = 3) -> dict:
    """Средние показатели команды (владение, удары, угловые, фолы, голевые моменты)
    по последним `limit` матчам из уже загруженных events. {} если данных недостаточно."""
    accum = {name: [] for name in _MATCH_OVERVIEW_KEYS.values()}
    matched = False
    for m in events[:limit]:
        match_id = m.get("id")
        if not match_id:
            continue
        is_home = m.get("homeTeam", {}).get("id") == team_id
        stats = get_match_statistics(match_id)
        overview = []
        for period in stats.get("statistics", []):
            if period.get("period") != "ALL":
                continue
            for group in period.get("groups", []):
                if group.get("groupName") == "Match overview":
                    overview = group.get("statisticsItems", [])
                    break
            break
        if not overview:
            continue
        for item in overview:
            key = item.get("key")
            if key not in _MATCH_OVERVIEW_KEYS:
                continue
            value = item.get("homeValue") if is_home else item.get("awayValue")
            if value is not None:
                accum[_MATCH_OVERVIEW_KEYS[key]].append(value)
                matched = True
    if not matched:
        return {}
    return {name: sum(vals) / len(vals) for name, vals in accum.items() if vals}


def format_average_stats_text(stats: dict, team_name: str) -> str:
    """Текстовая строка со средними показателями команды по последним матчам. '' если нечего показать."""
    if not stats:
        return ""
    parts = []
    if "possession" in stats:
        parts.append(f"владение {stats['possession']:.0f}%")
    if "shots" in stats:
        parts.append(f"удары {stats['shots']:.1f}")
    if "shots_on_target" in stats:
        parts.append(f"в створ {stats['shots_on_target']:.1f}")
    if "corners" in stats:
        parts.append(f"угловые {stats['corners']:.1f}")
    if "fouls" in stats:
        parts.append(f"фолы {stats['fouls']:.1f}")
    if "big_chances" in stats:
        parts.append(f"голевые моменты {stats['big_chances']:.1f}")
    if not parts:
        return ""
    return f"  {team_name}: {', '.join(parts)}\n"


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
