from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()

# Отримання параметрів підключення з змінних середовища
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'referral_bot')

# Створення URL для підключення до PostgreSQL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Створення двигуна SQLAlchemy з налаштуваннями для PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_size=20,  # Розмір пулу з'єднань
    max_overflow=10,  # Максимальна кількість додаткових з'єднань
    pool_timeout=30,  # Таймаут очікування з'єднання
    pool_recycle=3600,  # Перепідключення кожну годину
    pool_pre_ping=True  # Перевірка з'єднання перед використанням
)

# Створення базового класу для моделей
Base = declarative_base()

# Створення фабрики сесій
Session = sessionmaker(bind=engine)

# Моделі
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    phone_number = Column(String(20))
    referral_code = Column(String(10), unique=True)
    referred_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    balance = Column(Float, default=0.0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Зв'язки
    referrals = relationship('User', backref='referrer', remote_side=[id])
    bonuses = relationship('ReferralBonus', back_populates='user')
    tour_requests = relationship('TourRequest', back_populates='user')


class ReferralBonus(Base):
    __tablename__ = 'referral_bonuses'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    description = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Зв'язки
    user = relationship('User', back_populates='bonuses')


class TourRequest(Base):
    __tablename__ = 'tour_requests'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    description = Column(Text)
    status = Column(String(20), default='new')  # new, in_progress, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Зв'язки
    user = relationship('User', back_populates='tour_requests')


# Створення таблиць
def init_db():
    Base.metadata.create_all(engine) 