from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from database import init_db, hash_username, is_admin, create_or_update_user, get_user_laundry_bookings, get_user_restroom_bookings
from aiogram.utils.keyboard import InlineKeyboardBuilder
import datetime

router = Router()

@router.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    create_or_update_user(user_id, username)

    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Записаться в прачечную"),
        types.KeyboardButton(text="Записаться в комнату отдыха")
    )
    builder.row(types.KeyboardButton(text="Мои записи"))

    # Проверка прав через функцию is_admin
    if is_admin(user_id):
        builder.row(types.KeyboardButton(text="Администрирование"))

    await message.answer(
        "Привет! Я бот для записи в прачечную и комнату отдыха общежития №6 НГУ.\n"
        "Выберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


@router.message(F.text == "Мои записи")
async def show_my_bookings(message: types.Message):
    """Показывает активные записи пользователя"""
    user_id = message.from_user.id

    # Получаем записи через функции из database.py
    laundry = get_user_laundry_bookings(user_id)
    restroom = get_user_restroom_bookings(user_id)

    if not laundry and not restroom:
        await message.reply("У вас нет активных записей.")
        return

    response = "Ваши активные записи:\n\n"

    if laundry:
        response += "🏠 Прачечная:\n"
        for booking in laundry:
            response += (
                f"Машинка №{booking['machine_number']} "
                f"{booking['booking_date']} "
                f"{booking['start_time']}-{booking['end_time']}\n"
            )

    if restroom:
        response += "\n🛋️ Комната отдыха:\n"
        for booking in restroom:
            response += (
                f"{booking['booking_date']} "
                f"{booking['start_time']}-{booking['end_time']} "
                f"({booking['duration']} мин)\n"
            )

    # Создаем интерактивную клавиатуру
    builder = InlineKeyboardBuilder()
    if laundry:
        builder.button(text="Отменить запись в прачечную", callback_data="cancel_laundry_menu")
    if restroom:
        builder.button(text="Отменить запись в комнату отдыха", callback_data="cancel_restroom_menu")
    builder.adjust(1)

    await message.reply(response, reply_markup=builder.as_markup())


@router.callback_query(F.data == "main_menu")
async def return_to_main_menu(callback: types.CallbackQuery):
    """Обработчик кнопки 'Главное меню'"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Записаться в прачечную"),
        types.KeyboardButton(text="Записаться в комнату отдыха")
    )
    builder.row(types.KeyboardButton(text="Мои записи"))

    if is_admin(callback.from_user.id):
        builder.row(types.KeyboardButton(text="Администрирование"))

    await callback.message.answer(
        "Главное меню:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await callback.answer()


@router.callback_query(F.data == "my_bookings")
async def show_my_bookings_menu(callback: types.CallbackQuery):
    """Обновленное меню записей"""
    user_id = callback.from_user.id

    builder = InlineKeyboardBuilder()

    # Проверяем записи в прачечную
    laundry = get_user_laundry_bookings(user_id)
    if laundry:
        builder.button(
            text="Отменить запись в прачечную",
            callback_data="cancel_laundry_menu"
        )

    # Проверяем записи в комнату отдыха
    restroom = get_user_restroom_bookings(user_id)
    if restroom:
        builder.button(
            text="Отменить запись в комнату отдыха",
            callback_data="cancel_restroom_menu"
        )

    builder.button(text="↩️ Главное меню", callback_data="main_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()