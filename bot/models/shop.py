# bot/models/shop.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
import datetime

from bot.models.db import Base

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
    
    # Связи (опционально, если есть таблица покупок)
    purchases = relationship("Purchase", back_populates="item")
