import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Union
from contextlib import closing
import logging

# Настройки прачечной
LAUNDRY_MIN_BOOKING_HOURS = 2  # Минимальное время бронирования
logger = logging.getLogger(__name__)


def get_db_connection():
    """Создает и возвращает соединение с базой данных"""
    conn = sqlite3.connect('dorm_bot.db', timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    return conn


def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username_hash TEXT,
                    is_admin INTEGER DEFAULT 0
                )
            ''')

            # Таблица записей в прачечную
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS laundry_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    machine_number INTEGER,
                    booking_date TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT DEFAULT 'active',
                    notified INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица статусов машинок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS laundry_machines (
                    machine_number INTEGER PRIMARY KEY,
                    status TEXT DEFAULT 'active'
                )
            ''')

            # Таблица записей в комнату отдыха
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS restroom_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    booking_date TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    status TEXT DEFAULT 'active',
                    notified INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица недельных лимитов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS restroom_limits (
                    user_id INTEGER NOT NULL,
                    week_number INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    used_minutes INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, week_number, year),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица настроек системы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedule_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_name TEXT UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    description TEXT
                )
            ''')

            # Таблица слотов комнаты отдыха
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS restroom_slots (
                    slot_time TEXT PRIMARY KEY,
                    is_available INTEGER DEFAULT 1
                )
            ''')

            # Инициализация машинок
            for machine in [1, 2, 3]:
                cursor.execute('''
                    INSERT OR IGNORE INTO laundry_machines (machine_number, status)
                    VALUES (?, ?)
                ''', (machine, 'active'))

            # Инициализация слотов комнаты отдыха
            for hour in range(8, 23):
                for minute in [0, 30]:
                    slot_time = f"{hour:02d}:{minute:02d}"
                    cursor.execute('''
                        INSERT OR IGNORE INTO restroom_slots (slot_time)
                        VALUES (?)
                    ''', (slot_time,))

            # Начальные настройки системы
            default_settings = [
                ('laundry_open', '08:00', 'Обычное время открытия'),
                ('laundry_close', '23:00', 'Обычное время закрытия'),
                ('laundry_break_start', None, 'Начало перерыва (обычные дни)'),
                ('laundry_break_end', None, 'Конец перерыва (обычные дни)'),
                ('wednesday_start', '08:00', 'Время открытия в среду'),
                ('wednesday_break_start', '10:00', 'Начало перерыва в среду'),
                ('wednesday_break_end', '13:00', 'Конец перерыва в среду')
            ]

            cursor.executemany('''
                INSERT OR IGNORE INTO schedule_settings 
                (setting_name, setting_value, description)
                VALUES (?, ?, ?)
            ''', default_settings)


def hash_username(username: str) -> str:
    """Хеширует имя пользователя для безопасного хранения"""
    return hashlib.sha256(username.encode()).hexdigest() if username else ''


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result and result[0] == 1 if result else False


def get_current_week() -> Tuple[int, int]:
    """Возвращает текущую неделю и год"""
    today = datetime.now()
    year, week, _ = today.isocalendar()
    return week, year


def get_laundry_schedule(date: datetime) -> Dict[str, str]:
    """Возвращает расписание прачечной с учетом дня недели и перерывов"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT setting_name, setting_value FROM schedule_settings')
            settings = {row[0]: row[1] for row in cursor.fetchall()}

    base_schedule = {
        'open': settings.get('laundry_open', '08:00'),
        'close': settings.get('laundry_close', '23:00'),
        'break_start': settings.get('laundry_break_start'),
        'break_end': settings.get('laundry_break_end')
    }

    # Особое расписание для среды
    if date.weekday() == 2:  # Среда
        wednesday_schedule = {
            'open': settings.get('wednesday_start', '08:00'),
            'close': base_schedule['close'],
            'break_start': settings.get('wednesday_break_start', '10:00'),
            'break_end': settings.get('wednesday_break_end', '13:00')
        }
        return wednesday_schedule

    return base_schedule


def update_schedule_settings(setting_name: str, value: str) -> bool:
    """Обновляет настройки расписания"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO schedule_settings (setting_name, setting_value)
                    VALUES (?, ?)
                    ON CONFLICT(setting_name) DO UPDATE SET setting_value = excluded.setting_value
                ''', (setting_name, value))
                return True
            except sqlite3.Error:
                return False


def check_user_daily_bookings(user_id: int, date: str) -> bool:
    """Проверяет, что у пользователя не более 2 записей в день"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM laundry_bookings 
                WHERE user_id = ? AND booking_date = ? AND status = 'active'
            ''', (user_id, date))
            count = cursor.fetchone()[0]
            return count < 2


def get_available_laundry_slots(date: datetime, machine_number: int) -> List[str]:
    """Возвращает доступные 2-часовые слоты с учетом расписания и перерывов"""
    schedule = get_laundry_schedule(date)
    open_time = time_to_minutes(schedule['open'])
    close_time = time_to_minutes(schedule['close'])
    break_start = time_to_minutes(schedule['break_start']) if schedule['break_start'] else None
    break_end = time_to_minutes(schedule['break_end']) if schedule['break_end'] else None

    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            date_str = date.strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT start_time FROM laundry_bookings 
                WHERE booking_date = ? AND status = 'active' AND machine_number = ?
            ''', (date_str, machine_number))
            booked_slots = [time_to_minutes(row[0]) for row in cursor.fetchall()]

    available_slots = []
    current_time = open_time

    while current_time + 120 <= close_time:  # 120 минут = 2 часа
        # Проверяем, что слот не в перерыве
        if not (break_start and break_end and break_start <= current_time < break_end):
            if current_time not in booked_slots:
                available_slots.append(minutes_to_time(current_time))
        current_time += 120  # Шаг 2 часа

    return available_slots


def get_available_machines() -> List[int]:
    """Возвращает список доступных машинок"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT machine_number FROM laundry_machines WHERE status = "active"')
            return [row[0] for row in cursor.fetchall()]


def create_laundry_booking(user_id: int, machine_number: int, booking_date: str, start_time: str,
                           end_time: str) -> bool:
    """Создает запись в прачечную"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO laundry_bookings 
                    (user_id, machine_number, booking_date, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, machine_number, booking_date, start_time, end_time))
                return True
            except sqlite3.Error:
                return False


def cancel_laundry_booking(booking_id: int) -> bool:
    """Отменяет запись в прачечную с проверкой"""
    with closing(get_db_connection()) as conn:
        with conn:
            try:
                cursor = conn.cursor()
                # Проверяем существование записи перед отменой
                cursor.execute('SELECT id FROM laundry_bookings WHERE id = ? AND status = "active"', (booking_id,))
                if not cursor.fetchone():
                    return False

                cursor.execute('UPDATE laundry_bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Ошибка отмены записи {booking_id}: {e}")
                return False


def get_available_restroom_slots(date: datetime) -> List[Dict[str, str]]:
    """Возвращает доступные слоты для комнаты отдыха"""
    date_str = date.strftime('%Y-%m-%d')
    available_slots = []

    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()

            # Получаем все занятые слоты на выбранную дату
            cursor.execute('''
                SELECT start_time, end_time 
                FROM restroom_bookings 
                WHERE booking_date = ? AND status = 'active'
                ORDER BY start_time
            ''', (date_str,))
            booked_slots = cursor.fetchall()

            # Проверяем базовые слоты (каждые 30 минут с 8:00 до 23:00)
            for hour in range(8, 23):
                for minute in [0, 30]:
                    slot_time = f"{hour:02d}:{minute:02d}"
                    slot_dt = datetime.strptime(slot_time, '%H:%M').time()
                    is_available = True

                    for booked_start, booked_end in booked_slots:
                        start_dt = datetime.strptime(booked_start, '%H:%M').time()
                        end_dt = datetime.strptime(booked_end, '%H:%M').time()

                        if start_dt <= slot_dt < end_dt:
                            is_available = False
                            break

                    if is_available:
                        available_slots.append({
                            'time': slot_time,
                            'display': slot_time
                        })

    return available_slots


def check_restroom_limit(user_id: int, duration: int) -> Tuple[bool, int]:
    """Проверяет недельный лимит для комнаты отдыха"""
    week, year = get_current_week()

    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT setting_value FROM schedule_settings 
                WHERE setting_name = 'restroom_max_weekly_minutes'
            ''')
            max_minutes = int(cursor.fetchone()[0])

            cursor.execute('''
                SELECT used_minutes FROM restroom_limits 
                WHERE user_id = ? AND week_number = ? AND year = ?
            ''', (user_id, week, year))
            result = cursor.fetchone()
            used_minutes = result[0] if result else 0

            remaining = max_minutes - used_minutes
            can_book = (used_minutes + duration) <= max_minutes

            return (can_book, remaining)


def create_restroom_booking(user_id: int, booking_date: str, start_time: str, end_time: str, duration: int) -> bool:
    """Создает запись в комнату отдыха"""
    week, year = get_current_week()

    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                # Создаем запись
                cursor.execute('''
                    INSERT INTO restroom_bookings 
                    (user_id, booking_date, start_time, end_time, duration)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, booking_date, start_time, end_time, duration))

                # Обновляем лимит
                cursor.execute('''
                    INSERT INTO restroom_limits 
                    (user_id, week_number, year, used_minutes)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, week_number, year) 
                    DO UPDATE SET used_minutes = used_minutes + ?
                ''', (user_id, week, year, duration, duration))

                return True
            except sqlite3.Error:
                return False


def cancel_restroom_booking(booking_id: int) -> bool:
    """Отменяет запись в комнату отдыха"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                # Получаем информацию о записи для обновления лимита
                cursor.execute('''
                    SELECT user_id, duration, booking_date 
                    FROM restroom_bookings 
                    WHERE id = ?
                ''', (booking_id,))
                booking = cursor.fetchone()

                if not booking:
                    return False

                user_id, duration, booking_date = booking
                booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
                week = booking_date.isocalendar()[1]
                year = booking_date.year

                # Отменяем запись
                cursor.execute('''
                    UPDATE restroom_bookings 
                    SET status = 'cancelled' 
                    WHERE id = ?
                ''', (booking_id,))

                # Обновляем лимит
                cursor.execute('''
                    UPDATE restroom_limits 
                    SET used_minutes = used_minutes - ? 
                    WHERE user_id = ? AND week_number = ? AND year = ?
                ''', (duration, user_id, week, year))

                return True
            except sqlite3.Error:
                return False


def get_system_setting(setting_name: str) -> Optional[str]:
    """Возвращает значение системной настройки"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT setting_value FROM schedule_settings 
                WHERE setting_name = ?
            ''', (setting_name,))
            result = cursor.fetchone()
            return result[0] if result else None


def update_machine_status(machine_number: int, status: str) -> bool:
    """Обновляет статус машинки"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE laundry_machines 
                    SET status = ? 
                    WHERE machine_number = ?
                ''', (status, machine_number))
                return cursor.rowcount > 0
            except sqlite3.Error:
                return False


def get_all_machines() -> List[Dict[str, Union[int, str]]]:
    """Возвращает список всех машинок с их статусами"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT machine_number, status FROM laundry_machines ORDER BY machine_number')
            return [{
                'machine_number': row[0],
                'status': row[1]
            } for row in cursor.fetchall()]


def get_active_bookings(booking_type: str) -> List[Dict[str, Union[int, str]]]:
    """Возвращает все активные записи указанного типа"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            if booking_type == 'laundry':
                cursor.execute('''
                    SELECT lb.id, u.username_hash, lb.machine_number, 
                           lb.booking_date, lb.start_time, lb.end_time
                    FROM laundry_bookings lb
                    JOIN users u ON lb.user_id = u.user_id
                    WHERE lb.status = 'active'
                    ORDER BY lb.booking_date, lb.start_time
                ''')
            else:  # restroom
                cursor.execute('''
                    SELECT rb.id, u.username_hash, rb.booking_date, 
                           rb.start_time, rb.end_time, rb.duration
                    FROM restroom_bookings rb
                    JOIN users u ON rb.user_id = u.user_id
                    WHERE rb.status = 'active'
                    ORDER BY rb.booking_date, rb.start_time
                ''')

            return [dict(zip(
                ['id', 'username_hash', 'machine_number' if booking_type == 'laundry' else 'duration',
                 'booking_date', 'start_time', 'end_time'],
                row
            )) for row in cursor.fetchall()]


# Вспомогательные функции для работы со временем
def time_to_minutes(time_str: str) -> int:
    """Конвертирует время в формате HH:MM в минуты"""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def minutes_to_time(minutes: int) -> str:
    """Конвертирует минуты во время формата HH:MM"""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def update_system_setting(setting_name: str, setting_value: str) -> bool:
    """
    Обновляет значение системной настройки в базе данных.

    Параметры:
        setting_name (str): Название настройки (например, 'laundry_notification_minutes')
        setting_value (str): Новое значение настройки

    Возвращает:
        bool: True если обновление прошло успешно, False в случае ошибки
    """
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE schedule_settings
                    SET setting_value = ?
                    WHERE setting_name = ?
                ''', (setting_value, setting_name))

                # Проверяем, была ли обновлена хотя бы одна строка
                if cursor.rowcount == 0:
                    # Если настройки не существует, создаем новую
                    cursor.execute('''
                        INSERT INTO schedule_settings 
                        (setting_name, setting_value, description)
                        VALUES (?, ?, ?)
                    ''', (setting_name, setting_value, 'Автоматически создано системой'))

                return True
            except sqlite3.Error as e:
                logger.error(f"Ошибка при обновлении настройки {setting_name}: {e}")
                return False


def get_all_settings() -> Dict[str, str]:
    """Возвращает все системные настройки в виде словаря"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT setting_name, setting_value FROM schedule_settings')
            return dict(cursor.fetchall())


def reset_settings_to_default() -> bool:
    """Сбрасывает все настройки к значениям по умолчанию"""
    default_settings = {
        'laundry_notification_minutes': '30',
        'restroom_notification_minutes': '15',
        'laundry_grace_period': '15',
        'restroom_max_weekly_minutes': '240'
    }

    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                for name, value in default_settings.items():
                    cursor.execute('''
                        UPDATE schedule_settings
                        SET setting_value = ?
                        WHERE setting_name = ?
                    ''', (value, name))
                return True
            except sqlite3.Error:
                return False

def create_or_update_user(user_id: int, username: str) -> bool:
    """Создает или обновляет пользователя в БД"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            username_hash = hash_username(username)
            cursor.execute(
                'INSERT OR IGNORE INTO users (user_id, username_hash) VALUES (?, ?)',
                (user_id, username_hash)
            )
            return True

def get_user_laundry_bookings(user_id: str) -> List[Dict]:
    """Возвращает активные записи в прачечную для пользователя"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, machine_number, booking_date, start_time, end_time
                FROM laundry_bookings
                WHERE user_id = ? AND status = 'active' AND booking_date >= date('now')
                ORDER BY booking_date, start_time
            ''', (user_id,))
            return [dict(zip(
                ['id', 'machine_number', 'booking_date', 'start_time', 'end_time'],
                row
            )) for row in cursor.fetchall()]

def get_user_restroom_bookings(user_id: str) -> List[Dict]:
    """Возвращает активные записи в комнату отдыха для пользователя"""
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, booking_date, start_time, end_time, duration
                FROM restroom_bookings
                WHERE user_id = ? AND status = 'active' AND booking_date >= date('now')
                ORDER BY booking_date, start_time
            ''', (user_id,))
            return [dict(zip(
                ['id', 'booking_date', 'start_time', 'end_time', 'duration'],
                row
            )) for row in cursor.fetchall()]