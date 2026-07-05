"""Стартовые составы команд + отсутствующие игроки, через RapidAPI (SofaScore)."""
import logging

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def get_lineups(match_id: int) -> str:
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
        logger.exception("Ошибка get_lineups(%s)", match_id)
        return f"\nОшибка составов: {e}\n"
