import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Float, Boolean, ForeignKey, Text, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    
    # Баланс и прогресс
    balance = Column(Integer, default=0)  # в звёздах
    level = Column(Integer, default=1)
    exp = Column(Integer, default=0)
    
    # Статистика ставок
    total_bets = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    total_refunds = Column(Integer, default=0)
    total_stars_bet = Column(BigInteger, default=0)
    total_stars_won = Column(BigInteger, default=0)
    total_stars_lost = Column(BigInteger, default=0)
    total_stars_refunded = Column(BigInteger, default=0)
    
    # Реферальная система
    referral_code = Column(String(50), unique=True, index=True, nullable=True)
    referred_by = Column(BigInteger, nullable=True)  # telegram_id пригласившего
    referrals_count = Column(Integer, default=0)
    referral_earnings = Column(Integer, default=0)
    
    # Временные метки
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    last_daily_bonus = Column(DateTime, nullable=True)
    
    # Админские флаги
    is_banned = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)  # отдельный флаг, не только по списку
    
    # Защита от ботов
    ip_addresses = Column(Text, nullable=True)  # можно хранить как JSON список
    fingerprint = Column(String(255), nullable=True)
    
    # Связи
    bets = relationship("Bet", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    purchases = relationship("Purchase", back_populates="user")
    
    __table_args__ = (
        Index('ix_users_telegram_id_referral', 'telegram_id', 'referral_code'),
    )


class Bet(Base):
    __tablename__ = 'bets'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    round_id = Column(Integer, ForeignKey('rounds.id'), nullable=False)
    amount = Column(Integer, nullable=False)  # ставка в звёздах
    result = Column(String(20), nullable=True)  # 'win', 'loss', 'refund'
    payout = Column(Integer, default=0)  # сколько получено (0 если проигрыш)
    multiplier = Column(Float, default=1.0)  # множитель выигрыша (обычно 2.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="bets")
    round = relationship("Round", back_populates="bets")
    
    __table_args__ = (
        Index('ix_bets_user_id', 'user_id'),
        Index('ix_bets_round_id', 'round_id'),
        Index('ix_bets_created_at', 'created_at'),
    )


class Round(Base):
    __tablename__ = 'rounds'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    round_time = Column(DateTime, unique=True, nullable=False, index=True)  # время начала раунда (минута)
    
    # Статистика раунда
    total_bets = Column(Integer, default=0)
    total_amount = Column(Integer, default=0)  # сумма всех ставок
    winners_count = Column(Integer, default=0)
    winners_amount = Column(Integer, default=0)  # сумма выплат победителям
    refunds_count = Column(Integer, default=0)
    refunds_amount = Column(Integer, default=0)  # сумма кэшбека
    losers_count = Column(Integer, default=0)    # те, кто не получил ничего
    house_profit = Column(Integer, default=0)    # доход владельца (10% + экономия)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связи
    bets = relationship("Bet", back_populates="round", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    amount = Column(Integer, nullable=False)  # положительное - начисление, отрицательное - списание
    type = Column(String(50), nullable=False)  # 'bet', 'win', 'refund', 'referral_bonus', 'daily_bonus', 'purchase', 'admin'
    description = Column(String(255), nullable=True)
    reference_id = Column(Integer, nullable=True)  # ID связанной записи (например, bet_id)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="transactions")
    
    __table_args__ = (
        Index('ix_transactions_user_id', 'user_id'),
        Index('ix_transactions_type', 'type'),
        Index('ix_transactions_created_at', 'created_at'),
    )


class DailyBonus(Base):
    __tablename__ = 'daily_bonuses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    bonus_date = Column(DateTime, default=datetime.datetime.utcnow)  # день получения
    amount = Column(Integer, nullable=False)  # сколько звёзд получено
    streak = Column(Integer, default=1)  # текущая серия дней
    
    __table_args__ = (
        Index('ix_daily_bonuses_user_id_date', 'user_id', 'bonus_date'),
    )


class ShopItem(Base):
    __tablename__ = 'shop_items'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False)  # цена в звёздах
    item_type = Column(String(50), nullable=False)  # 'booster', 'skin', 'title'
    item_data = Column(JSON, nullable=True)  # дополнительные данные (например, множитель бустера)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Purchase(Base):
    __tablename__ = 'purchases'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    item_id = Column(Integer, ForeignKey('shop_items.id'), nullable=False)
    price_paid = Column(Integer, nullable=False)  # цена на момент покупки
    purchased_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_used = Column(Boolean, default=False)  # для одноразовых бустеров
    
    user = relationship("User", back_populates="purchases")
    item = relationship("ShopItem")


class Tournament(Base):
    __tablename__ = 'tournaments'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    prize_pool = Column(Integer, default=0)  # общий призовой фонд
    min_bet = Column(Integer, default=0)  # минимальная ставка для участия
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('ix_tournaments_start_end', 'start_time', 'end_time'),
    )


class TournamentParticipant(Base):
    __tablename__ = 'tournament_participants'
    
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    score = Column(Integer, default=0)  # очки (например, сумма выигрышей)
    rank = Column(Integer, nullable=True)  # место по итогам
    prize = Column(Integer, default=0)  # полученный приз
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('ix_tournament_participants_tournament', 'tournament_id'),
    )


class AdminLog(Base):
    __tablename__ = 'admin_logs'
    
    id = Column(Integer, primary_key=True)
    admin_id = Column(BigInteger, nullable=False)  # telegram_id администратора
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
