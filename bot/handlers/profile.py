import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update, func

from bot.main import async_session_maker
from bot.models.db import User, DailyBonus, Transaction
from bot.config import config

router = Router()

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Команда /profile - показать профиль пользователя"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся через /start")
            return
        
        # Вычисляем следующий уровень
        next_level_exp = user.level * 1000  # простой расчёт: 1000 опыта на уровень
        exp_progress = min(100, int((user.exp % 1000) / 10)) if next_level_exp else 0
        
        # Создаём прогресс-бар
        progress_bar = "▓" * (exp_progress // 10) + "░" * (10 - (exp_progress // 10))
        
        text = (
            f"👤 <b>Профиль</b>\n\n"
            f"🆔 ID: {user.telegram_id}\n"
            f"📛 Имя: {user.first_name or 'Не указано'}\n"
            f"⭐ Баланс: {user.balance}\n"
            f"📊 Уровень: {user.level}\n"
            f"✨ Опыт: {user.exp}/{user.level * 1000}\n"
            f"{progress_bar}\n\n"
            f"📈 Статистика:\n"
            f"🎲 Ставок: {user.total_bets}\n"
            f"🏆 Побед: {user.total_wins}\n"
            f"🔄 Кэшбеков: {user.total_refunds}\n"
            f"💔 Поражений: {user.total_losses}\n"
            f"👥 Рефералов: {user.referrals_count}\n"
            f"🔗 Код: <code>{user.referral_code}</code>\n"
        )
        
        # Кнопки
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📅 Ежедневный бонус", callback_data="daily_bonus")],
                [InlineKeyboardButton(text="👥 Рефералы", callback_data="referral_info")],
                [InlineKeyboardButton(text="🏆 Достижения", callback_data="achievements")]
            ]
        )
        
        await message.answer(text, reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "daily_bonus")
async def daily_bonus_callback(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку ежедневного бонуса"""
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        # Получаем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка: пользователь не найден", show_alert=True)
            return
        
        # Проверяем, получал ли бонус сегодня
        today = datetime.datetime.utcnow().date()
        # Ищем запись о бонусе за сегодня
        bonus_query = select(DailyBonus).where(
            DailyBonus.user_id == user.id,
            func.date(DailyBonus.bonus_date) == today
        )
        bonus_result = await session.execute(bonus_query)
        existing = bonus_result.scalar_one_or_none()
        
        if existing:
            await callback.answer("Ты уже получил бонус сегодня! Завтра приходи.", show_alert=True)
            return
        
        # Вычисляем сумму бонуса: базовая 50 + 10 * streak
        # Получаем последний бонус для определения streak
        last_bonus_query = select(DailyBonus).where(
            DailyBonus.user_id == user.id
        ).order_by(DailyBonus.bonus_date.desc()).limit(1)
        last_bonus_result = await session.execute(last_bonus_query)
        last_bonus = last_bonus_result.scalar_one_or_none()
        
        streak = 1
        if last_bonus:
            # Проверяем, был ли бонус вчера
            yesterday = today - datetime.timedelta(days=1)
            if last_bonus.bonus_date.date() == yesterday:
                streak = last_bonus.streak + 1
            else:
                streak = 1
        
        bonus_amount = 50 + (streak - 1) * 10  # 50, 60, 70, ...
        if bonus_amount > 200:
            bonus_amount = 200  # максимум 200
        
        # Начисляем бонус
        user.balance += bonus_amount
        user.exp += bonus_amount  // 2  # немного опыта
        
        # Записываем бонус
        daily_bonus = DailyBonus(
            user_id=user.id,
            bonus_date=datetime.datetime.utcnow(),
            amount=bonus_amount,
            streak=streak
        )
        session.add(daily_bonus)
        
        # Транзакция
        trans = Transaction(
            user_id=user.id,
            amount=bonus_amount,
            type='daily_bonus',
            description=f'Ежедневный бонус (день {streak})'
        )
        session.add(trans)
        
        await session.commit()
        
        await callback.message.edit_text(
            f"✅ Ты получил ежедневный бонус!\n"
            f"💰 {bonus_amount} ⭐ добавлено на счёт.\n"
            f"🔥 Текущая серия: {streak} дней.\n"
            f"Завтра бонус будет больше!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="👤 Назад в профиль", callback_data="back_to_profile")]
                ]
            )
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "referral_info")
async def referral_info_callback(callback: types.CallbackQuery):
    """Информация о реферальной системе"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return
        
        text = (
            f"👥 <b>Реферальная программа</b>\n\n"
            f"Твой код: <code>{user.referral_code}</code>\n"
            f"Приглашено друзей: {user.referrals_count}\n"
            f"Заработано с рефералов: {user.referral_earnings} ⭐\n\n"
            f"📋 <b>Условия:</b>\n"
            f"• За каждого приглашённого друга ты получаешь 50 ⭐ сразу\n"
            f"• Ты получаешь 5% от всех ставок друзей\n"
            f"• Твои друзья получают 100 ⭐ приветственного бонуса\n\n"
            f"🔗 Твоя ссылка для приглашения:\n"
            f"<code>https://t.me/{(await callback.bot.get_me()).username}?start=ref_{user.referral_code}</code>"
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=f"Играй со мной! Звёздный удвоитель: https://t.me/{(await callback.bot.get_me()).username}?start=ref_{user.referral_code}")],
                [InlineKeyboardButton(text="👤 Назад в профиль", callback_data="back_to_profile")]
            ]
        )
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data == "achievements")
async def achievements_callback(callback: types.CallbackQuery):
    """Достижения пользователя"""
    # Можно реализовать позже
    await callback.answer("Раздел в разработке", show_alert=True)

@router.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile_callback(callback: types.CallbackQuery):
    """Возврат в профиль"""
    # Просто вызываем команду /profile заново (можно отредактировать сообщение)
    await cmd_profile(callback.message)
    await callback.answer()
