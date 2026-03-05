# api/routers/user.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.core.security import get_current_user_id
from api.dependencies import get_db
from bot.models.db import User, Bet
from bot.config import config

router = APIRouter()

@router.get("/profile")
async def get_profile(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Получить данные профиля пользователя."""
    user = await db.execute(
        select(User).where(User.telegram_id == user_id)
    )
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Базовая статистика
    total_bets = user.total_bets
    total_wins = user.total_wins
    win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
    
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "balance": user.balance,
        "level": user.level,
        "exp": user.exp,
        "total_bets": total_bets,
        "total_wins": total_wins,
        "win_rate": round(win_rate, 1),
        "referral_code": user.referral_code,
        "referrals_count": user.referrals_count,
        "referral_earnings": user.referral_earnings,
        "banner_link": config.BANNER_LINK  # ссылка для баннера
    }

@router.get("/balance")
async def get_balance(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Получить только баланс пользователя."""
    user = await db.execute(
        select(User.balance).where(User.telegram_id == user_id)
    )
    balance = user.scalar_one_or_none()
    if balance is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"balance": balance}

@router.get("/stats")
async def get_stats(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Получить детальную статистику пользователя."""
    user = await db.execute(
        select(User).where(User.telegram_id == user_id)
    )
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "total_bets": user.total_bets,
        "total_wins": user.total_wins,
        "total_losses": user.total_losses,
        "total_refunds": user.total_refunds,
        "total_stars_bet": user.total_stars_bet,
        "total_stars_won": user.total_stars_won,
        "total_stars_lost": user.total_stars_lost,
        "total_stars_refunded": user.total_stars_refunded,
        "level": user.level,
        "exp": user.exp,
    }
