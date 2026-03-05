# bot/models/achievement.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
import datetime

from bot.models.db import Base

class Achievement(Base):
    __tablename__ = 'achievements'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)  # emoji или ссылка на иконку
    condition_type = Column(String(50), nullable=False)  # 'total_bets', 'total_wins', 'total_stars_won', 'referrals_count', 'level' и т.д.
    condition_value = Column(Integer, nullable=False)  # пороговое значение
    reward_stars = Column(Integer, default=0)  # награда звёздами
    reward_exp = Column(Integer, default=0)     # награда опытом
    is_hidden = Column(Boolean, default=False)  # скрытое достижение (до получения)
    order = Column(Integer, default=0)          # для сортировки
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связи
    user_achievements = relationship("UserAchievement", back_populates="achievement", cascade="all, delete-orphan")

class UserAchievement(Base):
    __tablename__ = 'user_achievements'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    achievement_id = Column(Integer, ForeignKey('achievements.id'), nullable=False)
    achieved_at = Column(DateTime, default=datetime.datetime.utcnow)
    claimed = Column(Boolean, default=False)  # получена ли награда (если награда не автоматическая)
    
    # Связи
    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="user_achievements")
