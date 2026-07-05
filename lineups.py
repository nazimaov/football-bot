"""Стартовые составы команд + отсутствующие игроки, через RapidAPI (SofaScore)."""
import logging
import time

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_SQUAD_CACHE_TTL = 24 * 60 * 60
_squad_cache: dict[int, tuple[float, dict[int, float]]] = {}


def _get_squad_market_values(team_id: int) -> dict[int, float]:
    """Стоимость игроков состава команды (player_id -> рыночная стоимость), с кэшем на сутки."""
    cached = _squad_cache.get(team_id)
    if cached and time.time() - cached[0] < _SQUAD_CACHE_TTL:
        return cached[1]
    values: dict[int, float] = {}
    try:
        url = f"{SOFA_BASE}/teams/get-squad"
        params = {"teamId": str(team_id)}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.info("_get_squad_market_values(%s): статус %s", team_id, r.status_code)
            return {}
        for entry in r.json().get("players", []):
            pi = entry.get("player", entry)
            pid = pi.get("id")
            value = (pi.get("proposedMarketValueRaw") or {}).get("value")
            if pid is not None and value:
                values[pid] = value
    except Exception:
        logger.exception("Ошибка _get_squad_market_values(%s)", team_id)
        return {}
    _squad_cache[team_id] = (time.time(), values)
    return values


def _severity_tag(player_id, values: dict[int, float]) -> str:
    """Помечает потерю игрока по его месту в стоимости состава команды.
    Работает только для игроков, которых SofaScore уже включил в missingPlayers —
    если травма туда не попала, тег не появится, игрок просто не будет отмечен."""
    if not values or player_id not in values:
        return ""
    sorted_values = sorted(values.values(), reverse=True)
    value = values[player_id]
    top_cutoff = sorted_values[min(2, len(sorted_values) - 1)]
    if value >= top_cutoff:
        return " [КЛЮЧЕВОЙ ИГРОК]"
    median = sorted_values[len(sorted_values) // 2]
    if value >= median:
        return " [важный игрок]"
    return ""


def get_lineups(match_id: int, home_team_id: int | None = None, away_team_id: int | None = None) -> str:
    """Текстовый блок со стартовыми составами и списком отсутствующих игроков."""
    try:
        url = f"{SOFA_BASE}/matches/get-lineups"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.info("get_lineups(%s): составы недоступны (статус %s)", match_id, r.status_code)
            return "\n[!] Составы ещё не опубликованы\n"
        data = r.json()
        if data.get("confirmed") is False:
            return "\n[!] Составы ещё не подтверждены\n"
        home = data.get("home", {})
        away = data.get("away", {})
        if not home and not away:
            return "\n[!] Составы недоступны\n"
        result = "\n=== СТАРТОВЫЕ СОСТАВЫ ===\n"
        for team_data, label, team_id in [(home, "Хозяева", home_team_id), (away, "Гости", away_team_id)]:
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
                values = _get_squad_market_values(team_id) if team_id else {}
                result += f"  Травмы/диск.:\n"
                for mp in missing_list[:5]:
                    mname = mp.get("player", {}).get("name", "?")
                    mid = mp.get("player", {}).get("id")
                    reason = mp.get("type", "?")
                    tag = _severity_tag(mid, values)
                    result += f"    ✗ {mname} ({reason}){tag}\n"
        return result
    except Exception as e:
        logger.exception("Ошибка get_lineups(%s)", match_id)
        return f"\nОшибка составов: {e}\n"
