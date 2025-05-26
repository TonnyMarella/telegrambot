import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import redis

from modules.models import Session, User, TourRequest
from modules.user_handlers import (
    start, handle_phone, show_statistics,
    request_tour, handle_tour_request
)
from modules.admin_handlers import (
    admin_panel, show_users, add_bonus,
    handle_bonus_amount, show_tour_requests,
    set_admin, remove_admin
)

# Завантаження змінних середовища
load_dotenv()

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Підключення до Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)


async def check_user_authorization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перевірка авторизації користувача"""
    user_id = update.effective_user.id
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        return user


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник текстових повідомлень"""
    # Перевіряємо чи очікуємо введення суми бонусу
    if context.user_data.get('waiting_for_bonus_amount'):
        await handle_bonus_amount(update, context)
        return

    # Перевіряємо авторизацію користувача
    user = await check_user_authorization(update, context)

    if not user:
        # Користувач не авторизований - показуємо меню авторизації
        await start(update, context)
        return

    text = update.message.text

    # Якщо користувач є адміністратором
    if user.is_admin:
        await handle_admin_text(update, context, text, user)
    else:
        await handle_user_text(update, context, text, user)


async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user):
    """Обробка текстових повідомлень для звичайних користувачів"""
    if text == "📊 Моя статистика":
        await show_statistics(update, context)
    elif text == "🏖 Підбір туру":
        await request_tour(update, context)
    elif text == "ℹ Про програму":
        await update.message.reply_text(
            "🎁 РЕФЕРАЛЬНА ПРОГРАМА\n\n"
            "Запрошуйте друзів та отримуйте бонуси:\n"
            "├── Запросив друга = +100 грн\n"
            "├── Друг запросив когось = +50 грн вам\n"
            "└── Третій рівень = +25 грн вам"
        )
    elif text == "📞 Контакти":
        await update.message.reply_text(
            "📞 Наші контакти:\n\n"
            "🌐 Сайт: your-site.com\n"
            "📱 Instagram: @your_instagram\n"
            "📱 Facebook: @your_facebook"
        )
    elif text == "🔗 Моє посилання":
        await update.message.reply_text(
            f"🔗 Ваше реферальне посилання:\n"
            f"t.me/MyNewArtembot?start={user.referral_code}"
        )
    elif text == "🛠 Адмін панель":
        # Перевіряємо чи користувач адмін
        with Session() as session:
            current_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
            if current_user and current_user.is_admin:
                await admin_panel(update, context)
            else:
                await update.message.reply_text("❌ У вас немає доступу до адмін-панелі!")
    elif context.user_data.get('waiting_for_tour_request'):
        await handle_tour_request(update, context)
    else:
        await update.message.reply_text("Будь ласка, використовуйте кнопки меню")


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user):
    """Обробка текстових повідомлень для адміністраторів"""
    if text == "👥 Користувачі":
        await show_users_list(update, context)
    elif text == "📋 Заявки на тури":
        await show_tour_requests_list(update, context)
    elif text == "💰 Додати бонус":
        await show_users_for_bonus(update, context)
    elif text == "📊 Статистика системи":
        with Session() as session:
            total_users = session.query(User).count()
            active_users = session.query(User).filter(User.balance > 0).count()
            total_balance = session.query(User).with_entities(User.balance).all()
            total_balance_sum = sum([b[0] for b in total_balance if b[0]])

            await update.message.reply_text(
                f"📊 СТАТИСТИКА СИСТЕМИ\n\n"
                f"👥 Всього користувачів: {total_users}\n"
                f"💰 Активних користувачів: {active_users}\n"
                f"💵 Загальний баланс: {total_balance_sum} грн"
            )
    elif text == "👤 Режим користувача":
        # Перемикання в режим користувача
        keyboard = [
            [KeyboardButton("📊 Моя статистика")],
            [KeyboardButton("🔗 Моє посилання")],
            [KeyboardButton("🏖 Підбір туру")],
            [KeyboardButton("ℹ Про програму")],
            [KeyboardButton("📞 Контакти")],
            [KeyboardButton("🛠 Адмін панель")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "Перемкнено в режим користувача",
            reply_markup=reply_markup
        )
    elif text == "🛠 Адмін панель":
        await show_admin_menu(update, context)
    else:
        # Якщо команда не розпізнана в адмін режимі, обробляємо як користувача
        await handle_user_text(update, context, text, user)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start з перевіркою авторизації"""
    user = await check_user_authorization(update, context)

    if user:
        # Користувач вже авторизований - показуємо відповідне меню
        keyboard = [
            [KeyboardButton("📊 Моя статистика")],
            [KeyboardButton("🔗 Моє посилання")],
            [KeyboardButton("🏖 Підбір туру")],
            [KeyboardButton("ℹ Про програму")],
            [KeyboardButton("📞 Контакти")],
            [KeyboardButton("🛠 Адмін панель")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"Вітаю! Ви вже авторизовані в системі ✅",
            reply_markup=reply_markup
        )
    else:
        # Користувач не авторизований - запитуємо номер телефону
        await start(update, context)


async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ адмінського меню"""
    keyboard = [
        [KeyboardButton("👥 Користувачі"), KeyboardButton("📋 Заявки на тури")],
        [KeyboardButton("💰 Додати бонус"), KeyboardButton("📊 Статистика системи")],
        [KeyboardButton("👤 Режим користувача")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🛠 АДМІН ПАНЕЛЬ\n\nВиберіть потрібний розділ:",
        reply_markup=reply_markup
    )


async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ списку користувачів для адміна"""
    with Session() as session:
        users = session.query(User).limit(10).all()  # Показуємо перших 10 користувачів

        if users:
            text = "👥 СПИСОК КОРИСТУВАЧІВ:\n\n"
            for user in users:
                admin_mark = " 👑" if user.is_admin else ""
                text += (
                    f"ID: {user.id}{admin_mark}\n"
                    f"📱 {user.phone_number}\n"
                    f"💰 Баланс: {user.balance} грн\n"
                    f"🔗 Код: {user.referral_code}\n"
                    f"📅 {user.created_at.strftime('%d.%m.%Y')}\n"
                    "─────────────────\n"
                )

            keyboard = [[InlineKeyboardButton("💰 Додати бонус користувачу", callback_data='select_user_bonus')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text("Користувачів не знайдено")


async def show_tour_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заявок на тури для адміна"""
    with Session() as session:
        requests = session.query(TourRequest).filter_by(status='new').limit(10).all()

        if requests:
            text = "🏖 НОВІ ЗАЯВКИ НА ТУРИ:\n\n"
            for req in requests:
                user = session.query(User).get(req.user_id)
                text += (
                    f"🆔 {req.id}\n"
                    f"👤 {user.phone_number}\n"
                    f"📝 {req.description[:100]}...\n"
                    f"📅 {req.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    "─────────────────\n"
                )
        else:
            text = "📭 Нових заявок немає"

        await update.message.reply_text(text)


async def show_users_for_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ користувачів для вибору додавання бонусу"""
    with Session() as session:
        users = session.query(User).filter(User.is_admin == False).limit(10).all()

        if users:
            keyboard = []
            for user in users:
                keyboard.append([InlineKeyboardButton(
                    f"{user.phone_number} (ID: {user.id})",
                    callback_data=f'bonus_{user.id}'
                )])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "💰 Виберіть користувача для додавання бонусу:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("Користувачів не знайдено")


def main():
    """Запуск бота"""
    application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()

    # Основні обробники
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.CONTACT, handle_phone))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Обробники команд
    application.add_handler(CommandHandler("stats", show_statistics))
    application.add_handler(CommandHandler("tour", request_tour))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("setadmin", set_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))

    # Callback обробники для адміністраторів
    application.add_handler(CallbackQueryHandler(show_users, pattern='^admin_users'))
    application.add_handler(CallbackQueryHandler(add_bonus, pattern='^(bonus_|select_user_bonus)'))
    application.add_handler(CallbackQueryHandler(show_tour_requests, pattern='^admin_tours'))

    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()