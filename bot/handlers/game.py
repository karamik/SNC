from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select, func

from bot.main import async_session_maker
from bot.models.db import User, Bet
from bot.config import config

router = Router()

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

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Команда /stats - показать игровую статистику пользователя"""
    async with async_session_maker() as session:
        # Получаем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся через /start")
            return
        
        # Получаем общее количество ставок, сумму ставок и т.д.
        # Можно также получить количество выигрышей и проигрышей
        # Используем агрегатные функции
        stats_query = select(
            func.count(Bet.id).label('total_bets'),
            func.sum(Bet.amount).label('total_amount'),
            func.sum(Bet.payout).label('total_payout'),
            func.sum(case((Bet.result == 'win', 1), else_=0)).label('wins'),
            func.sum(case((Bet.result == 'refund', 1), else_=0)).label('refunds'),
            func.sum(case((Bet.result == 'loss', 1), else_=0)).label('losses')
        ).where(Bet.user_id == user.id)
        
        stats_result = await session.execute(stats_query)
        stats = stats_result.first()
        
        total_bets = stats.total_bets or 0
        total_amount = stats.total_amount or 0
        total_payout = stats.total_payout or 0
        wins = stats.wins or 0
        refunds = stats.refunds or 0
        losses = stats.losses or 0
        
        # Расчет профита/убытка
        net = total_payout - total_amount
        
        text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"💰 Баланс: {user.balance} ⭐\n"
            f"🎲 Всего ставок: {total_bets}\n"
            f"💵 Общая сумма ставок: {total_amount} ⭐\n"
            f"🏆 Выигрыши: {wins}\n"
            f"🔄 Кэшбеки: {refunds}\n"
            f"💔 Проигрыши: {losses}\n"
            f"📈 Чистый результат: {net:+} ⭐\n"
            f"📊 Процент побед: {wins/total_bets*100:.1f}%" if total_bets > 0 else "📊 Процент побед: 0%"
        )
        
        await message.answer(text)

@router.message(Command("rules"))
async def cmd_rules(message: types.Message):
    """Команда /rules - правила игры"""
    text = (
        "<b>Правила игры «Звёздный удвоитель»</b>\n\n"
        "1. Каждую минуту проходит раунд.\n"
        "2. Ты можешь сделать ставку: 100⭐, 1000⭐ или 5000⭐.\n"
        "3. В каждом раунде 40% игроков выигрывают x2 от ставки.\n"
        "4. 50% игроков получают кэшбек 10% от ставки.\n"
        "5. Остальные 10% ставок идут в доход проекта (это позволяет нам платить призы и развиваться).\n"
        "6. Также ты получаешь опыт за ставки, повышаешь уровень и открываешь бонусы.\n"
        "7. Ежедневный бонус — заходи каждый день и получай звёзды.\n"
        "8. Приводи друзей по реферальной ссылке и получай 10% от их ставок.\n\n"
        "Удачи! ✨"
    )
    await message.answer(text)
