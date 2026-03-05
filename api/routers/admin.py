# api/routers/admin.py

import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional

from api.core.security import get_current_user_id
from api.dependencies import get_db, get_redis
from bot.models.db import User, Bet, Round, Transaction
from bot.config import config

router = APIRouter()

async def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.get("/stats")
async def admin_stats(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Общая статистика проекта (только для админов)."""
    if not await is_admin(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Общая статистика
    total_users = await db.scalar(select(func.count(User.id)))
    total_balance = await db.scalar(select(func.sum(User.balance))) or 0
    
    total_bets = await db.scalar(select(func.count(Bet.id))) or 0
    total_bet_amount = await db.scalar(select(func.sum(Bet.amount))) or 0
    total_payout = await db.scalar(select(func.sum(Bet.payout))) or 0
    
    total_rounds = await db.scalar(select(func.count(Round.id))) or 0
    total_profit = await db.scalar(select(func.sum(Round.house_profit))) or 0
    
    # Сегодня
    today = datetime.date.today()
    today_start = datetime.datetime.combine(today, datetime.time.min)
    today_end = datetime.datetime.combine(today, datetime.time.max)
    
    today_users = await db.scalar(
        select(func.count(User.id)).where(
            and_(User.last_activity >= today_start, User.last_activity <= today_end)
        )
    ) or 0
    
    today_bets = await db.scalar(
        select(func.count(Bet.id)).where(
            and_(Bet.created_at >= today_start, Bet.created_at <= today_end)
        )
    ) or 0
    
    today_profit = await db.scalar(
        select(func.sum(Round.house_profit)).where(
            and_(Round.created_at >= today_start, Round.created_at <= today_end)
        )
    ) or 0
    
    return {
        "total_users": total_users,
        "active_today": today_users,
        "total_balance": total_balance,
        "total_bets": total_bets,
        "total_bet_amount": total_bet_amount,
        "total_payout": total_payout,
        "total_rounds": total_rounds,
        "total_profit": total_profit,
        "today_bets": today_bets,
        "today_profit": today_profit,
    }

@router.get("/users")
async def admin_users(
    skip: int = 0,
    limit: int = 100,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Список пользователей (только для админов)."""
    if not await is_admin(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    users = await db.execute(
        select(User).order_by(User.id).offset(skip).limit(limit)
    )
    users_list = []
    for u in users.scalars().all():
        users_list.append({
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "first_name": u.first_name,
            "balance": u.balance,
            "level": u.level,
            "total_bets": u.total_bets,
            "registered_at": u.registered_at.isoformat() if u.registered_at else None,
            "last_activity": u.last_activity.isoformat() if u.last_activity else None,
            "is_banned": u.is_banned,
        })
    return {"users": users_list, "total": len(users_list)}

@router.post("/users/{telegram_id}/ban")
async def admin_ban_user(
    telegram_id: int,
    ban: bool = True,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Забанить/разбанить пользователя."""
    if not await is_admin(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    user = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_banned = ban
    await db.commit()
    return {"status": "ok", "banned": ban}

@router.post("/users/{telegram_id}/add_balance")
async def admin_add_balance(
    telegram_id: int,
    amount: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Начислить/списать баланс пользователю."""
    if not await is_admin(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    user = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.balance += amount
    # Запись транзакции
    trans = Transaction(
        user_id=user.id,
        amount=amount,
        type='admin',
        description=f"Административное начисление"
    )
    db.add(trans)
    await db.commit()
    return {"status": "ok", "new_balance": user.balance}

@router.get("/server_status")
async def admin_server_status(
    user_id: int = Depends(get_current_user_id),
    redis = Depends(get_redis)
):
    """Статус сервера и Redis."""
    if not await is_admin(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Проверяем Redis
    try:
        redis_ping = await redis.ping()
        redis_ok = redis_ping
    except:
        redis_ok = False
    
    # Информация о Redis
    redis_info = {}
    if redis_ok:
        try:
            info = await redis.info()
            redis_info = {
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            }
        except:
            pass
    
    return {
        "redis_ok": redis_ok,
        "redis_info": redis_info,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
