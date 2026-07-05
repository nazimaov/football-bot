"""Поиск команд и идентификация матча через RapidAPI (SofaScore)."""
import logging

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def search_team(team_name: str) -> dict:
    """Ищет команду по названию. Возвращает {"id":.., "name":..} или {} если не найдена."""
    try:
        url = f"{SOFA_BASE}/search"
        params = {"q": team_name, "type": "teams", "page": "0"}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("search_team(%s): статус %s", team_name, r.status_code)
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
    except Exception:
        logger.exception("Ошибка search_team(%s)", team_name)
        return {}


def get_next_match(team_id: int, opponent_id: int) -> dict:
    """Находит ближайший запланированный матч между двумя командами."""
    try:
        url = f"{SOFA_BASE}/teams/get-next-matches"
        params = {"teamId": str(team_id), "page": "0"}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("get_next_match(%s): статус %s", team_id, r.status_code)
            return {}
        events = r.json().get("events", [])
        for m in events:
            home_id = m.get("homeTeam", {}).get("id")
            away_id = m.get("awayTeam", {}).get("id")
            if opponent_id in (home_id, away_id):
                return m
        return {}
    except Exception:
        logger.exception("Ошибка get_next_match(%s, %s)", team_id, opponent_id)
        return {}


def get_match_detail(match_id: int) -> dict:
    """Получает подробности матча (стадион, судья и т.п.), если API их отдаёт."""
    try:
        url = f"{SOFA_BASE}/matches/detail"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("get_match_detail(%s): статус %s", match_id, r.status_code)
            return {}
        return r.json().get("event", {})
    except Exception:
        logger.exception("Ошибка get_match_detail(%s)", match_id)
        return {}
