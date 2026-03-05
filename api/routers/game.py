# api/routers/game.py

import json
import time
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel

from api.core.security import get_current_user_id
from api.dependencies import get_db, get_redis
from bot.models.db import User, Bet, Transaction
from bot.config import config

router = APIRouter()

class PlaceBetRequest(BaseModel):
    amount: int  # 100, 1000, 5000

class BetResponse(BaseModel):
    status: str
    new_balance: int
    message: Optional[str] = None

@router.post("/place_bet", response_model=BetResponse)
async def place_bet(
    request: Request,
    bet_req: PlaceBetRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
):
    """
    Разместить ставку в текущем раунде.
    """
    # Проверяем допустимость суммы ставки
    if bet_req.amount not in [100, 1000, 5000]:
        raise HTTPException(status_code=400, detail="Invalid bet amount")
    
    # Получаем пользователя
    user = await db.execute(
        select(User).where(User.telegram_id == user_id)
    )
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")
    
    if user.balance < bet_req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Списание баланса (пессимистическая блокировка не требуется, т.к. используем Redis и затем БД)
    user.balance -= bet_req.amount
    await db.commit()
    
    # Сохраняем ставку в Redis для текущей минуты
    now = time.time()
    # Ключ: round:<timestamp начала минуты>:bets
    round_timestamp = int(now // 60 * 60)
    round_key = f"round:{round_timestamp}:bets"
    
    bet_data = {
        "user_id": user_id,
        "amount": bet_req.amount,
        "timestamp": now
    }
    await redis.zadd(round_key, {json.dumps(bet_data): now})
    await redis.expire(round_key, 120)  # храним 2 минуты на случай задержек
    
    # Логируем транзакцию списания
    transaction = Transaction(
        user_id=user.id,
        amount=-bet_req.amount,
        type='bet',
        description='Ставка в раунде'
    )
    db.add(transaction)
    await db.commit()
    
    # Проверяем, не пора ли показать баннер (если баланс стал меньше порога)
    show_banner = user.balance < 500  # например, если меньше 500 звёзд
    
    return BetResponse(
        status="ok",
        new_balance=user.balance,
        message="Ставка принята!" + (" Хочешь ещё звёзд? 👆" if show_banner else "")
    )

@router.get("/round_info")
async def round_info(redis = Depends(get_redis)):
    """
    Получить информацию о текущем раунде: время до конца, количество ставок.
    """
    now = time.time()
    current_minute = int(now // 60)
    next_round_time = (current_minute + 1) * 60
    time_left = next_round_time - now
    
    round_key = f"round:{current_minute * 60}:bets"
    bets_count = await redis.zcard(round_key)
    
    return {
        "time_left": time_left,
        "bets_count": bets_count,
        "current_minute": current_minute
    }

@router.get("/last_wins")
async def last_wins(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """
    Получить последние крупные выигрыши для ленты.
    """
    # Выбираем последние выигрыши с суммой > 0
    result = await db.execute(
        select(Bet)
        .where(Bet.payout > 0)
        .order_by(desc(Bet.created_at))
        .limit(limit)
    )
    bets = result.scalars().all()
    
    wins_list = []
    for bet in bets:
        user = await db.get(User, bet.user_id)
        if user:
            wins_list.append({
                "username": user.first_name or f"ID{user.telegram_id}",
                "amount": bet.payout,
                "time": bet.created_at.isoformat()
            })
    
    return {"wins": wins_list}
