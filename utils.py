from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import re


def is_valid_date(date_str: str, date_format: str = '%d.%m.%Y') -> bool:
    """Проверяет, является ли строка корректной датой в указанном формате"""
    try:
        datetime.strptime(date_str, date_format)
        return True
    except ValueError:
        return False


def is_valid_time(time_str: str) -> bool:
    """Проверяет, является ли строка корректным временем в формате HH:MM"""
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        return False
    return True


def time_to_minutes(time_str: str) -> int:
    """Конвертирует время в минуты с проверкой формата"""
    try:
        h, m = map(int, time_str.split(':'))
        if m != 0:  # Разрешаем только часы (08:00, 10:00 и т.д.)
            raise ValueError
        return h * 60
    except (ValueError, AttributeError):
        raise ValueError("Допустимы только слоты по часам (например, 08:00, 10:00)")


def time_to_minutes(time_str: str) -> int:
    """Конвертирует время в формате HH:MM в минуты с начала дня"""
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except (ValueError, AttributeError):
        raise ValueError(f"Некорректный формат времени: {time_str}. Ожидается HH:MM")


def minutes_to_time(minutes: int) -> str:
    """Конвертирует минуты во время формата HH:MM"""
    if not isinstance(minutes, int) or minutes < 0 or minutes >= 1440:
        raise ValueError(f"Некорректное количество минут: {minutes}")
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def add_minutes_to_time(time_str: str, minutes: int) -> str:
    """Добавляет указанное количество минут к времени"""
    total_minutes = time_to_minutes(time_str) + minutes
    return minutes_to_time(total_minutes % 1440)  # Обрабатываем переход через полночь


def get_current_datetime() -> datetime:
    """Возвращает текущие дату и время"""
    return datetime.now()


def format_date(date_obj: datetime, date_format: str = '%d.%m.%Y') -> str:
    """Форматирует объект datetime в строку"""
    return date_obj.strftime(date_format)


def parse_date(date_str: str, date_format: str = '%d.%m.%Y') -> datetime:
    """Парсит строку с датой в объект datetime"""
    return datetime.strptime(date_str, date_format)


def get_weekday_name(date_obj: datetime) -> str:
    """Возвращает название дня недели на русском"""
    weekdays = ["Понедельник", "Вторник", "Среда",
                "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return weekdays[date_obj.weekday()]


def is_weekend(date_obj: datetime) -> bool:
    """Проверяет, является ли дата выходным днем"""
    return date_obj.weekday() >= 5  # 5 и 6 - суббота и воскресенье


def generate_time_slots(start_time: str, end_time: str, interval: int = 30) -> List[str]:
    """
    Генерирует список временных слотов между start_time и end_time
    с указанным интервалом в минутах
    """
    if not (is_valid_time(start_time) and is_valid_time(end_time)):
        raise ValueError("Некорректный формат времени")

    start = time_to_minutes(start_time)
    end = time_to_minutes(end_time)

    if start >= end:
        raise ValueError("Время начала должно быть раньше времени окончания")

    if interval <= 0:
        raise ValueError("Интервал должен быть положительным числом")

    return [minutes_to_time(t) for t in range(start, end, interval)]


def calculate_duration(start_time: str, end_time: str) -> int:
    """Вычисляет продолжительность между двумя временами в минутах"""
    return time_to_minutes(end_time) - time_to_minutes(start_time)


def is_time_between(time: str, start: str, end: str) -> bool:
    """Проверяет, находится ли время между start и end"""
    time_min = time_to_minutes(time)
    start_min = time_to_minutes(start)
    end_min = time_to_minutes(end)

    if start_min <= end_min:
        return start_min <= time_min < end_min
    else:  # Переход через полночь
        return time_min >= start_min or time_min < end_min


def get_nearest_available_time(time_slots: List[str], booked_slots: List[str]) -> Optional[str]:
    """
    Находит ближайшее доступное время, не входящее в список занятых слотов
    """
    for slot in time_slots:
        if slot not in booked_slots:
            return slot
    return None


def validate_booking_time(start_time: str, end_time: str, min_duration: int, max_duration: int) -> bool:
    """
    Проверяет, что временной интервал соответствует требованиям:
    - Длительность между min_duration и max_duration
    - Время корректное
    """
    if not (is_valid_time(start_time) and is_valid_time(end_time)):
        return False

    duration = calculate_duration(start_time, end_time)
    return min_duration <= duration <= max_duration


def split_duration(duration_minutes: int, max_chunk: int = 120) -> List[int]:
    """
    Разбивает длительность на части не больше max_chunk минут
    Например, 180 минут -> [120, 60]
    """
    chunks = []
    remaining = duration_minutes
    while remaining > 0:
        chunk = min(remaining, max_chunk)
        chunks.append(chunk)
        remaining -= chunk
    return chunks


def get_current_week() -> Tuple[int, int]:
    """Возвращает номер текущей недели и год"""
    today = datetime.now()
    year, week, _ = today.isocalendar()
    return week, year


def get_week_start_end(date_obj: datetime) -> Tuple[datetime, datetime]:
    """Возвращает даты начала и конца недели для указанной даты"""
    start = date_obj - timedelta(days=date_obj.weekday())
    end = start + timedelta(days=6)
    return start, end


def time_difference(time1: str, time2: str) -> int:
    """Возвращает разницу между двумя временами в минутах (time2 - time1)"""
    return time_to_minutes(time2) - time_to_minutes(time1)


def is_time_in_future(time_str: str, date_str: str) -> bool:
    """Проверяет, является ли время будущим относительно текущего момента"""
    try:
        booking_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return booking_dt > datetime.now()
    except ValueError:
        return False