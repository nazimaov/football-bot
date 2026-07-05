"""Главный аналитический движок: собирает данные из всех источников и вызывает AI."""
import logging
import time
from datetime import datetime

import ai
import injuries
import lineups
import match_data
import motivation
import odds
import referee
import report
import standings
import statistics as team_statistics
import weather
from utils import split_teams, extract_venue_city

logger = logging.getLogger(__name__)


def _empty_result() -> dict:
    return {
        "match": {}, "home_team": {}, "away_team": {}, "standings": {},
        "statistics": {}, "lineups": {}, "injuries": {}, "referee": {},
        "weather": {}, "odds": {}, "motivation": {},
    }


def analyze_match(team1_name: str, team2_name: str) -> dict:
    """
    Собирает данные о матче из всех доступных источников и возвращает единый
    структурированный объект вместе с текстом для передачи в AI.
    Недоступность одного источника не останавливает остальной пайплайн —
    он помечается как "нет данных" и логируется.
    """
    result = _empty_result()

    team1 = match_data.search_team(team1_name)
    team2 = match_data.search_team(team2_name)
    result["home_team"] = team1
    result["away_team"] = team2

    info_text = "=== ДАННЫЕ МАТЧА ===\n"
    quality = {
        "team_stats": False, "h2h": False, "lineups": False, "referee": False,
        "weather": False, "standings": False, "match_stats": False,
    }
    match_id = None
    events1, events2 = [], []

    if team1.get("id"):
        events1 = team_statistics.fetch_last_matches(team1["id"])
        info_text += team_statistics.format_last_matches_text(events1, team1["id"], team1.get("name", team1_name))
        quality["team_stats"] = True
    else:
        logger.warning("Команда не найдена: %s", team1_name)
        info_text += f"\n[!] '{team1_name}' не найдена\n"

    if team2.get("id"):
        events2 = team_statistics.fetch_last_matches(team2["id"])
        info_text += team_statistics.format_last_matches_text(events2, team2["id"], team2.get("name", team2_name))
        quality["team_stats"] = True
    else:
        logger.warning("Команда не найдена: %s", team2_name)
        info_text += f"\n[!] '{team2_name}' не найдена\n"

    if team1.get("id") and team2.get("id"):
        avg1 = team_statistics.get_average_match_stats(team1["id"], events1, limit=3)
        avg2 = team_statistics.get_average_match_stats(team2["id"], events2, limit=3)
        avg1_text = team_statistics.format_average_stats_text(avg1, team1.get("name", team1_name))
        avg2_text = team_statistics.format_average_stats_text(avg2, team2.get("name", team2_name))
        if avg1_text or avg2_text:
            info_text += "\n=== СТАТИСТИКА ПО МАТЧАМ (среднее за 3 последних) ===\n" + avg1_text + avg2_text
            quality["match_stats"] = True
        match = match_data.get_next_match(team1["id"], team2["id"])
        if match:
            match_id = match.get("id")
            detail = match_data.get_match_detail(match_id) or {}

            ts = match.get("startTimestamp", 0)
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"

            stadium, city = extract_venue_city(match, detail)
            if not stadium:
                stadium = "?"

            result["match"] = {"id": match_id, "date": date, "stadium": stadium, "city": city}
            info_text += f"\n=== МАТЧ НАЙДЕН ===\nДата: {date} UTC\nСтадион: {stadium}\nГород: {city or '(не указан)'}\n"

            tournament_context = standings.get_tournament_context(detail)
            info_text += standings.format_tournament_text(tournament_context)

            if tournament_context["is_knockout"]:
                knockout_motivation = motivation.get_knockout_motivation(tournament_context.get("round_name"))
                info_text += f"\n=== МОТИВАЦИЯ ===\n  Обе команды: {knockout_motivation}\n"
                result["standings"] = {}
                result["motivation"] = {"team1": knockout_motivation, "team2": knockout_motivation}
            else:
                standings_rows = standings.get_standings(
                    tournament_context["tournament_id"], tournament_context["season_id"]
                )
                standings_text = standings.format_standings_text(
                    standings_rows, team1["id"], team2["id"],
                    team1.get("name", team1_name), team2.get("name", team2_name),
                )
                info_text += standings_text
                if standings_rows:
                    quality["standings"] = True

                row1 = standings.find_team_row(standings_rows, team1["id"])
                row2 = standings.find_team_row(standings_rows, team2["id"])
                total_teams = len(standings_rows)
                motivation1 = motivation.get_motivation(row1, total_teams)
                motivation2 = motivation.get_motivation(row2, total_teams)
                if motivation1 or motivation2:
                    info_text += "\n=== МОТИВАЦИЯ ===\n"
                    if motivation1:
                        info_text += f"  {team1.get('name', team1_name)}: {motivation1}\n"
                    if motivation2:
                        info_text += f"  {team2.get('name', team2_name)}: {motivation2}\n"

                result["standings"] = {"total_teams": total_teams, "team1_row": row1, "team2_row": row2}
                result["motivation"] = {"team1": motivation1, "team2": motivation2}

            h2h_text = team_statistics.get_h2h_text(match_id)
            info_text += h2h_text
            if "не найдено" not in h2h_text and "недоступно" not in h2h_text:
                quality["h2h"] = True
            result["statistics"] = {"h2h_text": h2h_text}

            ref_name, ref_text = referee.get_referee_text(match, detail)
            info_text += ref_text
            if ref_name:
                quality["referee"] = True
            result["referee"] = {"name": ref_name}

            lineups_text = lineups.get_lineups(match_id)
            info_text += lineups_text
            if "[!]" not in lineups_text:
                quality["lineups"] = True
            result["lineups"] = {"text": lineups_text}

            if city:
                weather_text = weather.get_weather(city)
                info_text += weather_text
                if weather_text and "[!]" not in weather_text:
                    quality["weather"] = True
                result["weather"] = {"city": city, "text": weather_text}
            else:
                info_text += "\n[!] Город не определён, погода пропущена\n"
        else:
            logger.info("Ближайший матч между '%s' и '%s' не найден", team1_name, team2_name)
            info_text += "\n[!] Ближайший матч не найден через get-next-matches\n"

    result["injuries"] = injuries.get_injuries(team1.get("id"), team2.get("id"))
    result["odds"] = odds.get_odds(match_id)

    quality_summary = (
        f"\n[Качество: форма={quality['team_stats']}, H2H={quality['h2h']}, "
        f"составы={quality['lineups']}, судья={quality['referee']}, погода={quality['weather']}, "
        f"таблица={quality['standings']}, статистика_матчей={quality['match_stats']}]"
    )

    return {"info_text": info_text, "quality_summary": quality_summary, "structured": result}


def run_analysis(match_name: str) -> str:
    """Точка входа: 'Команда1 vs Команда2' -> готовый текст ответа для Telegram."""
    team1_name, team2_name = split_teams(match_name)
    if not team2_name:
        return "Напиши две команды. Например: Реал Мадрид - Барселона"

    start_time = time.time()
    try:
        data = analyze_match(team1_name, team2_name)
    except Exception:
        logger.exception("Необработанная ошибка при сборе данных матча '%s'", match_name)
        return "Не получилось собрать данные по матчу. Попробуй ещё раз чуть позже."
    elapsed = time.time() - start_time
    logger.info("Сбор данных по '%s' занял %.1f сек", match_name, elapsed)

    ai_text = ai.ask_groq(match_name, data["info_text"], data["quality_summary"])
    return report.format_report(ai_text)
