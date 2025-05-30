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
    admin_panel, show_users, show_users_for_bonus,
    handle_user_identifier, handle_bonus_amount, handle_bonus_description,
    show_tour_requests, set_admin, remove_admin,
    show_users_list, search_user, handle_user_search, show_users_statistics,
    show_bonus_history, show_tour_request_details, complete_tour_request,
    show_tour_requests_menu, search_tour_request, handle_tour_search,
    show_user_referrals, show_user_info, handle_deduct_amount, handle_deduct_description
)
from single_bot import SingletonBot

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
        user = session.query(User).filter_by(telegram_id=str(user_id)).first()
        return user


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник текстових повідомлень"""
    # Перевіряємо чи очікуємо введення ідентифікатора користувача
    if context.user_data.get('waiting_for_user_identifier'):
        await handle_user_identifier(update, context)
        return

    # Перевіряємо чи очікуємо введення суми бонусу
    if context.user_data.get('waiting_for_deduct_amount'):
        await handle_deduct_amount(update, context)
        return

    # Перевіряємо чи очікуємо введення опису бонусу
    if context.user_data.get('waiting_for_deduct_description'):
        await handle_deduct_description(update, context)
        return

    # Перевіряємо чи очікуємо введення суми бонусу
    if context.user_data.get('waiting_for_bonus_amount'):
        await handle_bonus_amount(update, context)
        return

    # Перевіряємо чи очікуємо введення опису бонусу
    if context.user_data.get('waiting_for_bonus_description'):
        await handle_bonus_description(update, context)
        return

    # Перевіряємо чи очікуємо пошук користувача
    if context.user_data.get('waiting_for_user_search'):
        await handle_user_search(update, context)
        return

    # Перевіряємо чи очікуємо пошук заявки
    if context.user_data.get('waiting_for_tour_search'):
        await handle_tour_search(update, context)
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
            "Інформація про програму:\n\n"
            "Ви маєте чудову нагоду допомогти своєму другу отримати якісну послугу з бронювання відпочинку: просто відправляйте своє унікальне посилання через цей бот, щоб наш спеціаліст звʼязався з ним. За кожну реєстрацію по Вашому посиланню, Вам буде нараховано 100 грн.\n"
            "Коли Ваші друзі почнуть розвивати свою мережу і відправляти свої посилання, то Вам також нараховуються бонуси, в такому розмірі:\n"
            "2 ланка = 50 грн\n"
            "3 ланка і всі наступні = 25 грн.\n"
            "Коли Ваш друг по прямій Вашій рекомендації отримає послугу здійснивши бронювання туру — Вам додатково нарахується бонус в розмірі 800 грн.\n"
            "Всі бонуси зберігаються на вашому особовому рахунку і можуть бути використані Вами на оплату своєї подорожі.\n\n"
            "Кількість таких рекомендацій не обмежена."
        )

    elif text == "📞 Контакти":
        await update.message.reply_text(
            "📞 Наші контакти:\n\n"
            "🌐 Сайт: www.poihaluznamu.com\n"
            "📱 Viber/telegram: +38(073)676-88-66\n"
            "📱 Телефон: +38(067)676-88-86\n"
            "📱 Instagram: [@poihalu_z_namu_lviv](https://www.instagram.com/poihalu_z_namu_lviv?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw==)",
            parse_mode='Markdown'
        )

    elif text == "🔗 Моє посилання":
        await update.message.reply_text(
            f"🔗 Ваше реферальне посилання:\n"
            f"t.me/TourWithUsBot?start={user.referral_code}",
            parse_mode='Markdown',
            disable_web_page_preview=True
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
    if text == "👥 Управління користувачами":
        await show_users(update, context)
    elif text == "📋 Заявки на тури":
        await show_tour_requests_menu(update, context)
    elif text == "💰 Нарахування балів":
        await show_users_for_bonus(update, context)
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
        await admin_panel(update, context)
    else:
        # Якщо команда не розпізнана в адмін режимі, обробляємо як користувача
        await handle_user_text(update, context, text, user)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start з перевіркою авторизації та реферального коду"""
    # Отримуємо реферальний код з параметрів команди
    args = context.args
    referral_code = args[0] if args else None

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
        # Користувач не авторизований - зберігаємо реферальний код в контексті
        if referral_code:
            context.user_data['referral_code'] = referral_code
            await update.message.reply_text(f"Вітаю! Ви перейшли за реферальним посиланням.\n")
        # Показуємо меню реєстрації
        await start(update, context)


def main():
    """Запуск бота з захистом від повторного запуску"""

    # Варіант 1: Використання file locking (рекомендований)
    with SingletonBot('telegram_bot.lock'):
        print("🚀 Запускаємо Telegram бота...")

        application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()

        # Основні обробники
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.CONTACT, handle_phone))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        # Обробники команд
        application.add_handler(CommandHandler("stats", show_statistics))
        application.add_handler(CommandHandler("tour", request_tour))
        application.add_handler(CommandHandler("admin", admin_panel))
        application.add_handler(CommandHandler("set_admin", set_admin))
        application.add_handler(CommandHandler("remove_admin", remove_admin))

        # Обробники callback-запитів
        application.add_handler(CallbackQueryHandler(show_users_list, pattern='^admin_users_list$'))
        application.add_handler(CallbackQueryHandler(search_user, pattern='^admin_users_search$'))
        application.add_handler(CallbackQueryHandler(show_users, pattern='^admin_users$'))
        application.add_handler(CallbackQueryHandler(show_users_for_bonus, pattern='^bonus_user_\d+$'))
        application.add_handler(CallbackQueryHandler(show_users_for_bonus, pattern='^deduct_points_\d+$'))
        application.add_handler(CallbackQueryHandler(show_bonus_history, pattern='^bonus_history_\d+$'))
        application.add_handler(CallbackQueryHandler(show_tour_requests, pattern='^admin_tours_list$'))
        application.add_handler(CallbackQueryHandler(search_tour_request, pattern='^admin_tours_search$'))
        application.add_handler(CallbackQueryHandler(show_tour_requests_menu, pattern='^admin_tours$'))
        application.add_handler(CallbackQueryHandler(show_tour_request_details, pattern='^tour_request_\d+$'))
        application.add_handler(CallbackQueryHandler(complete_tour_request, pattern='^complete_request_\d+$'))
        application.add_handler(CallbackQueryHandler(show_user_referrals, pattern='^show_referrals_\d+$'))
        application.add_handler(CallbackQueryHandler(show_user_info, pattern='^user_info_\d+$'))

        print("✅ Бот успішно запущений!")

        try:
            # Запуск бота
            application.run_polling()
        except KeyboardInterrupt:
            print("\n🛑 Отримано сигнал переривання. Зупиняємо бота...")
        except Exception as e:
            print(f"❌ Помилка при роботі бота: {e}")
        finally:
            print("👋 Бот завершив роботу")


if __name__ == '__main__':
    main()