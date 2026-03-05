# bot/services/events.py
import json
import datetime
import logging
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from bot.models.event import GameEvent

logger = logging.getLogger(__name__)

class EventManager:
    """Менеджер игровых событий (ивентов). Загружает активные ивенты и применяет их эффекты."""
    
    def __init__(self, session_maker):
        self.session_maker = session_maker
        self.active_events_cache: Dict[int, Dict[str, Any]] = {}
        self.last_refresh = None

    async def refresh_active_events(self):
        """Обновляет кэш активных ивентов из базы данных."""
        now = datetime.datetime.utcnow()
        async with self.session_maker() as session:
            result = await session.execute(
                select(GameEvent).where(
                    and_(
                        GameEvent.start_time <= now,
                        GameEvent.end_time >= now,
                        GameEvent.is_active == True
                    )
                )
            )
            events = result.scalars().all()
            
            new_cache = {}
            for event in events:
                try:
                    params = json.loads(event.parameters) if event.parameters else {}
                except json.JSONDecodeError:
                    params = {}
                    logger.error(f"Failed to parse parameters for event {event.id}")
                
                new_cache[event.id] = {
                    'id': event.id,
                    'type': event.event_type,
                    'params': params,
                    'start_time': event.start_time,
                    'end_time': event.end_time
                }
            
            self.active_events_cache = new_cache
            self.last_refresh = now
            logger.info(f"Active events refreshed: {len(self.active_events_cache)} events")

    def get_active_events(self) -> Dict[int, Dict[str, Any]]:
        """Возвращает текущие активные ивенты."""
        return self.active_events_cache

    def apply_event_modifiers(self, win_multiplier: float, cashback_percent: int) -> Tuple[float, int]:
        """
        Применяет активные ивенты к базовым параметрам раунда.
        
        Args:
            win_multiplier: базовый множитель выигрыша (обычно 2.0)
            cashback_percent: базовый процент кэшбека (обычно 10)
            
        Returns:
            tuple: (модифицированный win_multiplier, модифицированный cashback_percent)
        """
        modified_win = win_multiplier
        modified_cashback = cashback_percent
        
        for event_data in self.active_events_cache.values():
            if event_data['type'] == 'multiplier':
                # Увеличиваем множитель выигрыша
                extra = event_data['params'].get('win_multiplier', 1.0)
                modified_win *= extra
                logger.debug(f"Applied multiplier event: win_multiplier now {modified_win}")
            
            elif event_data['type'] == 'cashback':
                # Изменяем процент кэшбека
                new_cashback = event_data['params'].get('cashback_percent')
                if new_cashback is not None:
                    modified_cashback = new_cashback
                    logger.debug(f"Applied cashback event: cashback now {modified_cashback}%")
            
            elif event_data['type'] == 'jackpot':
                # Джекпот обрабатывается отдельно в логике раунда (пока не реализовано)
                pass
            
            # Другие типы можно добавить позже
        
        return modified_win, modified_cashback

    async def check_and_apply_special(self, user_id: int, bet_amount: int) -> Optional[Dict]:
        """
        Проверяет, не активировался ли для пользователя специальный ивент (например, комета).
        Возвращает словарь с эффектом, если применимо.
        """
        # Здесь можно реализовать логику для случайных ивентов, затрагивающих конкретного пользователя
        # Например, с вероятностью 1% в раунде может выпасть "комета" для случайного игрока
        # Пока оставим заглушку
        return None
