import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from .models import Session, User, ReferralBonus, TourRequest
from sqlalchemy import func
from .redis_client import (
    get_user_data, get_tour_request_status,
    set_tour_request_status, set_tour_request_data, get_recent_requests,
    set_user_data, get_user_balance, increment_user_balance,
    get_users_list, set_users_list, get_system_stats, set_system_stats,
    clear_users_list_cache
)


def is_admin(user_id: int) -> bool:
    """Перевірка чи є користувач адміністратором - Redis first"""
    # Спочатку перевіряємо в Redis
    user_data = get_user_data(str(user_id))
    if user_data:
        return user_data.get('is_admin', False)

    # Якщо немає в Redis - перевіряємо в БД та зберігаємо в Redis
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=str(user_id)).first()
        if user:
            user_data = {
                'id': user.id,
                'telegram_id': str(user.telegram_id),
                'phone_number': user.phone_number,
                'referral_code': user.referral_code,
                'referred_by': user.referred_by,
                'balance': user.balance,
                'is_admin': user.is_admin,
                'created_at': user.created_at.strftime('%d.%m.%Y')
            }
            set_user_data(str(user_id), user_data)
            return user.is_admin
        return False


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ адмін-панелі"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас немає доступу до адмін-панелі!")
        return

    keyboard = [
        [KeyboardButton("👥 Управління користувачами"), KeyboardButton("📋 Заявки на тури")],
        [KeyboardButton("💰 Нарахування балів")],
        [KeyboardButton("👤 Режим користувача")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🔧 АДМІН-ПАНЕЛЬ\n\n"
        "Ви увійшли в режим адміністратора.\n"
        "Виберіть потрібний розділ:",
        reply_markup=reply_markup
    )


def get_users_from_cache_or_db(limit=10, offset=0):
    """Отримати користувачів з Redis або БД"""
    # Спочатку отримуємо з БД
    with Session() as session:
        users = session.query(User).offset(offset).limit(limit).all()
        users_data = []

        for user in users:
            # Отримуємо актуальні дані з БД
            user_data = {
                'id': user.id,
                'telegram_id': str(user.telegram_id),
                'phone_number': user.phone_number,
                'referral_code': user.referral_code,
                'referred_by': user.referred_by,
                'balance': user.balance,
                'is_admin': user.is_admin,
                'created_at': user.created_at.strftime('%d.%m.%Y')
            }
            # Оновлюємо кеш в Redis
            set_user_data(str(user.telegram_id), user_data)
            users_data.append(user_data)

        # Зберігаємо список в кеш на 5 хвилин
        set_users_list(offset, limit, users_data, 300)
        return users_data


async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню управління користувачами"""
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("📋 Перегляд всіх користувачів", callback_data='admin_users_list')],
        [InlineKeyboardButton("🔍 Пошук користувача", callback_data='admin_users_search')]
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

    # Отримуємо користувачів з БД
    users_data = get_users_from_cache_or_db(limit=10)

    text = "👥 СПИСОК КОРИСТУВАЧІВ:\n\n"

    if users_data:
        for user_data in users_data:
            admin_mark = " 👑" if user_data.get('is_admin') else ""
            text += (
                f"ID: {user_data['id']}{admin_mark}\n"
                f"📱 {user_data['phone_number']}\n"
                f"💰 Баланс: {user_data['balance']} грн\n"
                f"🔗 Код: {user_data['referral_code']}\n"
                f"📅 {user_data.get('created_at', '')}\n"
                "─────────────────\n"
            )
    else:
        text = "Користувачів не знайдено"

    keyboard = [
        [InlineKeyboardButton("🔍 Пошук", callback_data='admin_users_search')],
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


def find_user_by_id_or_phone(identifier):
    """Пошук користувача за ID або телефоном"""
    with Session() as session:
        try:
            user_id = int(identifier)
            user = session.query(User).get(user_id) or session.query(User).filter_by(telegram_id=str(user_id)).first()
        except ValueError:
            # Це номер телефону
            user = session.query(User).filter_by(phone_number=identifier).first()

        if user:
            # Отримуємо актуальні дані з БД
            user_data = {
                'id': user.id,
                'telegram_id': str(user.telegram_id),
                'phone_number': user.phone_number,
                'referral_code': user.referral_code,
                'referred_by': user.referred_by,
                'balance': user.balance,
                'is_admin': user.is_admin,
                'created_at': user.created_at.strftime('%d.%m.%Y')
            }
            # Оновлюємо кеш в Redis
            set_user_data(str(user.telegram_id), user_data)
            return user_data

    return None


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
    """Обробка пошуку користувача - оптимізовано"""
    if not is_admin(update.effective_user.id):
        return

    if not context.user_data.get('waiting_for_user_search'):
        return

    identifier = update.message.text.strip()

    if identifier.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
        context.user_data.pop('waiting_for_user_search', None)
        await update.message.reply_text("❌ Пошук скасовано")
        return

    # Отримуємо актуальні дані з БД
    with Session() as session:
        try:
            user_id = int(identifier)
            user = session.query(User).get(user_id) or session.query(User).filter_by(telegram_id=str(user_id)).first()
        except ValueError:
            # Це номер телефону
            user = session.query(User).filter_by(phone_number=identifier).first()

        if user:
            # Отримуємо актуальну статистику з БД
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
                [InlineKeyboardButton("👥 Переглянути рефералів", callback_data=f'show_referrals_{user.id}')],
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


def get_system_statistics():
    """Отримати системну статистику - Redis first"""
    # Спочатку перевіряємо кеш
    cached_stats = get_system_stats()
    if cached_stats:
        return cached_stats

    # Якщо немає в кеші - розраховуємо з БД
    with Session() as session:
        total_users = session.query(User).count()
        active_users = session.query(User).filter(User.balance > 0).count()
        total_referrals = session.query(User).filter(User.referred_by.isnot(None)).count()
        total_bonuses = session.query(ReferralBonus).count()
        total_bonus_amount = session.query(func.sum(ReferralBonus.amount)).scalar() or 0

        # Отримуємо загальний баланс з Redis (більш актуальний)
        total_balance = 0
        users = session.query(User.telegram_id).all()
        for user in users:
            balance = get_user_balance(str(user.telegram_id))
            if balance:
                total_balance += float(balance)

        stats = {
            'total_users': total_users,
            'active_users': active_users,
            'total_balance': total_balance,
            'total_referrals': total_referrals,
            'total_bonuses': total_bonuses,
            'total_bonus_amount': float(total_bonus_amount)
        }

        # Кешуємо на 10 хвилин
        set_system_stats(stats, 600)
        return stats


async def show_users_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ загальної статистики користувачів - оптимізовано"""
    if not is_admin(update.effective_user.id):
        return

    stats = get_system_statistics()

    text = (
        "📊 СТАТИСТИКА КОРИСТУВАЧІВ\n\n"
        f"👥 Всього користувачів: {stats['total_users']}\n"
        f"✅ Активних користувачів: {stats['active_users']}\n"
        f"👥 Запрошено рефералів: {stats['total_referrals']}\n"
        f"🎁 Нараховано бонусів: {stats['total_bonuses']}\n"
        f"💵 Загальна сума бонусів: {stats['total_bonus_amount']:.2f} грн"
    )

    keyboard = [
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def show_users_for_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу додавання бонусу - оптимізовано"""
    if not is_admin(update.effective_user.id):
        return

    if hasattr(update, 'callback_query') and update.callback_query:
        user_id = int(update.callback_query.data.split('_')[2])

        # Спочатку шукаємо в Redis
        user_data = None
        with Session() as session:
            user = session.query(User).get(user_id)
            if user:
                user_data = get_user_data(str(user.telegram_id))
                if not user_data:
                    # Зберігаємо в Redis якщо немає
                    user_data = {
                        'id': user.id,
                        'telegram_id': str(user.telegram_id),
                        'phone_number': user.phone_number,
                        'referral_code': user.referral_code,
                        'referred_by': user.referred_by,
                        'balance': user.balance,
                        'is_admin': user.is_admin,
                        'created_at': user.created_at.strftime('%d.%m.%Y')
                    }
                    set_user_data(str(user.telegram_id), user_data)

        if user_data:
            context.user_data['bonus_user_id'] = user_data['id']
            context.user_data['bonus_user_phone'] = user_data['phone_number']
            context.user_data['bonus_user_telegram_id'] = user_data['telegram_id']

            await update.callback_query.message.edit_text(
                f"Знайдено: {user_data['phone_number']}\n"
                f"Поточний баланс: {user.balance} грн\n\n"
                f"Введіть суму для нарахування:"
            )
            context.user_data['waiting_for_bonus_amount'] = True
        else:
            await update.callback_query.message.edit_text("❌ Користувача не знайдено")
    else:
        await update.message.reply_text("Введіть ID користувача або номер телефону:")
        context.user_data['waiting_for_user_identifier'] = True


async def handle_user_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка введення ID або номера телефону користувача - оптимізовано"""
    if not is_admin(update.effective_user.id):
        return

    identifier = update.message.text.strip()

    if identifier.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
        context.user_data.pop('waiting_for_user_identifier', None)
        await update.message.reply_text("❌ Операцію скасовано")
        return

    # Використовуємо оптимізовану функцію пошуку
    user_data = find_user_by_id_or_phone(identifier)

    if user_data:
        balance = get_user_balance(user_data['telegram_id']) or user_data.get('balance', 0)
        context.user_data['bonus_user_id'] = user_data['id']
        context.user_data['bonus_user_phone'] = user_data['phone_number']
        context.user_data['bonus_user_telegram_id'] = user_data['telegram_id']

        await update.message.reply_text(
            f"Знайдено: {user_data['phone_number']}\n"
            f"Поточний баланс: {balance} грн\n\n"
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
    """Обробка введеної суми бонусу"""
    if not is_admin(update.effective_user.id):
        return

    text = update.message.text.strip()
    
    # Перевіряємо чи користувач хоче вийти
    if text.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
        context.user_data.pop('waiting_for_bonus_amount', None)
        context.user_data.pop('bonus_user_id', None)
        context.user_data.pop('bonus_user_phone', None)
        context.user_data.pop('bonus_user_telegram_id', None)
        await update.message.reply_text("❌ Операцію скасовано")
        return

    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text("❌ Сума має бути більше 0!")
            return

        context.user_data['bonus_amount'] = amount
        await update.message.reply_text(
            "Введіть опис для бонусу (наприклад: 'Бонус за активність'):"
        )
        context.user_data['waiting_for_bonus_amount'] = False
        context.user_data['waiting_for_bonus_description'] = True

    except ValueError:
        await update.message.reply_text("❌ Будь ласка, введіть коректну суму!")


async def handle_bonus_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка опису бонусу та нарахування"""
    if not is_admin(update.effective_user.id):
        return

    user_id = context.user_data.get('bonus_user_id')
    amount = context.user_data.get('bonus_amount')
    description = update.message.text

    with Session() as session:
        user = session.query(User).get(user_id)
        if user:
            # Нараховуємо бонус в базі даних
            user.balance += amount
            bonus = ReferralBonus(
                user_id=user.id,
                amount=amount,
                description=description
            )
            session.add(bonus)
            session.commit()

            # Оновлюємо баланс в Redis
            increment_user_balance(str(user.telegram_id), amount)

            # Відправляємо повідомлення користувачу
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"💰 Вам нараховано +{amount} грн!\n"
                         f"💬 {description}"
                )
            except Exception as e:
                print(f"Помилка відправки повідомлення користувачу {user.telegram_id}: {str(e)}")

            await update.message.reply_text(
                f"✅ Бонус успішно нараховано!\n"
                f"👤 Користувач: {user.phone_number}\n"
                f"💰 Сума: {amount} грн\n"
                f"💬 Опис: {description}"
            )
        else:
            await update.message.reply_text("❌ Користувача не знайдено!")

    # Очищаємо дані
    context.user_data.pop('selected_user_id', None)
    context.user_data.pop('bonus_amount', None)
    context.user_data.pop('waiting_for_bonus_description', None)


def get_tour_requests_from_cache_or_db():
    """Отримати заявки з Redis або БД"""
    # Спочатку перевіряємо кеш
    cached_requests = get_recent_requests()
    if cached_requests:
        return cached_requests

    # Якщо немає в кеші - отримуємо з БД
    with Session() as session:
        new_requests = session.query(TourRequest).filter_by(status='new').order_by(TourRequest.created_at.desc()).all()
        processed_requests = session.query(TourRequest).filter_by(status='end').order_by(
            TourRequest.created_at.desc()).limit(5).all()

        requests_data = {
            'new': [],
            'processed': []
        }

        # Обробляємо нові заявки
        for request in new_requests:
            # Отримуємо дані користувача
            user = session.query(User).get(request.user_id)
            user_data = get_user_data(str(user.telegram_id))
            if not user_data:
                user_data = {
                    'id': user.id,
                    'telegram_id': str(user.telegram_id),
                    'phone_number': user.phone_number,
                    'referral_code': user.referral_code,
                    'referred_by': user.referred_by,
                    'balance': user.balance,
                    'is_admin': user.is_admin,
                    'created_at': user.created_at.strftime('%d.%m.%Y')
                }
                set_user_data(str(user.telegram_id), user_data)

            # Зберігаємо дані заявки в Redis
            request_data = {
                'id': request.id,
                'user_id': request.user_id,
                'description': request.description,
                'status': request.status,
                'created_at': request.created_at.strftime('%d.%m.%Y %H:%M'),
                'user_phone': user_data['phone_number']
            }
            set_tour_request_data(request.id, request_data)
            requests_data['new'].append(request_data)

        # Обробляємо оброблені заявки
        for request in processed_requests:
            user = session.query(User).get(request.user_id)
            user_data = get_user_data(str(user.telegram_id))
            if not user_data:
                user_data = {
                    'id': user.id,
                    'telegram_id': str(user.telegram_id),
                    'phone_number': user.phone_number,
                    'referral_code': user.referral_code,
                    'referred_by': user.referred_by,
                    'balance': user.balance,
                    'is_admin': user.is_admin,
                    'created_at': user.created_at.strftime('%d.%m.%Y')
                }
                set_user_data(str(user.telegram_id), user_data)

            request_data = {
                'id': request.id,
                'user_id': request.user_id,
                'description': request.description,
                'status': request.status,
                'created_at': request.created_at.strftime('%d.%m.%Y %H:%M'),
                'user_phone': user_data['phone_number']
            }
            set_tour_request_data(request.id, request_data)
            requests_data['processed'].append(request_data)

        return requests_data


async def show_tour_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список заявок на тури"""
    with Session() as session:
        # Отримуємо нові заявки
        new_requests = session.query(TourRequest).filter_by(status='new').order_by(TourRequest.created_at.desc()).all()

        # Отримуємо оброблені заявки
        processed_requests = session.query(TourRequest).filter_by(status='end').order_by(TourRequest.created_at.desc()).limit(5).all()

        text = "📋 ЗАЯВКИ НА ТУРИ\n\n"

        if new_requests:
            text += "🆕 НОВІ ЗАЯВКИ:\n"
            for request in new_requests:
                # Перевіряємо статус в Redis
                status = get_tour_request_status(request.id) or 'new'

                # Перевіряємо дані користувача в Redis
                user = session.query(User).get(request.user_id)
                user_data = get_user_data(str(user.telegram_id))
                if not user_data:
                    user_data = {
                        'telegram_id': str(user.telegram_id),
                        'phone_number': user.phone_number,
                        'referral_code': user.referral_code,
                        'referred_by': user.referred_by,
                        'balance': user.balance,
                        'is_admin': user.is_admin
                    }
                    set_user_data(str(user.telegram_id), user_data)

                text += f"├── ID: {request.id}\n"
                text += f"├── Клієнт: {user_data['phone_number']}\n"
                text += f"├── Статус: {status}\n"
                text += f"└── Створено: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        else:
            text += "🆕 Нових заявок немає\n\n"

        if processed_requests:
            text += "✅ ОБРОБЛЕНІ ЗАЯВКИ:\n"
            for request in processed_requests:
                # Перевіряємо статус в Redis
                status = get_tour_request_status(request.id) or 'end'

                # Перевіряємо дані користувача в Redis
                user = session.query(User).get(request.user_id)
                user_data = get_user_data(str(user.telegram_id))
                if not user_data:
                    user_data = {
                        'telegram_id': str(user.telegram_id),
                        'phone_number': user.phone_number,
                        'referral_code': user.referral_code,
                        'referred_by': user.referred_by,
                        'balance': user.balance,
                        'is_admin': user.is_admin
                    }
                    set_user_data(str(user.telegram_id), user_data)

                text += f"├── ID: {request.id}\n"
                text += f"├── Клієнт: {user_data['phone_number']}\n"
                text += f"├── Статус: {status}\n"
                text += f"└── Створено: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        else:
            text += "✅ Оброблених заявок немає\n\n"

        keyboard = []
        for request in new_requests:
            keyboard.append([InlineKeyboardButton(f"Заявка #{request.id}", callback_data=f"tour_request_{request.id}")])

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_tours")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


async def show_tour_request_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати деталі заявки на тур"""
    request_id = int(update.callback_query.data.split('_')[2])

    with Session() as session:
        request = session.query(TourRequest).get(request_id)
        if request:
            # Перевіряємо дані користувача в Redis
            user = session.query(User).get(request.user_id)
            user_data = get_user_data(str(user.telegram_id))
            if not user_data:
                user_data = {
                    'telegram_id': str(user.telegram_id),
                    'phone_number': user.phone_number,
                    'referral_code': user.referral_code,
                    'referred_by': user.referred_by,
                    'balance': user.balance,
                    'is_admin': user.is_admin
                }
                set_user_data(str(user.telegram_id), user_data)

            # Перевіряємо статус в Redis
            status = get_tour_request_status(request.id) or request.status

            text = f"📋 ДЕТАЛІ ЗАЯВКИ #{request.id}\n\n"
            text += f"👤 Клієнт: {user_data['phone_number']}\n"
            text += f"📝 Опис:\n{request.description}\n\n"
            text += f"📅 Створено: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            text += f"📊 Статус: {status}\n"

            keyboard = []
            if status == 'new':
                keyboard.append([InlineKeyboardButton("✅ Завершити обробку", callback_data=f"complete_request_{request.id}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_tours_list")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


async def complete_tour_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершити обробку заявки на тур"""
    request_id = int(update.callback_query.data.split('_')[2])

    with Session() as session:
        request = session.query(TourRequest).get(request_id)
        if request and request.status == 'new':
            request.status = 'end'
            session.commit()

            # Оновлюємо статус в Redis
            set_tour_request_status(request_id, 'end')

            # Перевіряємо дані користувача в Redis
            user = session.query(User).get(request.user_id)
            user_data = get_user_data(str(user.telegram_id))
            if not user_data:
                user_data = {
                    'telegram_id': str(user.telegram_id),
                    'phone_number': user.phone_number,
                    'referral_code': user.referral_code,
                    'referred_by': user.referred_by,
                    'balance': user.balance,
                    'is_admin': user.is_admin
                }
                set_user_data(str(user.telegram_id), user_data)

            await show_tour_requests(update, context)


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

        # Перевіряємо дані користувача в Redis
        user_data = get_user_data(str(user.telegram_id))
        if not user_data:
            user_data = {
                'telegram_id': str(user.telegram_id),
                'phone_number': user.phone_number,
                'referral_code': user.referral_code,
                'referred_by': user.referred_by,
                'balance': user.balance,
                'is_admin': user.is_admin
            }
            set_user_data(str(user.telegram_id), user_data)

        # Отримуємо історію нарахувань
        bonuses = session.query(ReferralBonus).filter_by(user_id=user_id).order_by(ReferralBonus.created_at.desc()).all()

        if bonuses:
            text = f"📊 ІСТОРІЯ НАРАХУВАНЬ\n\nКористувач: {user_data['phone_number']}\n\n"
            for bonus in bonuses:
                text += (
                    f"💰 {bonus.amount} грн\n"
                    f"📝 {bonus.description}\n"
                    f"📅 {bonus.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    "─────────────────\n"
                )
        else:
            text = f"📊 ІСТОРІЯ НАРАХУВАНЬ\n\nКористувач: {user_data['phone_number']}\n\nІсторія нарахувань порожня"

        keyboard = [
            [InlineKeyboardButton("💰 Нарахувати бонус", callback_data=f'bonus_user_{user_id}')],
            [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)


async def show_tour_requests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню роботи з заявками"""
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("📋 Перегляд всіх заявок", callback_data='admin_tours_list')],
        [InlineKeyboardButton("🔍 Пошук заявки", callback_data='admin_tours_search')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = "🏖 УПРАВЛІННЯ ЗАЯВКАМИ\n\nВиберіть потрібну опцію:"

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def search_tour_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу пошуку заявки"""
    if not is_admin(update.effective_user.id):
        return

    text = "Введіть ID заявки для пошуку:\nДля скасування напишіть 'вийти'"
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text)
    else:
        await update.message.reply_text(text)
    
    context.user_data['waiting_for_tour_search'] = True


async def handle_tour_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка пошуку заявки"""
    if not is_admin(update.effective_user.id):
        return

    if not context.user_data.get('waiting_for_tour_search'):
        return

    identifier = update.message.text.strip()
    
    if identifier.lower() in ['вийти', 'exit', 'cancel', 'скасувати']:
        context.user_data.pop('waiting_for_tour_search', None)
        await update.message.reply_text("❌ Пошук скасовано")
        return

    try:
        request_id = int(identifier)
        with Session() as session:
            request = session.query(TourRequest).get(request_id)
            if request:
                user = session.query(User).get(request.user_id)
                text = (
                    f"🏖 ДЕТАЛІ ЗАЯВКИ #{request.id}\n\n"
                    f"👤 Користувач: {user.phone_number if user else 'Невідомий'}\n"
                    f"📅 Створено: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"📝 Опис:\n{request.description}\n\n"
                    f"Статус: {'✅ Опрацьовано' if request.status == 'end' else '⏳ В обробці'}"
                )

                keyboard = []
                if request.status == 'new':
                    keyboard.append([InlineKeyboardButton("✅ Завершити обробку", callback_data=f'complete_request_{request.id}')])
                keyboard.extend([
                    [InlineKeyboardButton("🔍 Пошук іншої", callback_data='admin_tours_search')],
                    [InlineKeyboardButton("◀️ Назад", callback_data='admin_tours')]
                ])
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(
                    "❌ Заявку не знайдено.\n"
                    "Спробуйте ще раз або напишіть 'вийти' для скасування:"
                )
    except ValueError:
        await update.message.reply_text(
            "❌ Будь ласка, введіть коректний ID заявки (тільки число)!\n"
            "Або напишіть 'вийти' для скасування:"
        )

    context.user_data.pop('waiting_for_tour_search', None)


async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Встановлення користувача як адміністратора"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас немає доступу до цієї команди!")
        return

    try:
        identifier = context.args[0]
        with Session() as session:
            # Спробуємо знайти користувача за ID або телефоном
            try:
                user_id = int(identifier)
                user = session.query(User).get(user_id) or session.query(User).filter_by(telegram_id=str(user_id)).first()
            except ValueError:
                # Якщо не ID, то шукаємо за телефоном
                user = session.query(User).filter_by(phone_number=identifier).first()

            if user:
                user.is_admin = True
                session.commit()

                # Оновлюємо дані в Redis
                user_data = get_user_data(str(user.telegram_id))
                if user_data:
                    user_data['is_admin'] = True
                    set_user_data(str(user.telegram_id), user_data)

                # Очищаємо кеш списку користувачів
                clear_users_list_cache()

                # Сповіщаємо нового адміністратора та оновлюємо його меню
                try:
                    keyboard = [
                        [KeyboardButton("👥 Управління користувачами"), KeyboardButton("📋 Заявки на тури")],
                        [KeyboardButton("💰 Нарахування балів")],
                        [KeyboardButton("👤 Режим користувача")]
                    ]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    # Надсилаємо повідомлення новому адміністратору
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
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
                await update.message.reply_text("❌ Користувача не знайдено")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Використовуйте: /set_admin <id або номер телефону>")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Зняття прав адміністратора"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас немає доступу до цієї команди!")
        return

    try:
        identifier = context.args[0]
        with Session() as session:
            # Спробуємо знайти користувача за ID або телефоном
            try:
                user_id = int(identifier)
                user = session.query(User).get(user_id) or session.query(User).filter_by(telegram_id=str(user_id)).first()
            except ValueError:
                # Якщо не ID, то шукаємо за телефоном
                user = session.query(User).filter_by(phone_number=identifier).first()

            if user and user.is_admin:
                user.is_admin = False
                session.commit()

                # Оновлюємо дані в Redis
                user_data = get_user_data(str(user.telegram_id))
                if user_data:
                    user_data['is_admin'] = False
                    set_user_data(str(user.telegram_id), user_data)

                # Очищаємо кеш списку користувачів
                clear_users_list_cache()

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
                        chat_id=user.telegram_id,
                        text="ℹ️ Ваші права адміністратора скасовані.\n"
                             "Меню повернуто до звичайного режиму.",
                        reply_markup=reply_markup
                    )

                    await update.message.reply_text(
                        f"✅ У користувача {user.phone_number} скасовані права адміністратора"
                    )
                except Exception as e:
                    await update.message.reply_text(
                        f"✅ У користувача {user.phone_number} скасовані права адміністратора\n"
                        f"⚠️ Не вдалося надіслати сповіщення (можливо, користувач заблокував бота)"
                    )
            else:
                await update.message.reply_text("❌ Користувача не знайдено або він не є адміністратором")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Використовуйте: /remove_admin <id або номер телефону>")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


def get_user_referrals(user_id: int, level: int = 1):
    """Отримання рефералів користувача за рівнем"""
    with Session() as session:
        if level == 1:
            # Прямі реферали
            return session.query(User).filter_by(referred_by=user_id).all()
        else:
            # Отримуємо рефералів попереднього рівня
            prev_level_referrals = get_user_referrals(user_id, level - 1)
            if not prev_level_referrals:
                return []
            
            # Отримуємо рефералів для кожного реферала попереднього рівня
            current_level_referrals = []
            for referral in prev_level_referrals:
                current_level_referrals.extend(
                    session.query(User).filter_by(referred_by=referral.id).all()
                )
            return current_level_referrals


def get_referral_stats(user_id: int):
    """Отримання статистики рефералів користувача"""
    stats = {
        'level_1': 0,
        'level_2': 0,
        'level_3': 0
    }
    
    for level in range(1, 4):
        referrals = get_user_referrals(user_id, level)
        stats[f'level_{level}'] = len(referrals)
    
    return stats


def get_referral_bonus_stats(user_id: int):
    """Отримання статистики бонусів від рефералів користувача"""
    with Session() as session:
        # Отримуємо бонуси для рефералів 1-го рівня
        first_level_bonuses = session.query(func.sum(ReferralBonus.amount)).filter(
            ReferralBonus.user_id == user_id,
            ReferralBonus.amount == 100
        ).scalar() or 0

        # Отримуємо бонуси для рефералів 2-го рівня
        second_level_bonuses = session.query(func.sum(ReferralBonus.amount)).filter(
            ReferralBonus.user_id == user_id,
            ReferralBonus.description.like('%2-й рівень%')
        ).scalar() or 0

        # Отримуємо бонуси для рефералів 3-го рівня
        third_level_bonuses = session.query(func.sum(ReferralBonus.amount)).filter(
            ReferralBonus.user_id == user_id,
            ReferralBonus.description.like('%3-й рівень%')
        ).scalar() or 0

        # Отримуємо загальну суму бонусів
        total_bonuses = session.query(func.sum(ReferralBonus.amount)).filter(
            ReferralBonus.user_id == user_id
        ).scalar() or 0

        stats = {
            'level_1': first_level_bonuses,
            'level_2': second_level_bonuses,
            'level_3': third_level_bonuses,
            'total': total_bonuses
        }
        return stats


async def show_user_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ рефералів користувача"""
    if not is_admin(update.effective_user.id):
        return

    query = update.callback_query
    user_id = int(query.data.split('_')[2])  # Отримуємо ID користувача з callback_data

    # Отримуємо статистику рефералів
    stats = get_referral_stats(user_id)
    bonus_stats = get_referral_bonus_stats(user_id)
    
    # Отримуємо всі бонуси для перевірки
    with Session() as session:
        all_bonuses = session.query(ReferralBonus).filter_by(user_id=user_id).all()
        total_bonus_amount = sum(bonus.amount for bonus in all_bonuses)
    
    text = (
        f"👥 РЕФЕРАЛИ КОРИСТУВАЧА (ID: {user_id})\n\n"
        f"📊 Статистика:\n"
        f"1️⃣ Рівень: {stats['level_1']} рефералів (Бонуси: {bonus_stats['level_1']} грн)\n"
        f"2️⃣ Рівень: {stats['level_2']} рефералів (Бонуси: {bonus_stats['level_2']} грн)\n"
        f"3️⃣ Рівень: {stats['level_3']} рефералів (Бонуси: {bonus_stats['level_3']} грн)\n"
        f"💰 Загальна сума бонусів: {total_bonus_amount} грн\n\n"
    )

    # Отримуємо рефералів для кожного рівня
    for level in range(1, 4):
        referrals = get_user_referrals(user_id, level)
        text += f"📊 Рівень {level}:\n"
        
        if referrals:
            for ref in referrals:
                text += (
                    f"👤 ID: {ref.id}\n"
                    f"📱 Телефон: {ref.phone_number}\n"
                    f"💰 Баланс: {ref.balance} грн\n"
                    f"📅 Дата реєстрації: {ref.created_at.strftime('%d.%m.%Y')}\n"
                    "─────────────────\n"
                )
        else:
            text += "Немає рефералів\n"
        text += "\n"

    keyboard = [
        [InlineKeyboardButton("◀️ Назад", callback_data=f'user_info_{user_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(text, reply_markup=reply_markup)


async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ інформації про користувача"""
    if not is_admin(update.effective_user.id):
        return

    query = update.callback_query
    user_id = int(query.data.split('_')[2])  # Отримуємо ID користувача з callback_data

    with Session() as session:
        user = session.query(User).get(user_id)
        if not user:
            await query.message.edit_text("❌ Користувача не знайдено")
            return

        # Отримуємо актуальну статистику з БД
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
            [InlineKeyboardButton("👥 Переглянути рефералів", callback_data=f'show_referrals_{user.id}')],
            [InlineKeyboardButton("🔍 Пошук іншого", callback_data='admin_users_search')],
            [InlineKeyboardButton("◀️ Назад", callback_data='admin_users')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(text, reply_markup=reply_markup)