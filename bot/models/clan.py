# bot/models/clan.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, BigInteger, Float
from sqlalchemy.orm import relationship
import datetime

from bot.models.db import Base

class Clan(Base):
    __tablename__ = 'clans'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    tag = Column(String(10), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    avatar = Column(String(255), nullable=True)  # ссылка на картинку
    
    # Уровень и опыт клана
    level = Column(Integer, default=1)
    exp = Column(BigInteger, default=0)
    
    # Общий банк звёзд (для совместных ставок)
    bank = Column(BigInteger, default=0)
    
    # Статистика
    total_bets = Column(BigInteger, default=0)
    total_wins = Column(BigInteger, default=0)
    total_members = Column(Integer, default=1)
    
    # Время создания
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связи
    members = relationship("ClanMember", back_populates="clan", cascade="all, delete-orphan")
    battles = relationship("ClanBattle", foreign_keys="[ClanBattle.clan1_id]", back_populates="clan1")

class ClanMember(Base):
    __tablename__ = 'clan_members'
    
    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey('clans.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)  # один пользователь может быть только в одном клане
    
    role = Column(String(50), default='member')  # 'leader', 'officer', 'member'
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Вклад в клан
    contributed_stars = Column(BigInteger, default=0)  # сколько звёзд внёс в банк
    contributed_exp = Column(BigInteger, default=0)    # сколько опыта принёс клану
    
    # Связи
    clan = relationship("Clan", back_populates="members")
    user = relationship("User", backref="clan_membership")

class ClanBattle(Base):
    __tablename__ = 'clan_battles'
    
    id = Column(Integer, primary_key=True)
    clan1_id = Column(Integer, ForeignKey('clans.id'), nullable=False)
    clan2_id = Column(Integer, ForeignKey('clans.id'), nullable=False)
    
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    
    # Счёт (сумма выигрышей членов клана за время битвы)
    clan1_score = Column(BigInteger, default=0)
    clan2_score = Column(BigInteger, default=0)
    
    winner_id = Column(Integer, nullable=True)
    
    prize_pool = Column(BigInteger, default=0)  # призовой фонд (может формироваться из взносов или от проекта)
    
    is_active = Column(Boolean, default=True)
    
    # Связи
    clan1 = relationship("Clan", foreign_keys=[clan1_id])
    clan2 = relationship("Clan", foreign_keys=[clan2_id])
