from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from bot.main import async_session_maker, bot
from bot.models.db import User, Transaction

router = Router()

@router.message(Command("referral"))
async def cmd_referral(message: types.Message):
    """Команда /referral - информация о реферальной системе"""
    async with async_session_maker() as session:
        # Получаем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся через /start")
            return
        
        # Получаем список рефералов (по referred_by)
        referrals = await session.execute(
            select(User).where(User.referred_by == message.from_user.id).order_by(User.registered_at.desc())
        )
        referrals = referrals.scalars().all()
        
        # Суммарный заработок с рефералов
        total_earned = user.referral_earnings
        
        bot_username = (await bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"
        
        text = (
            f"👥 <b>Реферальная программа</b>\n\n"
            f"Приводи друзей и получай 10% от их ставок навсегда!\n\n"
            f"📊 <b>Твоя статистика</b>\n"
            f"• Приглашено: {user.referrals_count}\n"
            f"• Заработано: {total_earned} ⭐\n\n"
            f"🔗 <b>Твоя ссылка:</b>\n"
            f"<code>{referral_link}</code>\n\n"
            f"👇 Список твоих рефералов:"
        )
        
        if referrals:
            ref_list = ""
            for i, ref in enumerate(referrals[:10], 1):
                ref_list += f"{i}. {ref.first_name or 'Аноним'} (@{ref.username or 'нет'}) — {ref.total_stars_bet} ⭐ ставок\n"
            text += "\n\n" + ref_list
            if len(referrals) > 10:
                text += f"\n... и ещё {len(referrals) - 10}"
        else:
            text += "\n\nПока никого нет. Поделись ссылкой с друзьями!"
        
        # Кнопка для копирования ссылки (в ТГ можно сделать через callback)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Копировать ссылку", callback_data="ref_copy")],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="ref_refresh")]
            ]
        )
        
        await message.answer(text, reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "ref_copy")
async def ref_copy(callback: types.CallbackQuery):
    """Подсказка, как скопировать ссылку (можно вывести в уведомлении)"""
    await callback.answer("Выдели ссылку выше и скопируй её", show_alert=False)

@router.callback_query(lambda c: c.data == "ref_refresh")
async def ref_refresh(callback: types.CallbackQuery):
    """Обновить информацию о рефералах"""
    await cmd_referral(callback.message)
    await callback.answer()
