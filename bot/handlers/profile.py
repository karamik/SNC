# bot/handlers/profile.py

import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from bot.main import async_session_maker, bot
from bot.models.db import User, Bet, Transaction, DailyBonus, Purchase
from bot.models.shop import ShopItem
from bot.models.booster import ActiveBooster
from bot.services.leveling import get_level_info, exp_for_next_level

router = Router()

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Просмотр профиля пользователя"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся через /start")
            return
        
        # Статистика из модели
        total_bets = user.total_bets
        total_wins = user.total_wins
        total_losses = user.total_losses
        total_refunds = user.total_refunds
        
        win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
        
        # Информация об уровне
        level = user.level
        exp = user.exp
        next_exp = exp_for_next_level(level)
        exp_progress = exp / next_exp * 100 if next_exp > 0 else 0
        
        # Реферальная информация
        referrals = user.referrals_count
        referral_earnings = user.referral_earnings
        
        # Последний ежедневный бонус
        last_bonus = user.last_daily_bonus
        bonus_status = "✅ Доступен" if not last_bonus or (datetime.datetime.utcnow() - last_bonus).days >= 1 else "❌ Уже получен сегодня"
        
        # Активные бустеры
        boosters = await session.execute(
            select(ActiveBooster).where(ActiveBooster.user_id == user.id)
        )
        boosters = boosters.scalars().all()
        boosters_text = ""
        if boosters:
            boosters_text = "\n<b>Активные бустеры:</b>\n"
            for b in boosters:
                if b.booster_type == 'win_chance':
                    boosters_text += f"• Удача +{(b.multiplier-1)*100:.0f}%"
                elif b.booster_type == 'insurance':
                    boosters_text += f"• Страховка"
                elif b.booster_type == 'exp_boost':
                    boosters_text += f"• Опыт x{b.multiplier}"
                if b.expires_at:
                    time_left = (b.expires_at - datetime.datetime.utcnow()).seconds // 60
                    boosters_text += f" (ещё {time_left} мин)"
                if b.uses_left:
                    boosters_text += f" (осталось {b.uses_left} раз)"
                boosters_text += "\n"
        
        # Купленные титулы (последний активный)
        purchases = await session.execute(
            select(Purchase).where(
                Purchase.user_id == user.id
            ).order_by(Purchase.purchased_at.desc())
        )
        purchases = purchases.scalars().all()
        active_title = None
        for p in purchases:
            item = await session.get(ShopItem, p.item_id)
            if item and item.item_type == 'title':
                active_title = item.item_data.get('title', '')
                break
        
        title_text = f"\n👑 <b>Титул:</b> {active_title}" if active_title else ""
        
        text = (
            f"👤 <b>Профиль игрока</b>{title_text}\n\n"
            f"🆔 ID: {user.telegram_id}\n"
            f"📛 Имя: {user.first_name or 'Не указано'}\n"
            f"⭐ Баланс: {user.balance}\n\n"
            f"📊 <b>Прогресс</b>\n"
            f"Уровень: {level}\n"
            f"Опыт: {exp}/{next_exp} ({exp_progress:.1f}%)\n\n"
            f"🎲 <b>Статистика</b>\n"
            f"Всего ставок: {total_bets}\n"
            f"🏆 Побед: {total_wins}\n"
            f"🔄 Кэшбеков: {total_refunds}\n"
            f"💔 Поражений: {total_losses}\n"
            f"📈 Процент побед: {win_rate:.1f}%\n\n"
            f"👥 <b>Рефералы</b>\n"
            f"Приглашено: {referrals}\n"
            f"Заработано: {referral_earnings} ⭐\n\n"
            f"🎁 <b>Ежедневный бонус</b>\n"
            f"{bonus_status}\n"
            f"{boosters_text}\n"
            f"🔗 Твоя реферальная ссылка:\n"
            f"<code>https://t.me/{(await bot.get_me()).username}?start=ref_{user.referral_code}</code>"
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="profile_details")],
                [InlineKeyboardButton(text="🎁 Забрать ежедневный бонус", callback_data="daily_bonus_claim")],
                [InlineKeyboardButton(text="🏆 Достижения", callback_data="profile_achievements")],
            ]
        )
        
        await message.answer(text, reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "profile_details")
async def profile_details(callback: types.CallbackQuery):
    """Детальная статистика ставок"""
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return
        
        total_stars_bet = user.total_stars_bet
        total_stars_won = user.total_stars_won
        total_stars_lost = user.total_stars_lost
        total_stars_refunded = user.total_stars_refunded
        
        net_profit = total_stars_won + total_stars_refunded - total_stars_bet
        
        bets_by_amount = await session.execute(
            select(Bet.amount, func.count(Bet.id), func.sum(Bet.payout))
            .where(Bet.user_id == user.id)
            .group_by(Bet.amount)
        )
        bets_by_amount = bets_by_amount.all()
        
        amount_text = ""
        for amount, count, payout in bets_by_amount:
            amount_text += f"  {amount}⭐: {count} раз, выплат {payout or 0}⭐\n"
        
        text = (
            f"📊 <b>Детальная статистика</b>\n\n"
            f"💰 Общая сумма ставок: {total_stars_bet} ⭐\n"
            f"🏆 Выиграно: {total_stars_won} ⭐\n"
            f"🔄 Кэшбек: {total_stars_refunded} ⭐\n"
            f"💔 Проиграно: {total_stars_lost} ⭐\n"
            f"📈 Чистый результат: {net_profit:+} ⭐\n\n"
            f"🎲 <b>Ставки по номиналам</b>\n"
            f"{amount_text}"
        )
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="profile_back")]]
        ))
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: types.CallbackQuery):
    """Возврат в профиль"""
    await cmd_profile(callback.message)
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_achievements")
async def profile_achievements(callback: types.CallbackQuery):
    """Переход к достижениям"""
    await callback.message.answer("/achievements")
    await callback.answer()
