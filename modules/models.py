from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine('sqlite:///referral_bot.db')
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    phone_number = Column(String)
    referral_code = Column(String, unique=True)
    balance = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    referred_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    is_admin = Column(Integer, default=0)

class ReferralBonus(Base):
    __tablename__ = 'referral_bonuses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class TourRequest(Base):
    __tablename__ = 'tour_requests'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    description = Column(String)
    status = Column(String, default='new')
    created_at = Column(DateTime, default=datetime.utcnow)

# Створення таблиць
Base.metadata.create_all(engine) 