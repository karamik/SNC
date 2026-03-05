# bot/models/event.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float
from sqlalchemy.orm import relationship
import datetime

from bot.models.db import Base

class GameEvent(Base):
    __tablename__ = 'game_events'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Тип ивента: 'multiplier' (увеличение выигрыша), 'cashback' (увеличение кэшбека), 'jackpot' (суперприз) и т.д.
    event_type = Column(String(50), nullable=False)
    
    # Параметры ивента (хранятся в JSON)
    # Пример: {"win_multiplier": 3.0, "duration_minutes": 10}
    # или {"cashback_percent": 25, "duration_minutes": 5}
    parameters = Column(Text, nullable=True)  # можно хранить JSON-строку
    
    # Время начала и окончания
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    
    # Активен ли (можно отключить вручную)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
