"""Турнирная мотивация команды на основе её положения в турнирной таблице."""


def get_motivation(row: dict, total_teams: int) -> str:
    """Возвращает текстовую оценку турнирной мотивации по строке standings.get_standings.
    '' если строка/таблица недоступна."""
    if not row or not total_teams:
        return ""
    position = row.get("position")
    if position is None:
        return ""
    zone = row.get("promotion", {}).get("text", "")
    if zone:
        return f"место {position}/{total_teams}, борьба за {zone}"
    if position <= 3:
        return f"место {position}/{total_teams}, борьба за чемпионство"
    if position > total_teams - 3:
        return f"место {position}/{total_teams}, борьба за выживание"
    return f"место {position}/{total_teams}, турнирная мотивация невысокая (середина таблицы)"
