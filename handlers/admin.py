from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from datetime import datetime

from database import (
    get_all_machines,
    update_machine_status,
    get_active_bookings,
    get_system_setting,
    update_system_setting,
    is_admin,
    update_schedule_settings
)
from utils import is_valid_time, format_date

router = Router()

# Проверка прав администратора для всех обработчиков
router.message.filter(F.from_user.id.is_(lambda x: is_admin(x)))
router.callback_query.filter(F.from_user.id.is_(lambda x: is_admin(x)))


@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Главное меню администратора"""
    builder = ReplyKeyboardBuilder()
    buttons = [
        "Управление машинками",
        "Просмотр записей",
        "Настройки уведомлений",
        "Статистика",
        "Главное меню"
    ]
    for button in buttons:
        builder.add(types.KeyboardButton(text=button))
    builder.adjust(2)

    await message.reply(
        "⚙️ Панель администратора:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


@router.message(F.text == "Управление машинками")
async def manage_machines(message: types.Message):
    """Управление статусом машинок"""
    machines = get_all_machines()

    builder = InlineKeyboardBuilder()
    for machine in machines:
        status_icon = "✅" if machine['status'] == 'active' else "❌"
        builder.button(
            text=f"Машинка {machine['machine_number']} {status_icon}",
            callback_data=f"toggle_machine_{machine['machine_number']}"
        )
    builder.adjust(1)

    await message.reply(
        "Текущий статус машинок:\n"
        "✅ - доступна\n"
        "❌ - не доступна\n"
        "Выберите машинку для изменения статуса:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("toggle_machine_"))
async def toggle_machine_status(callback: types.CallbackQuery):
    """Переключение статуса машинки"""
    machine_number = int(callback.data.split('_')[2])
    current_status = next(
        (m['status'] for m in get_all_machines()
         if m['machine_number'] == machine_number),
        'active'
    )
    new_status = 'inactive' if current_status == 'active' else 'active'

    if update_machine_status(machine_number, new_status):
        await callback.answer(f"Статус машинки {machine_number} изменен")
        await manage_machines(callback.message)
    else:
        await callback.answer("❌ Ошибка изменения статуса")


@router.message(F.text == "Просмотр записей")
async def view_bookings_menu(message: types.Message):
    """Меню просмотра записей"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Прачечная", callback_data="view_bookings_laundry")
    builder.button(text="Комната отдыха", callback_data="view_bookings_restroom")
    await message.reply(
        "Выберите тип записей для просмотра:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("view_bookings_"))
async def view_bookings(callback: types.CallbackQuery):
    """Просмотр активных записей"""
    booking_type = callback.data.split('_')[2]  # laundry или restroom
    bookings = get_active_bookings(booking_type)

    response = (
        "📋 Активные записи в прачечную:\n\n" if booking_type == 'laundry' else
        "📋 Активные записи в комнату отдыха:\n\n"
    )

    for booking in bookings:
        if booking_type == 'laundry':
            response += (
                f"🔹 Машинка №{booking['machine_number']}\n"
                f"📅 {booking['booking_date']} {booking['start_time']}-{booking['end_time']}\n"
                f"👤 Пользователь: {booking['username_hash'][:8]}...\n\n"
            )
        else:
            response += (
                f"🔹 {booking['booking_date']} {booking['start_time']}-{booking['end_time']}\n"
                f"⏳ {booking['duration']} минут\n"
                f"👤 Пользователь: {booking['username_hash'][:8]}...\n\n"
            )

    if not bookings:
        response = "Нет активных записей"

    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="admin_back")
    await callback.message.edit_text(
        response,
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.message(F.text == "Настройки уведомлений")
async def notification_settings(message: types.Message, state: FSMContext):
    """Меню настроек уведомлений"""
    settings = {
        'laundry_notification_minutes': "Уведомление перед стиркой (мин)",
        'restroom_notification_minutes': "Уведомление перед комнатой отдыха (мин)",
        'laundry_grace_period': "Грейс-период прачечной (мин)"
    }

    builder = InlineKeyboardBuilder()
    for setting, description in settings.items():
        value = get_system_setting(setting) or "30"
        builder.button(
            text=f"{description}: {value}",
            callback_data=f"edit_setting_{setting}"
        )
    builder.adjust(1)

    await message.reply(
        "⚙️ Текущие настройки уведомлений:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("edit_setting_"))
async def edit_setting(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование настройки"""
    setting_name = callback.data.split('_')[2]
    current_value = get_system_setting(setting_name) or "30"

    await state.update_data(editing_setting=setting_name)
    await callback.message.answer(
        f"Введите новое значение для '{setting_name}' (текущее: {current_value}):"
    )
    await callback.answer()


@router.message(F.text.regexp(r'^\d+$'))
async def save_setting(message: types.Message, state: FSMContext):
    """Сохранение новой настройки"""
    user_data = await state.get_data()
    if 'editing_setting' not in user_data:
        return

    setting_name = user_data['editing_setting']
    new_value = message.text

    if update_system_setting(setting_name, new_value):
        await message.reply(f"✅ Настройка '{setting_name}' обновлена: {new_value}")
    else:
        await message.reply("❌ Ошибка при сохранении настройки")

    await state.clear()


@router.message(F.text == "Статистика")
async def show_stats(message: types.Message):
    """Показать статистику использования"""
    # Здесь можно реализовать сбор и отображение статистики
    await message.reply("📊 Статистика будет доступна в следующих версиях")


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    """Возврат в главное меню администратора"""
    await admin_panel(callback.message)
    await callback.answer()


@router.message(F.text == "Настройки расписания")
async def schedule_settings_menu(message: types.Message):
    """Меню настроек расписания"""
    builder = InlineKeyboardBuilder()
    buttons = [
        ("Обычное время открытия", "set_open_time"),
        ("Обычное время закрытия", "set_close_time"),
        ("Перерыв (начало)", "set_break_start"),
        ("Перерыв (конец)", "set_break_end"),
        ("Среда: время открытия", "set_wednesday_start"),
        ("Среда: перерыв (начало)", "set_wednesday_break_start"),
        ("Среда: перерыв (конец)", "set_wednesday_break_end"),
        ("Сброс настроек", "reset_schedule_settings")
    ]

    for text, callback in buttons:
        builder.button(text=text, callback_data=callback)
    builder.adjust(1)

    await message.answer("⚙️ Настройки расписания прачечной:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("set_"))
async def ask_for_new_time(callback: types.CallbackQuery, state: FSMContext):
    """Запрос нового значения для настройки"""
    setting_map = {
        'set_open_time': 'laundry_open',
        'set_close_time': 'laundry_close',
        'set_break_start': 'laundry_break_start',
        'set_break_end': 'laundry_break_end',
        'set_wednesday_start': 'wednesday_start',
        'set_wednesday_break_start': 'wednesday_break_start',
        'set_wednesday_break_end': 'wednesday_break_end'
    }

    setting_name = setting_map[callback.data]
    await state.update_data(editing_setting=setting_name)
    await callback.message.answer(f"Введите новое время для {setting_name} (формат HH:MM):")
    await callback.answer()


@router.message(F.text.regexp(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'))
async def save_schedule_setting(message: types.Message, state: FSMContext):
    """Сохранение новой настройки расписания"""
    user_data = await state.get_data()
    if 'editing_setting' not in user_data:
        return

    setting_name = user_data['editing_setting']
    time_value = message.text

    if update_schedule_settings(setting_name, time_value):
        await message.reply(f"✅ Настройка '{setting_name}' обновлена: {time_value}")
    else:
        await message.reply("❌ Ошибка при сохранении настройки")

    await state.clear()


@router.callback_query(F.data == "reset_schedule_settings")
async def reset_schedule_settings(callback: types.CallbackQuery):
    """Сброс настроек расписания к значениям по умолчанию"""
    default_settings = {
        'laundry_open': '08:00',
        'laundry_close': '23:00',
        'laundry_break_start': None,
        'laundry_break_end': None,
        'wednesday_start': '08:00',
        'wednesday_break_start': '10:00',
        'wednesday_break_end': '13:00'
    }

    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            try:
                for name, value in default_settings.items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO schedule_settings 
                        (setting_name, setting_value) VALUES (?, ?)
                    ''', (name, value))
                await callback.answer("✅ Настройки сброшены к значениям по умолчанию")
            except sqlite3.Error:
                await callback.answer("❌ Ошибка при сбросе настроек")

    await callback.message.edit_reply_markup()