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
    """Обробка отримання контакту користувача"""
    if not update.message.contact:
        await update.message.reply_text("❌ Будь ласка, надішліть свій контакт")
        return

    phone_number = update.message.contact.phone_number
    user_id = update.effective_user.id

    with Session() as session:
        # Перевіряємо чи користувач вже існує
        existing_user = session.query(User).filter_by(telegram_id=user_id).first()
        if existing_user:
            await update.message.reply_text("✅ Ви вже зареєстровані в системі!")
            return

        # Перевіряємо чи є реферальний код
        referral_code = context.user_data.get('referral_code')
        referred_by = None
        second_level_referrer = None

        if referral_code:
            # Знаходимо користувача, який запросив
            referrer = session.query(User).filter_by(referral_code=referral_code).first()
            if referrer:
                referred_by = referrer.id
                # Нараховуємо бонус запрошувачу
                referrer.balance += 100
                bonus = ReferralBonus(
                    user_id=referrer.id,
                    amount=100,
                    description=f"Бонус за запрошення користувача {phone_number}"
                )
                session.add(bonus)

                # Перевіряємо чи є у запрошувача свій запрошувач (другий рівень)
                if referrer.referred_by:
                    second_level_referrer = session.query(User).get(referrer.referred_by)
                    if second_level_referrer:
                        # Нараховуємо бонус користувачу другого рівня
                        second_level_referrer.balance += 50
                        bonus = ReferralBonus(
                            user_id=second_level_referrer.id,
                            amount=50,
                            description=f"Бонус за запрошення користувача {phone_number} (2-й рівень)"
                        )
                        session.add(bonus)

        # Створюємо нового користувача
        new_user = User(
            telegram_id=user_id,
            phone_number=phone_number,
            referred_by=referred_by
        )
        session.add(new_user)
        session.commit()

        # Відправляємо повідомлення про успішну реєстрацію
        await update.message.reply_text(
            "✅ Реєстрація успішна!\n\n"
            "Тепер ви можете:\n"
            "├── Запрошувати друзів\n"
            "├── Отримувати бонуси\n"
            "└── Використовувати всі можливості бота"
        )

        # Відправляємо повідомлення запрошувачу про нарахування бонусу
        if referred_by:
            try:
                referrer_user = session.query(User).get(referred_by)
                await context.bot.send_message(
                    chat_id=referrer_user.telegram_id,
                    text=f"💰 Вам нараховано +100 грн!\n"
                         f"💬 За запрошення користувача {phone_number}"
                )
            except Exception as e:
                print(f"Помилка відправки повідомлення запрошувачу {referred_by}: {str(e)}")

        # Відправляємо повідомлення користувачу другого рівня про нарахування бонусу
        if second_level_referrer:
            try:
                await context.bot.send_message(
                    chat_id=second_level_referrer.telegram_id,
                    text=f"💰 Вам нараховано +50 грн!\n"
                         f"💬 За запрошення користувача {phone_number} (2-й рівень)"
                )
            except Exception as e:
                print(f"Помилка відправки повідомлення користувачу 2-го рівня {second_level_referrer.telegram_id}: {str(e)}")

        # Показуємо основне меню
        keyboard = [
            [KeyboardButton("📊 Моя статистика")],
            [KeyboardButton("🔗 Моє посилання")],
            [KeyboardButton("🏖 Підбір туру")],
            [KeyboardButton("ℹ Про програму")],
            [KeyboardButton("📞 Контакти")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Виберіть потрібну опцію:", reply_markup=reply_markup)


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

                # Відправляємо повідомлення адміністраторам
                admins = session.query(User).filter_by(is_admin=True).all()
                for admin in admins:
                    try:
                        await context.bot.send_message(
                            chat_id=admin.telegram_id,
                            text=f"🔔 НОВА ЗАЯВКА НА ТУР\n\n"
                                 f"👤 Користувач: {user.phone_number}\n"
                                 f"📝 Опис:\n{update.message.text}\n\n"
                                 f"🆔 ID заявки: {tour_request.id}\n"
                                 f"📅 Створено: {tour_request.created_at.strftime('%d.%m.%Y %H:%M')}"
                        )
                    except Exception as e:
                        print(f"Помилка відправки повідомлення адміну {admin.telegram_id}: {str(e)}")

                await update.message.reply_text(
                    "Дякую! Ваша заявка передана менеджеру.\n"
                    "З вами зв'яжуться протягом години! ✅"
                )
                context.user_data['waiting_for_tour_request'] = False
            else:
                await update.message.reply_text("Спочатку потрібно зареєструватися!")