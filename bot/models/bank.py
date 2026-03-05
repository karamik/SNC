# bot/models/bank.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, BigInteger, Enum
from sqlalchemy.orm import relationship
import datetime
import enum

from bot.models.db import Base

class DepositStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EARLY_WITHDRAWN = "early_withdrawn"

class DepositTariff(Base):
    __tablename__ = 'deposit_tariffs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # например, "На 7 дней", "На 30 дней"
    duration_days = Column(Integer, nullable=False)  # срок в днях
    interest_rate = Column(Float, nullable=False)  # процентная ставка (например, 5.0 за 7 дней, 10.0 за 30)
    min_amount = Column(Integer, default=0)  # минимальная сумма вклада
    max_amount = Column(Integer, nullable=True)  # максимальная сумма (None - без ограничений)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Deposit(Base):
    __tablename__ = 'deposits'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    tariff_id = Column(Integer, ForeignKey('deposit_tariffs.id'), nullable=False)
    
    amount = Column(BigInteger, nullable=False)  # сумма вклада в звёздах
    interest_rate = Column(Float, nullable=False)  # ставка на момент открытия
    expected_interest = Column(BigInteger, nullable=False)  # ожидаемый доход (расчётный)
    
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=False)  # дата окончания
    
    status = Column(Enum(DepositStatus), default=DepositStatus.ACTIVE)
    
    # Если досрочное снятие
    early_withdrawn_at = Column(DateTime, nullable=True)
    early_withdrawn_amount = Column(BigInteger, nullable=True)  # сколько получено при досрочном снятии (без процентов)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связи
    user = relationship("User", backref="deposits")
    tariff = relationship("DepositTariff")
