import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from .models import Session, User, ReferralBonus, TourRequest


def generate_referral_code():
    """Генерація унікального реферального коду"""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return code


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start"""
    keyboard = [
        [KeyboardButton("📱 Поділитися номером", request_contact=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "Вітаю! Для реєстрації поділіться номером телефону 📱",
        reply_markup=reply_markup
    )


async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник отримання номера телефону"""
    if not update.message.contact:
        await update.message.reply_text("Будь ласка, поділіться вашим номером телефону")
        return

    phone_number = update.message.contact.phone_number
    user_id = update.effective_user.id

    with Session() as session:
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            # Створення нового користувача
            referral_code = generate_referral_code()
            user = User(
                telegram_id=user_id,
                phone_number=phone_number,
                referral_code=referral_code
            )

            # Перевіряємо наявність реферального коду
            if 'referral_code' in context.user_data:
                referrer = session.query(User).filter_by(referral_code=context.user_data['referral_code']).first()
                if referrer:
                    user.referred_by = referrer.id
                    # Нараховуємо бонус рефереру
                    referrer.balance += 100
                    bonus = ReferralBonus(
                        user_id=referrer.id,
                        amount=100,
                        description=f"Бонус за реєстрацію користувача {phone_number}"
                    )
                    session.add(bonus)

            session.add(user)
            session.commit()

            # Створюємо клавіатуру з основними кнопками
            keyboard = [
                [KeyboardButton("📊 Моя статистика")],
                [KeyboardButton("🔗 Моє посилання")],
                [KeyboardButton("🏖 Підбір туру")],
                [KeyboardButton("ℹ Про програму")],
                [KeyboardButton("📞 Контакти")],
                [KeyboardButton("🛠 Адмін панель")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            # Формуємо повідомлення про реєстрацію
            message = "Дякую! Ви зареєстровані ✅\n"
            if user.referred_by:
                message += "Ваш друг отримав +100 грн за ваше запрошення!\n"
            message += f"Ваше реферальне посилання: t.me/MyNewArtembot?start={referral_code}"

            await update.message.reply_text(message, reply_markup=reply_markup)
        else:
            # Оновлюємо меню для існуючого користувача
            keyboard = [
                [KeyboardButton("📊 Моя статистика")],
                [KeyboardButton("🔗 Моє посилання")],
                [KeyboardButton("🏖 Підбір туру")],
                [KeyboardButton("ℹ Про програму")],
                [KeyboardButton("📞 Контакти")],
                [KeyboardButton("🛠 Адмін панель")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Ви вже зареєстровані в системі!", reply_markup=reply_markup)


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати статистику користувача"""
    user_id = update.effective_user.id
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if user:
            # Отримання статистики рефералів
            first_level = session.query(User).filter_by(referred_by=user.id).count()
            second_level = session.query(User).filter(
                User.referred_by.in_(
                    session.query(User.id).filter_by(referred_by=user.id)
                )
            ).count()
            third_level = session.query(User).filter(
                User.referred_by.in_(
                    session.query(User.id).filter(
                        User.referred_by.in_(
                            session.query(User.id).filter_by(referred_by=user.id)
                        )
                    )
                )
            ).count()

            stats_text = (
                f"📊 ВАША СТАТИСТИКА\n"
                f"💰 Поточний баланс: {user.balance} грн\n\n"
                f"👥 ВАШІ РЕФЕРАЛИ:\n"
                f"├── 1-й рівень: {first_level} осіб ({first_level * 100} грн)\n"
                f"├── 2-й рівень: {second_level} осіб ({second_level * 50} грн)\n"
                f"└── 3-й рівень: {third_level} осіб ({third_level * 25} грн)\n\n"
                f"🔗 Ваше посилання:\n"
                f"t.me/yourbot?start={user.referral_code}"
            )

            keyboard = [[InlineKeyboardButton("📤 Поділитися посиланням", url=f"https://t.me/yourbot?start={user.referral_code}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(stats_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text("Спочатку потрібно зареєструватися!")


async def request_tour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник запиту на підбір туру"""
    user_id = update.effective_user.id
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if user:
            await update.message.reply_text(
                "Опишіть ваші побажання до туру\n"
                "(країна, дати, бюджет, кількість осіб):"
            )
            context.user_data['waiting_for_tour_request'] = True
        else:
            await update.message.reply_text("Спочатку потрібно зареєструватися!")


async def handle_tour_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник тексту з описом туру"""
    if context.user_data.get('waiting_for_tour_request'):
        user_id = update.effective_user.id
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()

            if user:
                tour_request = TourRequest(
                    user_id=user.id,
                    description=update.message.text
                )
                session.add(tour_request)
                session.commit()

                await update.message.reply_text(
                    "Дякую! Ваша заявка передана менеджеру.\n"
                    "З вами зв'яжуться протягом години! ✅"
                )
                context.user_data['waiting_for_tour_request'] = False
            else:
                await update.message.reply_text("Спочатку потрібно зареєструватися!")