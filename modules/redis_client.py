import redis
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()

# Отримання параметрів підключення з змінних середовища
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# Створення клієнта Redis
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True  # Автоматично декодуємо відповіді в рядки
)


def set_user_data(user_id: str, data: dict, expire_seconds: int = 3600):
    """Зберігає дані користувача в Redis"""
    key = f"user:{user_id}"
    redis_client.setex(key, expire_seconds, json.dumps(data))


def get_user_data(user_id: str) -> dict:
    """Отримує дані користувача з Redis"""
    key = f"user:{user_id}"
    data = redis_client.get(key)
    return json.loads(data) if data else {}


def delete_user_data(user_id: str):
    """Видаляє дані користувача з Redis"""
    key = f"user:{user_id}"
    redis_client.delete(key)


def set_referral_code(code: str, user_id: str, expire_seconds: int = 86400):
    """Зберігає реферальний код в Redis"""
    key = f"referral:{code}"
    redis_client.setex(key, expire_seconds, user_id)


def get_referral_user_id(code: str) -> str:
    """Отримує ID користувача за реферальним кодом"""
    key = f"referral:{code}"
    return redis_client.get(key)


def increment_user_balance(user_id: str, amount: float):
    """Збільшує баланс користувача в Redis"""
    key = f"balance:{user_id}"
    redis_client.incrbyfloat(key, amount)


def decrement_user_balance(user_id: str, amount: float):
    """Зменшує баланс користувача в Redis"""
    key = f"balance:{user_id}"
    redis_client.incrbyfloat(key, -amount)


def get_user_balance(user_id: str) -> float:
    """Отримує баланс користувача з Redis"""
    key = f"balance:{user_id}"
    balance = redis_client.get(key)
    return float(balance) if balance else 0.0


def set_tour_request_status(request_id: int, status: str):
    """Зберігає статус заявки на тур в Redis"""
    key = f"tour_request:{request_id}"
    redis_client.set(key, status)


def get_tour_request_status(request_id: int) -> str:
    """Отримує статус заявки на тур з Redis"""
    key = f"tour_request:{request_id}"
    return redis_client.get(key)


def add_to_recent_requests(request_id: int, user_id: str):
    """Додає заявку до списку останніх заявок користувача"""
    key = f"recent_requests:{user_id}"
    redis_client.lpush(key, str(request_id))
    redis_client.ltrim(key, 0, 9)  # Зберігаємо тільки 10 останніх заявок


def get_recent_requests(user_id: str) -> list:
    """Отримує список останніх заявок користувача"""
    key = f"recent_requests:{user_id}"
    return redis_client.lrange(key, 0, -1)


def set_user_session(user_id: str, session_data: dict, expire_seconds: int = 3600):
    """Зберігає дані сесії користувача"""
    key = f"session:{user_id}"
    redis_client.setex(key, expire_seconds, json.dumps(session_data))


def get_user_session(user_id: str) -> dict:
    """Отримує дані сесії користувача"""
    key = f"session:{user_id}"
    data = redis_client.get(key)
    return json.loads(data) if data else {}


def clear_user_session(user_id: str):
    """Очищає дані сесії користувача"""
    key = f"session:{user_id}"
    redis_client.delete(key)


def clear_users_list_cache():
    """Очистити кеш списку користувачів"""
    pattern = "users_list:*"
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)


def get_system_stats() -> dict:
    """Отримати системну статистику з Redis"""
    data = redis_client.get("system_stats")
    return json.loads(data) if data else None


def set_system_stats(stats: dict, expire_seconds: int = 600):
    """Зберегти системну статистику в Redis"""
    redis_client.setex("system_stats", expire_seconds, json.dumps(stats))


def set_tour_request_data(request_id: int, request_data: dict, expire_seconds: int = 3600):
    """Зберегти дані заявки в Redis"""
    key = f"tour_request:{request_id}"
    redis_client.setex(key, expire_seconds, json.dumps(request_data))


def get_tour_request_data(request_id: int) -> dict:
    """Отримати дані заявки з Redis"""
    key = f"tour_request:{request_id}"
    data = redis_client.get(key)
    return json.loads(data) if data else None


def clear_all_redis_data():
    """Повністю очистити всі дані в Redis"""
    redis_client.flushall()
    print("✅ Redis очищено успішно") 