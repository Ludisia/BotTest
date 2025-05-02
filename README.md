# Telegram Bot для записи в прачечную и комнату отдыха общежития №6 НГУ

Этот бот позволяет студентам общежития №6 НГУ записываться в прачечную и комнату отдыха, управлять своими записями и получать уведомления.

## Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/yourusername/dorm-bot.git
   cd dorm-bot
   
2. Установите зависимости:
    ```bash
   pip install -r requirements.txt
   
3. Создайте файл .env и добавьте токен вашего бота:
    ```bash
   TELEGRAM_BOT_TOKEN=ваш_токен_бота
   
4. Запустите бота:
    ```bash
   python main.py
   
## Настройка администратора

1. Подключитесь к базе данных:
   ```bash
   sqlite3 dorm_bot.db
   
2. Назначьте пользователя администратором:
    ```sql
   UPDATE users SET is_admin = 1 WHERE user_id = ID_ВАШЕГО_ТЕЛЕГРАМ_АККАУНТА;
   
3. Выйдите из SQLite:
    ```sql
   .quit