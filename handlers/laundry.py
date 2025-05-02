from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from datetime import datetime
import logging

from database import (
    get_available_machines,
    get_available_laundry_slots,
    create_laundry_booking,
    get_user_laundry_bookings,
    cancel_laundry_booking,
    get_system_setting,
    check_user_daily_bookings
)
from utils import (
    is_valid_time,
    time_to_minutes,
    minutes_to_time,
    format_date
)
from states import LaundryStates

router = Router()

# Минимальное время бронирования (в часах)
LAUNDRY_MIN_BOOKING_HOURS = 2
logger = logging.getLogger(__name__)


@router.message(F.text == "Записаться в прачечную")
async def laundry_start(message: types.Message, state: FSMContext):
    """Начало процесса записи в прачечную"""
    available_machines = get_available_machines()
    if not available_machines:
        await message.reply("❌ В данный момент нет доступных машинок для записи.")
        return

    await state.set_state(LaundryStates.choosing_date)
    await message.reply("📅 На какую дату вы хотите записаться? (Формат: ДД.ММ.ГГГГ)")


@router.message(LaundryStates.choosing_date)
async def process_laundry_date(message: types.Message, state: FSMContext):
    """Обработка выбранной даты"""
    try:
        booking_date = datetime.strptime(message.text, '%d.%m.%Y').date()
        today = datetime.now().date()

        if booking_date < today:
            await message.reply("❌ Нельзя записаться на прошедшую дату. Введите корректную дату.")
            return

        available_machines = get_available_machines()
        if not available_machines:
            await state.clear()
            await message.reply("❌ Нет доступных машинок.")
            return

        # Сохраняем дату в FSM контексте
        await state.update_data(booking_date=booking_date.strftime('%Y-%m-%d'))

        # Создаем клавиатуру с доступными машинками
        builder = InlineKeyboardBuilder()
        for machine in available_machines:
            builder.button(
                text=f"Машинка №{machine}",
                callback_data=f"machine_{machine}"
            )
        builder.adjust(1)

        await state.set_state(LaundryStates.choosing_machine)
        await message.reply(
            "🌀 Выберите машинку:",
            reply_markup=builder.as_markup()
        )

    except ValueError:
        await message.reply("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")


@router.callback_query(F.data.startswith('machine_'), LaundryStates.choosing_machine)
async def process_laundry_machine(callback: types.CallbackQuery, state: FSMContext):
    machine_number = int(callback.data.split('_')[1])
    user_data = await state.get_data()
    booking_date = user_data['booking_date']
    date_obj = datetime.strptime(booking_date, '%Y-%m-%d').date()

    available_slots = get_available_laundry_slots(date_obj, machine_number)

    if not available_slots:
        await callback.message.edit_text(
            "❌ На выбранную дату нет свободных слотов для этой машинки.",
            reply_markup=None
        )
        await state.clear()
        return

    builder = ReplyKeyboardBuilder()
    for slot in available_slots:
        builder.add(types.KeyboardButton(text=slot))
    builder.adjust(2)  # 2 кнопки в ряд

    await state.update_data(machine_number=machine_number)
    await state.set_state(LaundryStates.choosing_time)
    await callback.message.answer(
        f"⏰ Выберите время начала для машинки №{machine_number} (слоты по 2 часа):",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
    )
    await callback.answer()
    builder = ReplyKeyboardBuilder()
    for slot in available_slots:
        builder.add(types.KeyboardButton(text=slot))
    builder.adjust(2)

    await callback.answer()


@router.message(LaundryStates.choosing_time)
async def process_laundry_time(message: types.Message, state: FSMContext):
    if not is_valid_time(message.text):
        await message.reply("❌ Неверный формат времени.")
        return

    user_data = await state.get_data()
    booking_date = user_data['booking_date']
    machine_number = user_data['machine_number']
    start_time = message.text
    date_obj = datetime.strptime(booking_date, '%Y-%m-%d').date()

    # Проверка доступности слота
    available_slots = get_available_laundry_slots(date_obj, machine_number)
    if start_time not in available_slots:
        await state.clear()
        await message.reply("❌ Это время уже занято.", reply_markup=types.ReplyKeyboardRemove())
        return

    # Проверка лимита записей (не более 2 в день)
    if not check_user_daily_bookings(message.from_user.id, booking_date):
        await state.clear()
        await message.reply(
            "❌ У вас уже 2 записи на этот день. Отмените одну из них для создания новой.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    # Создание записи (2 часа)
    end_time = minutes_to_time(time_to_minutes(start_time) + 120)

    if create_laundry_booking(
            user_id=message.from_user.id,
            machine_number=machine_number,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time
    ):
        await message.reply(
            f"✅ Вы успешно записаны на машинку №{machine_number}\n"
            f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {start_time}-{end_time}\n\n"
            f"ℹ️ Вы можете иметь до 2 активных записей в день.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.reply("❌ Ошибка при создании записи.", reply_markup=types.ReplyKeyboardRemove())

    await state.clear()

@router.callback_query(F.data == "cancel_laundry")
async def cancel_laundry(callback: types.CallbackQuery):
    """Обработка отмены записи в прачечную"""
    user_id = callback.from_user.id
    bookings = get_user_laundry_bookings(user_id)

    if not bookings:
        await callback.answer("У вас нет активных записей")
        return

    # Создаем клавиатуру с записями для отмены
    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"Машинка {booking['machine_number']} {booking['booking_date']} {booking['start_time']}",
            callback_data=f"cancel_laundry_{booking['id']}"
        )
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите запись для отмены:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_laundry_menu")
async def show_cancel_laundry_menu(callback: types.CallbackQuery):
    """Показывает меню отмены записей в прачечную"""
    user_id = callback.from_user.id
    bookings = get_user_laundry_bookings(user_id)

    if not bookings:
        await callback.answer("У вас нет активных записей", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"Машинка {booking['machine_number']} {booking['booking_date']} {booking['start_time']}",
            callback_data=f"cancel_laundry_{booking['id']}"
        )
    builder.button(text="↩️ Назад", callback_data="main_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите запись для отмены:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_laundry_"))
async def process_laundry_cancel(callback: types.CallbackQuery):
    """Обрабатывает отмену конкретной записи"""
    try:
        # Безопасное извлечение ID
        parts = callback.data.split('_')
        if len(parts) != 3:
            raise ValueError("Invalid callback data format")

        booking_id = int(parts[2])

        if cancel_laundry_booking(booking_id):
            await callback.message.edit_text(
                "✅ Запись успешно отменена",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось отменить запись",
                reply_markup=None
            )
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка отмены записи: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)
    finally:
        await callback.answer()


# Административные команды
@router.message(Command("laundry_status"))
async def show_laundry_status(message: types.Message):
    """Показывает статус всех машинок (только для админов)"""
    # Реализация аналогична оригинальному коду
    pass