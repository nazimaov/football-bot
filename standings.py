"""Турнирные таблицы через RapidAPI (SofaScore): /tournaments/get-standings."""
import logging

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def get_standings(tournament_id: int | None, season_id: int | None) -> list:
    """Возвращает список строк турнирной таблицы (rows). [] если недоступно."""
    if not tournament_id or not season_id:
        return []
    try:
        url = f"{SOFA_BASE}/tournaments/get-standings"
        params = {"tournamentId": str(tournament_id), "seasonId": str(season_id), "type": "total"}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("get_standings(%s, %s): статус %s", tournament_id, season_id, r.status_code)
            return []
        standings = r.json().get("standings", [])
        if not standings:
            return []
        return standings[0].get("rows", [])
    except Exception:
        logger.exception("Ошибка get_standings(%s, %s)", tournament_id, season_id)
        return []


def get_tournament_context(detail: dict) -> dict:
    """Извлекает из match_data.get_match_detail() контекст турнира: название, сезон,
    стадия/тур и признак плей-офф (там нет турнирной таблицы по определению)."""
    tournament = detail.get("tournament") or {}
    unique_tournament = tournament.get("uniqueTournament") or {}
    season = detail.get("season") or {}
    round_info = detail.get("roundInfo") or {}
    is_knockout = tournament.get("competitionType") == 2 or bool(round_info.get("cupRoundType"))
    return {
        "tournament_id": unique_tournament.get("id"),
        "season_id": season.get("id"),
        "name": unique_tournament.get("name") or tournament.get("name") or "",
        "season_name": season.get("name") or "",
        "round_name": round_info.get("name") or "",
        "round_number": round_info.get("round"),
        "is_knockout": is_knockout,
    }


def format_tournament_text(context: dict) -> str:
    """Текстовый блок с названием турнира, сезоном и стадией (тур/плей-офф)."""
    if not context.get("name"):
        return ""
    text = f"\n=== ТУРНИР ===\n  {context['name']}"
    if context.get("season_name"):
        text += f" ({context['season_name']})"
    if context.get("round_name"):
        stage = "плей-офф" if context.get("is_knockout") else "тур"
        text += f", {context['round_name']} [{stage}]"
    elif context.get("round_number"):
        text += f", тур {context['round_number']}"
    text += "\n"
    return text


def get_tournament_goal_average(rows: list) -> float | None:
    """Средний тотал голов за матч по всему турниру, на основе уже загруженной таблицы.
    None если посчитать не из чего (нет данных о голах/матчах)."""
    if not rows:
        return None
    total_goals = sum(row.get("scoresFor", 0) or 0 for row in rows)
    total_team_matches = sum(row.get("matches", 0) or 0 for row in rows)
    if not total_team_matches:
        return None
    total_matches = total_team_matches / 2
    if not total_matches:
        return None
    return total_goals / total_matches


def find_team_row(rows: list, team_id: int | None) -> dict:
    """Находит строку конкретной команды в турнирной таблице. {} если не найдена."""
    for row in rows:
        if row.get("team", {}).get("id") == team_id:
            return row
    return {}


def format_standings_text(rows: list, team1_id: int | None, team2_id: int | None,
                           team1_name: str, team2_name: str) -> str:
    """Текстовый блок турнирной таблицы для обеих команд матча."""
    if not rows:
        return "\n[!] Турнирная таблица недоступна\n"
    total = len(rows)
    leader_points = rows[0].get("points") if rows else None
    text = "\n=== ТУРНИРНАЯ ТАБЛИЦА ===\n"
    for team_id, team_name in [(team1_id, team1_name), (team2_id, team2_name)]:
        row = find_team_row(rows, team_id)
        if not row:
            text += f"  {team_name}: нет в этой турнирной таблице\n"
            continue
        pos = row.get("position")
        pts = row.get("points")
        w, d, l = row.get("wins"), row.get("draws"), row.get("losses")
        gf, ga = row.get("scoresFor"), row.get("scoresAgainst")
        gap = (leader_points - pts) if (leader_points is not None and pts is not None) else None
        zone = row.get("promotion", {}).get("text", "")
        text += f"  {team_name}: {pos}/{total} место, {pts} очков ({w}В {d}Н {l}П, {gf}:{ga})"
        if gap is not None:
            text += f", отставание от лидера: {gap}"
        if zone:
            text += f" [{zone}]"
        text += "\n"
    avg_goals = get_tournament_goal_average(rows)
    if avg_goals is not None:
        text += f"  Средний тотал по турниру: {avg_goals:.2f} гола за матч\n"
    return text
