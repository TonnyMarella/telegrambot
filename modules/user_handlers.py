import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from .models import Session, User, ReferralBonus, TourRequest
from .redis_client import (
    set_user_data, get_user_data, set_referral_code,
    get_referral_user_id, increment_user_balance,
    get_user_balance, set_tour_request_status,
    get_tour_request_status, add_to_recent_requests,
    get_recent_requests
)


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
    user_id = str(update.effective_user.id)

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
        third_level_referrer = None

        if referral_code:
            # Спочатку перевіряємо в Redis
            referrer_id = get_referral_user_id(referral_code)
            if referrer_id:
                referred_by = int(referrer_id)
            else:
                # Якщо немає в Redis, шукаємо в базі даних
                referrer = session.query(User).filter_by(referral_code=referral_code).first()
                if referrer:
                    referred_by = referrer.id
                    # Зберігаємо в Redis для майбутнього використання
                    set_referral_code(referral_code, str(referrer.id))

            if referred_by:
                # Нараховуємо бонус запрошувачу
                referrer = session.query(User).get(referred_by)
                referrer.balance += 800
                bonus = ReferralBonus(
                    user_id=referrer.id,
                    amount=800,
                    description=f"Бонус за запрошення користувача {phone_number}"
                )
                session.add(bonus)
                # Оновлюємо баланс в Redis
                increment_user_balance(str(referrer.telegram_id), 800)

                # Перевіряємо чи є у запрошувача свій запрошувач (другий рівень)
                if referrer.referred_by:
                    second_level_referrer = session.query(User).get(referrer.referred_by)
                    if second_level_referrer:
                        # Нараховуємо бонус користувачу другого рівня
                        second_level_referrer.balance += 400
                        bonus = ReferralBonus(
                            user_id=second_level_referrer.id,
                            amount=400,
                            description=f"Бонус за запрошення користувача {phone_number} (2-й рівень)"
                        )
                        session.add(bonus)
                        # Оновлюємо баланс в Redis
                        increment_user_balance(str(second_level_referrer.telegram_id), 400)

                        # Перевіряємо чи є у користувача другого рівня свій запрошувач (третій рівень)
                        if second_level_referrer.referred_by:
                            third_level_referrer = session.query(User).get(second_level_referrer.referred_by)
                            if third_level_referrer:
                                # Нараховуємо бонус користувачу третього рівня
                                third_level_referrer.balance += 200
                                bonus = ReferralBonus(
                                    user_id=third_level_referrer.id,
                                    amount=200,
                                    description=f"Бонус за запрошення користувача {phone_number} (3-й рівень)"
                                )
                                session.add(bonus)
                                # Оновлюємо баланс в Redis
                                increment_user_balance(str(third_level_referrer.telegram_id), 200)

        # Генеруємо реферальний код для нового користувача
        new_referral_code = generate_referral_code()
        
        # Створюємо нового користувача
        new_user = User(
            telegram_id=user_id,
            phone_number=phone_number,
            referred_by=referred_by,
            referral_code=new_referral_code
        )
        session.add(new_user)
        session.commit()

        # Зберігаємо дані користувача в Redis
        user_data = {
            'telegram_id': user_id,
            'phone_number': phone_number,
            'referral_code': new_referral_code,
            'referred_by': referred_by,
            'balance': 0.0,
            'is_admin': False
        }
        set_user_data(user_id, user_data)
        set_referral_code(new_referral_code, user_id)

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
                    text=f"💰 Вам нараховано +800 грн!\n"
                         f"💬 За запрошення користувача {phone_number}"
                )
            except Exception as e:
                print(f"Помилка відправки повідомлення запрошувачу {referred_by}: {str(e)}")

        # Відправляємо повідомлення користувачу другого рівня про нарахування бонусу
        if second_level_referrer:
            try:
                await context.bot.send_message(
                    chat_id=second_level_referrer.telegram_id,
                    text=f"💰 Вам нараховано +400 грн!\n"
                         f"💬 За запрошення користувача {phone_number} (2-й рівень)"
                )
            except Exception as e:
                print(f"Помилка відправки повідомлення користувачу 2-го рівня {second_level_referrer.telegram_id}: {str(e)}")

        # Відправляємо повідомлення користувачу третього рівня про нарахування бонусу
        if third_level_referrer:
            try:
                await context.bot.send_message(
                    chat_id=third_level_referrer.telegram_id,
                    text=f"💰 Вам нараховано +200 грн!\n"
                         f"💬 За запрошення користувача {phone_number} (3-й рівень)"
                )
            except Exception as e:
                print(f"Помилка відправки повідомлення користувачу 3-го рівня {third_level_referrer.telegram_id}: {str(e)}")

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
    user_id = str(update.effective_user.id)
    
    # Спочатку перевіряємо дані в Redis
    user_data = get_user_data(user_id)
    
    with Session() as session:
        if not user_data:
            # Якщо даних немає в Redis, беремо з бази даних
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                # Зберігаємо дані в Redis
                user_data = {
                    'telegram_id': user_id,
                    'phone_number': user.phone_number,
                    'referral_code': user.referral_code,
                    'referred_by': user.referred_by,
                    'balance': user.balance,
                    'is_admin': user.is_admin
                }
                set_user_data(user_id, user_data)
            else:
                await update.message.reply_text("Спочатку потрібно зареєструватися!")
                return

        # Отримання статистики рефералів
        first_level = session.query(User).filter_by(referred_by=user_data.get('id')).count()
        second_level = session.query(User).filter(
            User.referred_by.in_(
                session.query(User.id).filter_by(referred_by=user_data.get('id'))
            )
        ).count()
        third_level = session.query(User).filter(
            User.referred_by.in_(
                session.query(User.id).filter(
                    User.referred_by.in_(
                        session.query(User.id).filter_by(referred_by=user_data.get('id'))
                    )
                )
            )
        ).count()

        # Отримуємо баланс з Redis
        balance = get_user_balance(user_id)

        stats_text = (
            f"📊 ВАША СТАТИСТИКА\n"
            f"💰 Поточний баланс: {balance} грн\n\n"
            f"👥 ВАШІ РЕФЕРАЛИ:\n"
            f"├── 1-й рівень: {first_level} осіб ({first_level * 800} грн)\n"
            f"├── 2-й рівень: {second_level} осіб ({second_level * 400} грн)\n"
            f"└── 3-й рівень: {third_level} осіб ({third_level * 200} грн)\n\n"
            f"🔗 Ваше посилання:\n"
            f"t.me/yourbot?start={user_data.get('referral_code')}"
        )

        keyboard = [[InlineKeyboardButton("📤 Поділитися посиланням", url=f"https://t.me/yourbot?start={user_data.get('referral_code')}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(stats_text, reply_markup=reply_markup)


async def request_tour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник запиту на підбір туру"""
    user_id = str(update.effective_user.id)
    
    # Перевіряємо дані користувача в Redis
    user_data = get_user_data(user_id)
    
    if not user_data:
        await update.message.reply_text("Спочатку потрібно зареєструватися!")
        return

    await update.message.reply_text(
        "Опишіть ваші побажання до туру\n"
        "(країна, дати, бюджет, кількість осіб):"
    )
    context.user_data['waiting_for_tour_request'] = True


async def handle_tour_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник тексту з описом туру"""
    if context.user_data.get('waiting_for_tour_request'):
        user_id = str(update.effective_user.id)
        
        # Перевіряємо дані користувача в Redis
        user_data = get_user_data(user_id)
        
        if not user_data:
            await update.message.reply_text("Спочатку потрібно зареєструватися!")
            return

        with Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                tour_request = TourRequest(
                    user_id=user.id,
                    description=update.message.text
                )
                session.add(tour_request)
                session.commit()

                # Зберігаємо статус заявки в Redis
                set_tour_request_status(tour_request.id, 'new')
                # Додаємо заявку до списку останніх заявок користувача
                add_to_recent_requests(tour_request.id, user_id)

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


async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user):
    """Обробка текстових повідомлень для звичайних користувачів"""
    if text == "📊 Моя статистика":
        await show_statistics(update, context)
    elif text == "🏖 Підбір туру":
        await request_tour(update, context)
    elif text == "ℹ Про програму":
        await update.message.reply_text(
            "Ви маєте чудову нагоду допомогти своєму другу отримати якісну послугу з бронювання відпочинку: просто відправляйте унікальне посилання через цей бот або передайте його контактну інформацію (також тут), щоб наш найкращий спеціаліст зв'язався з ним.\n"
            "Коли Ваш друг отримає послугу здійснивши бронювання туру - Вам нараховується бонус 800 грн.\n"
            "Коли Ваші друзі почнуть розвивати свою мережу і відправляти свої посилання і хтось із них отримує послугу, то Вам також нараховуються бонуси, в такому розмірі:\n"
            "2 ланка = 400 грн\n"
            "3 ланка і всі наступні = 200 грн.\n"
            "Всі бонуси зберігаються на вашому особовому рахунку і можуть бути використані Вами на оплату своє подорожі.\n\n"
            "Кількість таких рекомендацій не обмежена"
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