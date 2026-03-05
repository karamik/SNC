import random
import string
import datetime
from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.main import async_session_maker, bot
from bot.models.db import User, Transaction
from bot.config import config

router = Router()

def generate_referral_code(length: int = 8) -> str:
    """Генерация уникального реферального кода"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandStart):
    """Обработчик команды /start с поддержкой реферального параметра"""
    args = command.args
    referrer_id = None
    
    # Проверяем, есть ли реферальный код в ссылке
    if args and args.startswith('ref_'):
        try:
            code = args[4:]  # убираем 'ref_'
            # Ищем пользователя с таким кодом
            async with async_session_maker() as session:
                result = await session.execute(
                    select(User).where(User.referral_code == code)
                )
                referrer = result.scalar_one_or_none()
                if referrer:
                    referrer_id = referrer.telegram_id
        except Exception:
            pass
    
    # Регистрируем/обновляем пользователя
    async with async_session_maker() as session:
        # Ищем существующего
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        now = datetime.datetime.utcnow()
        
        if not user:
            # Новый пользователь
            referral_code = generate_referral_code()
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                referral_code=referral_code,
                referred_by=referrer_id,
                registered_at=now,
                last_activity=now,
                balance=100  # Приветственный бонус 100 звёзд
            )
            session.add(user)
            await session.flush()
            
            # Записываем транзакцию приветственного бонуса
            transaction = Transaction(
                user_id=user.id,
                amount=100,
                type='welcome_bonus',
                description='Приветственный бонус'
            )
            session.add(transaction)
            
            # Если есть пригласивший, начисляем ему бонус
            if referrer_id:
                # Находим пригласившего по telegram_id
                ref_result = await session.execute(
                    select(User).where(User.telegram_id == referrer_id)
                )
                referrer_user = ref_result.scalar_one_or_none()
                if referrer_user:
                    referrer_user.balance += 50
                    referrer_user.referrals_count += 1
                    referrer_user.referral_earnings += 50
                    
                    # Транзакция для пригласившего
                    ref_trans = Transaction(
                        user_id=referrer_user.id,
                        amount=50,
                        type='referral_bonus',
                        description=f'За приглашение пользователя {message.from_user.id}'
                    )
                    session.add(ref_trans)
            
            await session.commit()
            
            await message.answer(
                f"✨ <b>Добро пожаловать в Звёздный удвоитель!</b>\n\n"
                f"🎁 Ты получил <b>100 звёзд</b> на первый счёт!\n"
                f"🔗 Твой реферальный код: <code>{referral_code}</code>\n"
                f"👥 Приводи друзей и получай бонусы.\n\n"
                f"Используй кнопку ниже, чтобы открыть игру."
            )
        else:
            # Пользователь уже есть, обновляем активность
            user.last_activity = now
            await session.commit()
            
            await message.answer(
                f"С возвращением, {user.first_name or 'игрок'}!\n"
                f"Твой баланс: <b>{user.balance} ⭐</b>\n\n"
                f"Нажми кнопку, чтобы играть."
            )
    
    # Кнопка для открытия Mini App
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🚀 Играть",
                web_app=WebAppInfo(url=f"{config.API_BASE_URL}/static/index.html")
            )]
        ]
    )
    await message.answer("👇 Запускай Mini App и делай ставки!", reply_markup=keyboard)

@router.message(Command("game"))
async def cmd_game(message: types.Message):
    """Команда /game - открыть игру"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎮 Открыть игру",
                web_app=WebAppInfo(url=f"{config.API_BASE_URL}/static/index.html")
            )]
        ]
    )
    await message.answer("👇 Нажми кнопку, чтобы запустить игру:", reply_markup=keyboard)
