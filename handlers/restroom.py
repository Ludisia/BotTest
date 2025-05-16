from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from datetime import datetime
from states import RestroomStates
from contextlib import closing
from datetime import datetime
from database import get_db_connection, get_current_week, is_admin

from database import (
    get_available_restroom_slots,
    create_restroom_booking,
    get_user_restroom_bookings,
    cancel_restroom_booking,
    check_restroom_limit,
    get_system_setting
)
from utils import (
    is_valid_time,
    time_to_minutes,
    minutes_to_time,
    format_date
)

router = Router()


@router.message(F.text == "Записаться в комнату отдыха")
async def restroom_start(message: types.Message, state: FSMContext):
    """Начало процесса записи в комнату отдыха"""
    await state.set_state(RestroomStates.choosing_date)
    await message.reply("📅 На какую дату вы хотите записаться? (Формат: ДД.ММ.ГГГГ)")


@router.message(RestroomStates.choosing_date)
async def process_restroom_date(message: types.Message, state: FSMContext):
    """Обработка выбранной даты"""
    try:
        booking_date = datetime.strptime(message.text, '%d.%m.%Y').date()
        today = datetime.now().date()

        if booking_date < today:
            await message.reply("❌ Нельзя записаться на прошедшую дату.")
            return

        available_slots = get_available_restroom_slots(booking_date)
        if not available_slots:
            await state.clear()
            await message.reply("❌ На выбранную дату нет свободных слотов.")
            return

        # Сохраняем дату и готовим клавиатуру со слотами
        await state.update_data(booking_date=booking_date.strftime('%Y-%m-%d'))

        builder = ReplyKeyboardBuilder()
        for slot in available_slots:
            builder.add(types.KeyboardButton(text=slot['display']))
        builder.adjust(2)

        await state.set_state(RestroomStates.choosing_start)
        await message.reply(
            "⏰ Выберите время начала:",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )

    except ValueError:
        await message.reply("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")


@router.message(RestroomStates.choosing_start)
async def process_restroom_start(message: types.Message, state: FSMContext):
    """Обработка выбранного времени начала"""
    if not is_valid_time(message.text.split('-')[0]):
        await message.reply("❌ Неверный формат времени.")
        return

    user_data = await state.get_data()
    booking_date = user_data['booking_date']
    start_time = message.text.split('-')[0]  # Извлекаем время из формата "HH:MM-HH:MM"

    # Проверяем доступность слота
    date_obj = datetime.strptime(booking_date, '%Y-%m-%d').date()
    available_slots = get_available_restroom_slots(date_obj)
    slot_available = any(slot['display'] == message.text for slot in available_slots)

    if not slot_available:
        await state.clear()
        await message.reply("❌ Это время уже занято.", reply_markup=types.ReplyKeyboardRemove())
        return

    await state.update_data(start_time=start_time)

    # Подготовка клавиатуры с вариантами продолжительности
    builder = ReplyKeyboardBuilder()
    durations = ["30 минут", "1 час", "1.5 часа", "2 часа"]
    for duration in durations:
        builder.add(types.KeyboardButton(text=duration))
    builder.adjust(2)

    await state.set_state(RestroomStates.choosing_duration)
    await message.reply(
        "⏳ Выберите продолжительность:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


@router.message(RestroomStates.choosing_duration)
async def process_restroom_duration(message: types.Message, state: FSMContext):
    """Обработка выбранной продолжительности"""
    duration_map = {
        "30 минут": 30,
        "1 час": 60,
        "1.5 часа": 90,
        "2 часа": 120
    }

    if message.text not in duration_map:
        await message.reply("❌ Выберите вариант из списка.")
        return

    duration = duration_map[message.text]
    user_data = await state.get_data()
    booking_date = user_data['booking_date']
    start_time = user_data['start_time']
    user_id = message.from_user.id

    # Проверка недельного лимита
    can_book, remaining = check_restroom_limit(user_id, duration)
    if not can_book:
        remaining_hours = remaining // 60
        remaining_minutes = remaining % 60
        await message.reply(
            f"❌ Превышен недельный лимит. Доступно: {remaining_hours}ч {remaining_minutes}мин.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.clear()
        return

    # Расчет времени окончания
    end_time = minutes_to_time(time_to_minutes(start_time) + duration)

    # Создание записи
    if create_restroom_booking(
            user_id=user_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            duration=duration
    ):
        # Получаем настройку уведомлений
        notify_minutes = get_system_setting('restroom_notification_minutes') or 15

        await message.reply(
            f"✅ Вы успешно записаны в комнату отдыха\n"
            f"📅 Дата: {format_date(datetime.strptime(booking_date, '%Y-%m-%d'))}\n"
            f"⏰ Время: {start_time}-{end_time}\n"
            f"⏳ Продолжительность: {duration} минут\n\n"
            f"ℹ️ Вы получите уведомление за {notify_minutes} минут до времени записи.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.reply(
            "❌ Произошла ошибка при создании записи. Попробуйте позже.",
            reply_markup=types.ReplyKeyboardRemove()
        )

    await state.clear()


@router.callback_query(F.data == "cancel_restroom")
async def cancel_restroom(callback: types.CallbackQuery):
    """Обработка отмены записи в комнату отдыха"""
    user_id = callback.from_user.id
    bookings = get_user_restroom_bookings(user_id)

    if not bookings:
        await callback.answer("У вас нет активных записей")
        return

    # Создаем клавиатуру с записями для отмены
    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"{booking['booking_date']} {booking['start_time']}-{booking['end_time']}",
            callback_data=f"cancel_restroom_{booking['id']}"
        )
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите запись для отмены:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_restroom_"))
async def process_restroom_cancel(callback: types.CallbackQuery):
    """Подтверждение отмены записи"""
    booking_id = int(callback.data.split('_')[2])

    if cancel_restroom_booking(booking_id):
        await callback.message.edit_text(
            "✅ Запись успешно отменена",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось отменить запись",
            reply_markup=None
        )

    await callback.answer()


@router.message(Command("restroom_stats"))
async def show_restroom_stats(message: types.Message):
    """Показывает статистику по комнате отдыха (только для админов)"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам")
        return

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()

        # Статистика за текущую неделю
        week, year = get_current_week()
        cursor.execute('''
            SELECT COUNT(*), SUM(duration) 
            FROM restroom_bookings 
            WHERE status = 'active' 
            AND strftime('%W', booking_date) = ? 
            AND strftime('%Y', booking_date) = ?
        ''', (str(week), str(year)))
        weekly_count, weekly_minutes = cursor.fetchone()
        weekly_minutes = weekly_minutes or 0

        # Статистика за текущий месяц
        cursor.execute('''
            SELECT COUNT(*), SUM(duration) 
            FROM restroom_bookings 
            WHERE status = 'active' 
            AND strftime('%m', booking_date) = strftime('%m', 'now') 
            AND strftime('%Y', booking_date) = strftime('%Y', 'now')
        ''')
        monthly_count, monthly_minutes = cursor.fetchone()
        monthly_minutes = monthly_minutes or 0

        # Самые активные пользователи
        cursor.execute('''
            SELECT user_id, COUNT(*) as bookings_count, SUM(duration) as total_minutes
            FROM restroom_bookings
            WHERE status = 'active'
            GROUP BY user_id
            ORDER BY bookings_count DESC
            LIMIT 5
        ''')
        top_users = cursor.fetchall()

    # Формируем ответ
    response = (
        "📊 Статистика комнаты отдыха:\n\n"
        f"📅 За текущую неделю:\n"
        f"• Количество записей: {weekly_count}\n"
        f"• Суммарное время: {weekly_minutes} мин. ({weekly_minutes // 60} ч. {weekly_minutes % 60} мин.)\n\n"
        f"📅 За текущий месяц:\n"
        f"• Количество записей: {monthly_count}\n"
        f"• Суммарное время: {monthly_minutes} мин. ({monthly_minutes // 60} ч. {monthly_minutes % 60} мин.)\n\n"
        "🏆 Топ пользователей:\n"
    )

    for i, (user_id, count, minutes) in enumerate(top_users, 1):
        response += (
            f"{i}. ID {user_id}: {count} записей, {minutes} мин.\n"
        )

    # Добавляем кнопку обновления статистики
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="refresh_restroom_stats")

    await message.answer(
        response,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "refresh_restroom_stats")
async def refresh_stats(callback: types.CallbackQuery):
    """Обновление статистики"""
    await show_restroom_stats(callback.message)
    await callback.answer("Статистика обновлена")