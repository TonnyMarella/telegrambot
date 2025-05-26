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
        [KeyboardButton("💰 Нарахування балів"), KeyboardButton("📊 Статистика системи")],
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

            keyboard = [[InlineKeyboardButton("💰 Нарахування балів користувачу", callback_data='select_user_bonus')]]
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


async def show_users_for_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу додавання бонусу"""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "Введіть ID користувача або номер телефону:"
    )
    context.user_data['waiting_for_user_identifier'] = True


async def handle_user_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка введення ID або номера телефону користувача"""
    if not is_admin(update.effective_user.id):
        return

    identifier = update.message.text.strip()
    
    # Перевіряємо чи користувач хоче вийти
    if identifier.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
        # Очищаємо дані контексту
        context.user_data.pop('waiting_for_user_identifier', None)
        await update.message.reply_text(
            "❌ Операцію скасовано"
        )
        return

    with Session() as session:
        # Спробуємо знайти користувача за ID або номером телефону
        user_id = int(identifier)
        user = session.query(User).get(user_id) or session.query(User).filter_by(phone_number=identifier).first()

        if user:
            context.user_data['bonus_user_id'] = user.id
            context.user_data['bonus_user_phone'] = user.phone_number
            await update.message.reply_text(
                f"Знайдено: {user.phone_number}\n"
                f"Поточний баланс: {user.balance} грн\n\n"
                f"Введіть суму для нарахування:"
            )
            context.user_data['waiting_for_user_identifier'] = False
            context.user_data['waiting_for_bonus_amount'] = True
        else:
            await update.message.reply_text(
                "❌ Користувача не знайдено.\n"
                "Спробуйте ще раз або напишіть 'вийти' для скасування:"
            )


async def handle_bonus_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення суми бонусу"""
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get('waiting_for_bonus_amount'):
        amount = update.message.text.strip()
        
        # Перевіряємо чи користувач хоче вийти
        if amount.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
            # Очищаємо дані контексту
            context.user_data.pop('waiting_for_bonus_amount', None)
            context.user_data.pop('bonus_user_id', None)
            context.user_data.pop('bonus_user_phone', None)
            await update.message.reply_text(
                "❌ Операцію скасовано"
            )
            return

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Сума має бути більше 0")

            context.user_data['bonus_amount'] = amount
            await update.message.reply_text(
                "Введіть опис нарахування:"
            )
            context.user_data['waiting_for_bonus_amount'] = False
            context.user_data['waiting_for_bonus_description'] = True
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректну суму (тільки число більше 0)!\n"
                "Або напишіть 'вийти' для скасування:"
            )


async def handle_bonus_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення опису бонусу"""
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get('waiting_for_bonus_description'):
        description = update.message.text.strip()
        
        # Перевіряємо чи користувач хоче вийти
        if description.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
            # Очищаємо дані контексту
            context.user_data.pop('waiting_for_bonus_description', None)
            context.user_data.pop('bonus_user_id', None)
            context.user_data.pop('bonus_user_phone', None)
            context.user_data.pop('bonus_amount', None)
            await update.message.reply_text(
                "❌ Операцію скасовано"
            )
            return

        user_id = context.user_data['bonus_user_id']
        amount = context.user_data['bonus_amount']

        with Session() as session:
            user = session.query(User).get(user_id)
            if user:
                # Нараховуємо бонус
                user.balance += amount
                bonus = ReferralBonus(
                    user_id=user.id,
                    amount=amount,
                    description=description
                )
                session.add(bonus)
                session.commit()

                # Відправляємо повідомлення адміну
                await update.message.reply_text(
                    f"✅ Нараховано {amount} грн користувачу {user.phone_number}\n"
                    f"Новий баланс: {user.balance} грн"
                )

                # Відправляємо повідомлення користувачу
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=f"💰 Вам нараховано +{amount} грн!\n"
                             f"💬 Причина: {description}"
                    )
                except Exception as e:
                    print(f"Помилка відправки повідомлення користувачу {user.telegram_id}: {str(e)}")

            # Очищаємо дані контексту
            context.user_data.pop('bonus_user_id', None)
            context.user_data.pop('bonus_user_phone', None)
            context.user_data.pop('bonus_amount', None)
            context.user_data.pop('waiting_for_bonus_description', None)


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
                        [KeyboardButton("💰 Нарахування балів"), KeyboardButton("📊 Статистика системи")],
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