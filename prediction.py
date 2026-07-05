"""Статистическая модель прогноза (распределение Пуассона) на основе среднего голов команд.

Считает вероятности исходов/тотала/ОЗ независимо от AI, чтобы финальные проценты
в ответе опирались на реальный расчёт, а не только на текстовое "мнение" модели.
"""
import math

LEAGUE_AVG_GOALS_FALLBACK = 2.6  # средний тотал футбольного матча, если нет данных по турниру
HOME_ADVANTAGE = 1.10
AWAY_DISADVANTAGE = 0.92
MAX_GOALS = 6  # диапазон суммирования распределения Пуассона (0..6 голов на команду)


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def estimate_expected_goals(home_stats: dict, away_stats: dict, league_avg: float | None) -> tuple | None:
    """Считает ожидаемые голы хозяев/гостей по их среднему голов за/против.
    None если по одной из команд нет статистики (compute_scoring_stats вернул {})."""
    if not home_stats or not away_stats:
        return None
    lam_home = (home_stats["avg_scored"] + away_stats["avg_conceded"]) / 2
    lam_away = (away_stats["avg_scored"] + home_stats["avg_conceded"]) / 2
    lam_home *= HOME_ADVANTAGE
    lam_away *= AWAY_DISADVANTAGE
    lam_home = max(lam_home, 0.1)
    lam_away = max(lam_away, 0.1)
    return lam_home, lam_away


def compute_probabilities(lam_home: float, lam_away: float) -> dict:
    """Вероятности П1/Х/П2, тотала Б/М 2.5 и обе забьют — по независимому распределению Пуассона."""
    home_win = draw = away_win = 0.0
    over25 = 0.0
    btts = 0.0
    for i in range(MAX_GOALS + 1):
        p_i = _poisson_pmf(i, lam_home)
        for j in range(MAX_GOALS + 1):
            p_j = _poisson_pmf(j, lam_away)
            p = p_i * p_j
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p
            if i + j > 2:
                over25 += p
            if i > 0 and j > 0:
                btts += p
    return {
        "home_win": home_win, "draw": draw, "away_win": away_win,
        "over25": over25, "under25": 1 - over25,
        "btts_yes": btts, "btts_no": 1 - btts,
        "expected_goals_home": lam_home, "expected_goals_away": lam_away,
    }


def format_prediction_text(probs: dict, home_name: str, away_name: str) -> str:
    """Текстовый блок с расчётными вероятностями — опорные цифры для AI. '' если расчёта нет."""
    if not probs:
        return ""
    text = "\n=== РАСЧЁТНАЯ МОДЕЛЬ (Пуассон, по среднему голов) ===\n"
    text += f"  Ожидаемые голы: {home_name} {probs['expected_goals_home']:.2f} | {away_name} {probs['expected_goals_away']:.2f}\n"
    text += f"  П1: {probs['home_win']*100:.0f}% | Х: {probs['draw']*100:.0f}% | П2: {probs['away_win']*100:.0f}%\n"
    text += f"  Тотал 2.5: Б {probs['over25']*100:.0f}% / М {probs['under25']*100:.0f}%\n"
    text += f"  Обе забьют: Да {probs['btts_yes']*100:.0f}% / Нет {probs['btts_no']*100:.0f}%\n"
    return text
