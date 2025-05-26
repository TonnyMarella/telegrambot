import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from .models import Session, User, ReferralBonus, TourRequest


def is_admin(user_id: int) -> bool:
    """Перевірка чи є користувач адміністратором"""
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        return user.is_admin if user else False


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ адмін-панелі"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас немає доступу до адмін-панелі!")
        return

    # Показуємо адмінське меню з кнопками
    keyboard = [
        [KeyboardButton("👥 Користувачі"), KeyboardButton("📋 Заявки на тури")],
        [KeyboardButton("💰 Додати бонус"), KeyboardButton("📊 Статистика системи")],
        [KeyboardButton("👤 Режим користувача")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🔧 АДМІН-ПАНЕЛЬ\n\n"
        "Ви увійшли в режим адміністратора.\n"
        "Виберіть потрібний розділ:",
        reply_markup=reply_markup
    )


async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ списку користувачів"""
    if not is_admin(update.effective_user.id):
        return

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

            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
        else:
            message = "Користувачів не знайдено"
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.message.edit_text(message)
            else:
                await update.message.reply_text(message)


async def add_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Додавання бонусів користувачу"""
    if not is_admin(update.effective_user.id):
        return

    query = update.callback_query

    if query.data == 'select_user_bonus':
        # Показуємо список користувачів для вибору
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
                await query.message.edit_text(
                    "💰 Виберіть користувача для додавання бонусу:",
                    reply_markup=reply_markup
                )
            else:
                await query.message.edit_text("Користувачів не знайдено")
    else:
        # Обробка вибору конкретного користувача
        user_id = int(query.data.split('_')[1])
        context.user_data['bonus_user_id'] = user_id
        await query.message.edit_text(
            "💰 Введіть суму для нарахування (тільки число):"
        )
        context.user_data['waiting_for_bonus_amount'] = True


async def handle_bonus_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення суми бонусу"""
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get('waiting_for_bonus_amount'):
        try:
            amount = float(update.message.text)
            user_id = context.user_data['bonus_user_id']

            with Session() as session:
                user = session.query(User).get(user_id)

                if user:
                    user.balance += amount
                    bonus = ReferralBonus(
                        user_id=user.id,
                        amount=amount,
                        description="Ручне нарахування адміністратором"
                    )
                    session.add(bonus)
                    session.commit()

                    await update.message.reply_text(
                        f"✅ Нараховано {amount} грн користувачу {user.phone_number}\n"
                        f"Новий баланс: {user.balance} грн"
                    )
                else:
                    await update.message.reply_text("❌ Користувача не знайдено!")

            context.user_data['waiting_for_bonus_amount'] = False
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректну суму (тільки число)!")


async def show_tour_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заявок на підбір турів"""
    if not is_admin(update.effective_user.id):
        return

    with Session() as session:
        requests = session.query(TourRequest).filter_by(status='new').limit(10).all()

        if requests:
            text = "🏖 НОВІ ЗАЯВКИ НА ТУРИ:\n\n"
            for req in requests:
                user = session.query(User).get(req.user_id)
                text += (
                    f"🆔 {req.id}\n"
                    f"👤 {user.phone_number if user else 'Невідомий'}\n"
                    f"📝 {req.description[:100]}{'...' if len(req.description) > 100 else ''}\n"
                    f"📅 {req.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    "─────────────────\n"
                )
        else:
            text = "📭 Нових заявок немає"

        keyboard = [[InlineKeyboardButton("🔄 Оновити", callback_data='admin_tours')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)


async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Встановлення користувача як адміністратора"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас немає доступу до цієї команди!")
        return

    try:
        user_id = int(context.args[0])
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()

            if user:
                user.is_admin = True
                session.commit()

                # Сповіщаємо нового адміністратора та оновлюємо його меню
                try:
                    keyboard = [
                        [KeyboardButton("👥 Користувачі"), KeyboardButton("📋 Заявки на тури")],
                        [KeyboardButton("💰 Додати бонус"), KeyboardButton("📊 Статистика системи")],
                        [KeyboardButton("👤 Режим користувача")]
                    ]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    # Надсилаємо повідомлення новому адміністратору
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🎉 Вітаємо! Ви тепер адміністратор системи!\n"
                             "🛠 Адмін-панель активована. Використовуйте кнопки нижче для управління.",
                        reply_markup=reply_markup
                    )

                    await update.message.reply_text(
                        f"✅ Користувач {user.phone_number} тепер адміністратор\n"
                        f"📨 Йому надіслано сповіщення про нові права"
                    )
                except Exception as e:
                    await update.message.reply_text(
                        f"✅ Користувач {user.phone_number} тепер адміністратор\n"
                        f"⚠️ Не вдалося надіслати сповіщення (можливо, користувач заблокував бота)"
                    )
            else:
                await update.message.reply_text("❌ Користувача з таким Telegram ID не знайдено")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Використовуйте: /setadmin <telegram_id>")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Зняття прав адміністратора"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас немає доступу до цієї команди!")
        return

    try:
        user_id = int(context.args[0])
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()

            if user and user.is_admin:
                user.is_admin = False
                session.commit()

                # Оновлюємо меню користувача на звичайне
                try:
                    keyboard = [
                        [KeyboardButton("📊 Моя статистика")],
                        [KeyboardButton("🔗 Моє посилання")],
                        [KeyboardButton("🏖 Підбір туру")],
                        [KeyboardButton("ℹ Про програму")],
                        [KeyboardButton("📞 Контакти")]
                    ]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    await context.bot.send_message(
                        chat_id=user_id,
                        text="ℹ️ Ваші права адміністратора скасовані.\n"
                             "Меню повернуто до звичайного режиму.",
                        reply_markup=reply_markup
                    )

                    await update.message.reply_text(
                        f"✅ У користувача {user.phone_number} скасовані права адміністратора"
                    )
                except:
                    await update.message.reply_text(
                        f"✅ У користувача {user.phone_number} скасовані права адміністратора\n"
                        f"⚠️ Не вдалося надіслати сповіщення"
                    )
            else:
                await update.message.reply_text("❌ Користувача не знайдено або він не є адміністратором")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Використовуйте: /removeadmin <telegram_id>")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")