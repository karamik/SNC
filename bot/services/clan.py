# bot/services/clan.py
import datetime
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from bot.models.db import User
from bot.models.clan import Clan, ClanMember, ClanBattle

logger = logging.getLogger(__name__)

async def create_clan(session: AsyncSession, user_id: int, name: str, tag: str, description: str = "") -> Optional[Clan]:
    """
    Создание нового клана. Пользователь становится лидером.
    Возвращает созданный клан или None, если имя/tag уже заняты.
    """
    # Проверяем уникальность имени и тега
    existing = await session.execute(
        select(Clan).where((Clan.name == name) | (Clan.tag == tag))
    )
    if existing.scalar_one_or_none():
        return None
    
    clan = Clan(
        name=name,
        tag=tag,
        description=description
    )
    session.add(clan)
    await session.flush()
    
    # Добавляем создателя как лидера
    member = ClanMember(
        clan_id=clan.id,
        user_id=user_id,
        role='leader'
    )
    session.add(member)
    
    await session.commit()
    logger.info(f"Clan created: {name} (tag: {tag}) by user {user_id}")
    return clan

async def add_member(session: AsyncSession, clan_id: int, user_id: int, role: str = 'member') -> bool:
    """Добавление пользователя в клан."""
    # Проверяем, не состоит ли уже пользователь в клане
    existing = await session.execute(
        select(ClanMember).where(ClanMember.user_id == user_id)
    )
    if existing.scalar_one_or_none():
        return False
    
    member = ClanMember(
        clan_id=clan_id,
        user_id=user_id,
        role=role
    )
    session.add(member)
    
    # Увеличиваем счётчик участников в клане
    clan = await session.get(Clan, clan_id)
    if clan:
        clan.total_members += 1
    
    await session.commit()
    logger.info(f"User {user_id} added to clan {clan_id}")
    return True

async def remove_member(session: AsyncSession, clan_id: int, user_id: int) -> bool:
    """Удаление пользователя из клана."""
    member = await session.execute(
        select(ClanMember).where(
            and_(ClanMember.clan_id == clan_id, ClanMember.user_id == user_id)
        )
    )
    member = member.scalar_one_or_none()
    if not member:
        return False
    
    await session.delete(member)
    
    clan = await session.get(Clan, clan_id)
    if clan:
        clan.total_members -= 1
    
    await session.commit()
    logger.info(f"User {user_id} removed from clan {clan_id}")
    return True

async def update_clan_stats(session: AsyncSession, clan_id: int, bet_amount: int, win_amount: int, exp_gain: int):
    """
    Обновление статистики клана после ставки члена клана.
    bet_amount – сумма ставки, win_amount – выигрыш (0 если проигрыш).
    """
    clan = await session.get(Clan, clan_id)
    if not clan:
        return
    
    clan.total_bets += 1
    if win_amount > 0:
        clan.total_wins += 1
        # Дополнительно можно добавлять что-то в банк, если нужно
    
    clan.exp += exp_gain
    # Уровень можно пересчитать отдельно
    
    await session.commit()

async def get_clan_rankings(session: AsyncSession, limit: int = 10) -> List[Dict]:
    """Топ-10 кланов по опыту."""
    clans = await session.execute(
        select(Clan).order_by(desc(Clan.exp)).limit(limit)
    )
    result = []
    for clan in clans.scalars().all():
        result.append({
            'id': clan.id,
            'name': clan.name,
            'tag': clan.tag,
            'level': clan.level,
            'exp': clan.exp,
            'members': clan.total_members
        })
    return result

async def start_clan_battle(session: AsyncSession, clan1_id: int, clan2_id: int, duration_hours: int = 24) -> Optional[ClanBattle]:
    """
    Начало битвы между двумя кланами.
    """
    # Проверяем, нет ли уже активной битвы у этих кланов
    existing = await session.execute(
        select(ClanBattle).where(
            and_(
                ClanBattle.is_active == True,
                ((ClanBattle.clan1_id == clan1_id) | (ClanBattle.clan2_id == clan1_id) |
                 (ClanBattle.clan1_id == clan2_id) | (ClanBattle.clan2_id == clan2_id))
            )
        )
    )
    if existing.scalar_one_or_none():
        return None
    
    battle = ClanBattle(
        clan1_id=clan1_id,
        clan2_id=clan2_id,
        end_time=datetime.datetime.utcnow() + datetime.timedelta(hours=duration_hours)
    )
    session.add(battle)
    await session.commit()
    return battle

async def process_clan_battles(session: AsyncSession):
    """
    Проверяет завершённые битвы и определяет победителя.
    Вызывается планировщиком, например, каждый час.
    """
    now = datetime.datetime.utcnow()
    battles = await session.execute(
        select(ClanBattle).where(
            and_(ClanBattle.is_active == True, ClanBattle.end_time <= now)
        )
    )
    battles = battles.scalars().all()
    
    for battle in battles:
        if battle.clan1_score > battle.clan2_score:
            battle.winner_id = battle.clan1_id
        elif battle.clan2_score > battle.clan1_score:
            battle.winner_id = battle.clan2_id
        else:
            battle.winner_id = None  # ничья
        
        battle.is_active = False
        
        # Здесь можно начислить призы победителю и участникам
        # Например, распределить prize_pool
        if battle.prize_pool > 0 and battle.winner_id:
            winner_clan = await session.get(Clan, battle.winner_id)
            if winner_clan:
                # Начислить в банк клана или распределить между членами
                winner_clan.bank += battle.prize_pool
        
        logger.info(f"Battle {battle.id} finished. Winner: {battle.winner_id}")
    
    await session.commit()
