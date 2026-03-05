# bot/models/chat.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import datetime

from bot.models.db import Base

class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    username = Column(String(255), nullable=True)  # денормализовано для быстрого доступа
    message = Column(Text, nullable=False)
    room = Column(String(100), default='general')  # можно будет расширить на несколько комнат
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Связь с пользователем (опционально)
    user = relationship("User", backref="chat_messages")
