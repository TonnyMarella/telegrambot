import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from .models import Session, User, ReferralBonus, TourRequest
from sqlalchemy import func


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
        [KeyboardButton("👥 Управління користувачами"), KeyboardButton("📋 Заявки на тури")],
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
    """Показ меню управління користувачами"""
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("📋 Перегляд всіх користувачів", callback_data='admin_users_list')],
        [InlineKeyboardButton("🔍 Пошук користувача", callback_data='admin_users_search')],
        [InlineKeyboardButton("📊 Статистика користувачів", callback_data='admin_users_stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = "👥 УПРАВЛІННЯ КОРИСТУВАЧАМИ\n\nВиберіть потрібну опцію:"

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ списку всіх користувачів"""
    if not is_admin(update.effective_user.id):
        return

    with Session() as session:
        users = session.query(User).limit(10).all()

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

            keyboard = [
                [InlineKeyboardButton("🔄 Оновити", callback_data='admin_users_list')],
                [InlineKeyboardButton("🔍 Пошук", callback_data='admin_users_search')],
                [InlineKeyboardButton("📊 Статистика", callback_data='admin_users_stats')],
                [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
            ]
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


async def search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу пошуку користувача"""
    if not is_admin(update.effective_user.id):
        return

    text = "Введіть ID користувача або номер телефону для пошуку:\nДля скасування напишіть 'вийти'"
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text)
    else:
        await update.message.reply_text(text)
    
    context.user_data['waiting_for_user_search'] = True


async def handle_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка пошуку користувача"""
    if not is_admin(update.effective_user.id):
        return

    if not context.user_data.get('waiting_for_user_search'):
        return

    identifier = update.message.text.strip()
    
    if identifier.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
        context.user_data.pop('waiting_for_user_search', None)
        await update.message.reply_text("❌ Пошук скасовано")
        return

    with Session() as session:
        user_id = int(identifier)
        user = session.query(User).get(user_id) or session.query(User).filter_by(phone_number=identifier).first()

        if user:
            # Отримуємо статистику користувача
            total_referrals = session.query(User).filter_by(referred_by=user.id).count()
            total_bonuses = session.query(ReferralBonus).filter_by(user_id=user.id).count()
            total_bonus_amount = session.query(ReferralBonus).filter_by(user_id=user.id).with_entities(
                func.sum(ReferralBonus.amount)).scalar() or 0

            text = (
                f"👤 ІНФОРМАЦІЯ ПРО КОРИСТУВАЧА\n\n"
                f"🆔 ID: {user.id}\n"
                f"📱 Телефон: {user.phone_number}\n"
                f"💰 Баланс: {user.balance} грн\n"
                f"🔗 Реферальний код: {user.referral_code}\n"
                f"📅 Дата реєстрації: {user.created_at.strftime('%d.%m.%Y')}\n"
                f"👥 Запрошено рефералів: {total_referrals}\n"
                f"🎁 Отримано бонусів: {total_bonuses}\n"
                f"💵 Загальна сума бонусів: {total_bonus_amount} грн\n"
                f"{'👑 Адміністратор' if user.is_admin else ''}"
            )

            keyboard = [
                [InlineKeyboardButton("💰 Нарахувати бонус", callback_data=f'bonus_user_{user.id}')],
                [InlineKeyboardButton("📊 Історія нарахувань", callback_data=f'bonus_history_{user.id}')],
                [InlineKeyboardButton("🔍 Пошук іншого", callback_data='admin_users_search')],
                [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(
                "❌ Користувача не знайдено.\n"
                "Спробуйте ще раз або напишіть 'вийти' для скасування:"
            )

    context.user_data.pop('waiting_for_user_search', None)


async def show_users_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ загальної статистики користувачів"""
    if not is_admin(update.effective_user.id):
        return

    with Session() as session:
        total_users = session.query(User).count()
        active_users = session.query(User).filter(User.balance > 0).count()
        total_balance = session.query(func.sum(User.balance)).scalar() or 0
        total_referrals = session.query(User).filter(User.referred_by.isnot(None)).count()
        total_bonuses = session.query(ReferralBonus).count()
        total_bonus_amount = session.query(func.sum(ReferralBonus.amount)).scalar() or 0

        text = (
            "📊 СТАТИСТИКА КОРИСТУВАЧІВ\n\n"
            f"👥 Всього користувачів: {total_users}\n"
            f"✅ Активних користувачів: {active_users}\n"
            f"💰 Загальний баланс: {total_balance} грн\n"
            f"👥 Запрошено рефералів: {total_referrals}\n"
            f"🎁 Нараховано бонусів: {total_bonuses}\n"
            f"💵 Загальна сума бонусів: {total_bonus_amount} грн"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Оновити", callback_data='admin_users_stats')],
            [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)


async def show_users_for_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу додавання бонусу"""
    if not is_admin(update.effective_user.id):
        return

    # Отримуємо ID користувача з callback_data
    if hasattr(update, 'callback_query') and update.callback_query:
        user_id = int(update.callback_query.data.split('_')[2])
        with Session() as session:
            user = session.query(User).get(user_id)
            if user:
                context.user_data['bonus_user_id'] = user.id
                context.user_data['bonus_user_phone'] = user.phone_number
                await update.callback_query.message.edit_text(
                    f"Знайдено: {user.phone_number}\n"
                    f"Поточний баланс: {user.balance} грн\n\n"
                    f"Введіть суму для нарахування:"
                )
                context.user_data['waiting_for_bonus_amount'] = True
            else:
                await update.callback_query.message.edit_text("❌ Користувача не знайдено")
    else:
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
                        [KeyboardButton("👥 Управління користувачами"), KeyboardButton("📋 Заявки на тури")],
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


async def show_bonus_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ історії нарахувань користувача"""
    if not is_admin(update.effective_user.id):
        return

    user_id = int(update.callback_query.data.split('_')[2])
    
    with Session() as session:
        user = session.query(User).get(user_id)
        if not user:
            await update.callback_query.message.edit_text("❌ Користувача не знайдено")
            return

        # Отримуємо історію нарахувань
        bonuses = session.query(ReferralBonus).filter_by(user_id=user_id).order_by(ReferralBonus.created_at.desc()).all()

        if bonuses:
            text = f"📊 ІСТОРІЯ НАРАХУВАНЬ\n\nКористувач: {user.phone_number}\n\n"
            for bonus in bonuses:
                text += (
                    f"💰 {bonus.amount} грн\n"
                    f"📝 {bonus.description}\n"
                    f"📅 {bonus.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    "─────────────────\n"
                )
        else:
            text = f"📊 ІСТОРІЯ НАРАХУВАНЬ\n\nКористувач: {user.phone_number}\n\nІсторія нарахувань порожня"

        keyboard = [
            [InlineKeyboardButton("💰 Нарахувати бонус", callback_data=f'bonus_user_{user_id}')],
            [InlineKeyboardButton("◀️ Назад", callback_data=f'search_user_{user_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)