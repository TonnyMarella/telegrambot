# Telegram Реферальний Бот

Бот для управління реферальною програмою та заявками на підбір турів.

## Встановлення

1. Створіть віртуальне середовище:
```bash
python -m venv .venv
source .venv/bin/activate  # для Linux/Mac
# або
.venv\Scripts\activate  # для Windows
```

2. Встановіть залежності:
```bash
pip install -r requirements.txt
```

3. Встановіть Redis:
```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# MacOS
brew install redis

# Windows
# Завантажте Redis з офіційного сайту
```

4. Створіть файл `.env` та додайте наступні змінні:
```
TELEGRAM_TOKEN=your_telegram_bot_token_here
ADMIN_USER_IDS=123456789,987654321  # ID адміністраторів через кому
```

## Запуск

1. Запустіть Redis сервер:
```bash
redis-server
```

2. Запустіть бота:
```bash
python bot.py
```

## Функціонал

### Для користувачів:
- Реєстрація через номер телефону
- Отримання реферального посилання
- Перегляд статистики та балансу
- Подача заявки на підбір туру

### Для адміністраторів:
- Управління користувачами
- Нарахування бонусів
- Обробка заявок на підбір турів

## Структура бази даних

- `users` - інформація про користувачів
- `referral_bonuses` - історія нарахування бонусів
- `tour_requests` - заявки на підбір турів 