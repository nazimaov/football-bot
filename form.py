"""Анализ формы: серии, домашняя/гостевая форма, игра против сильных/слабых соперников.

Использует уже загруженные последние матчи команды (statistics.fetch_last_matches) —
без новых запросов к API. Сила соперника определяется по полю "class" (клубы)
или "ranking" (сборные), которые уже приходят вместе с данными о матче.
"""
import logging

logger = logging.getLogger(__name__)

STRONG_CLASS_THRESHOLD = 3
WEAK_CLASS_THRESHOLD = 1
STRONG_RANKING_THRESHOLD = 20
WEAK_RANKING_THRESHOLD = 50

_RESULT_LABELS = {"W": "побед", "D": "ничьих", "L": "поражений"}


def _match_result(m: dict, team_id: int):
    """(scored, conceded, is_home, opponent) или None если матч не завершён."""
    home = m.get("homeTeam", {})
    away = m.get("awayTeam", {})
    hs = m.get("homeScore", {}).get("current")
    as_ = m.get("awayScore", {}).get("current")
    if hs is None or as_ is None:
        return None
    is_home = home.get("id") == team_id
    scored, conceded = (hs, as_) if is_home else (as_, hs)
    opponent = away if is_home else home
    return scored, conceded, is_home, opponent


def _opponent_strength(opponent: dict) -> str:
    """'strong' / 'weak' / 'mid' по рейтингу сборной или классу клуба."""
    if opponent.get("national"):
        ranking = opponent.get("ranking")
        if ranking is None:
            return "mid"
        if ranking <= STRONG_RANKING_THRESHOLD:
            return "strong"
        if ranking > WEAK_RANKING_THRESHOLD:
            return "weak"
        return "mid"
    team_class = opponent.get("class")
    if team_class is None:
        return "mid"
    if team_class >= STRONG_CLASS_THRESHOLD:
        return "strong"
    if team_class <= WEAK_CLASS_THRESHOLD:
        return "weak"
    return "mid"


def analyze_form(events: list, team_id: int) -> dict:
    """Разбирает events на домашнюю/гостевую форму, текущую серию и результаты
    против сильных/слабых соперников. {} если нет завершённых матчей.
    events должны быть отсортированы от самого свежего к самому старому (как отдаёт API)."""
    home_wdl = [0, 0, 0]
    away_wdl = [0, 0, 0]
    strong_wdl = [0, 0, 0]
    weak_wdl = [0, 0, 0]
    streak_type = None
    streak_len = 0
    streak_broken = False

    for m in events:
        parsed = _match_result(m, team_id)
        if not parsed:
            continue
        scored, conceded, is_home, opponent = parsed
        if scored > conceded:
            result, idx = "W", 0
        elif scored == conceded:
            result, idx = "D", 1
        else:
            result, idx = "L", 2

        (home_wdl if is_home else away_wdl)[idx] += 1

        strength = _opponent_strength(opponent)
        if strength == "strong":
            strong_wdl[idx] += 1
        elif strength == "weak":
            weak_wdl[idx] += 1

        if not streak_broken:
            if streak_type is None:
                streak_type, streak_len = result, 1
            elif result == streak_type:
                streak_len += 1
            else:
                streak_broken = True

    if sum(home_wdl) + sum(away_wdl) == 0:
        return {}

    return {
        "home": {"wins": home_wdl[0], "draws": home_wdl[1], "losses": home_wdl[2]},
        "away": {"wins": away_wdl[0], "draws": away_wdl[1], "losses": away_wdl[2]},
        "vs_strong": {"wins": strong_wdl[0], "draws": strong_wdl[1], "losses": strong_wdl[2]},
        "vs_weak": {"wins": weak_wdl[0], "draws": weak_wdl[1], "losses": weak_wdl[2]},
        "streak_type": streak_type,
        "streak_len": streak_len,
    }


def format_form_text(form: dict, team_name: str) -> str:
    """Текстовый блок с деталями формы команды. '' если данных нет."""
    if not form:
        return ""
    h, a = form["home"], form["away"]
    s, w = form["vs_strong"], form["vs_weak"]
    text = f"  {team_name}:\n"
    text += f"    Дома: {h['wins']}В {h['draws']}Н {h['losses']}П | В гостях: {a['wins']}В {a['draws']}Н {a['losses']}П\n"
    if sum(s.values()) > 0:
        text += f"    Против сильных соперников: {s['wins']}В {s['draws']}Н {s['losses']}П\n"
    if sum(w.values()) > 0:
        text += f"    Против слабых соперников: {w['wins']}В {w['draws']}Н {w['losses']}П\n"
    if form["streak_len"] > 1:
        label = _RESULT_LABELS.get(form["streak_type"], "")
        text += f"    Серия: {form['streak_len']} {label} подряд\n"
    return text
