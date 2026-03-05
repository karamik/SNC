import datetime
import platform
import psutil
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func, and_

from bot.main import async_session_maker, bot, redis_client, game_engine
from bot.models.db import User, Bet, Round, Transaction
from bot.config import config

router = Router()

# Проверка прав администратора
def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Главная панель администратора"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🖥️ Состояние сервера", callback_data="admin_server")],
            [InlineKeyboardButton(text="💰 Финансовая сводка", callback_data="admin_finance")],
            [InlineKeyboardButton(text="👥 Пользователи онлайн", callback_data="admin_online")],
            [InlineKeyboardButton(text="⚙️ Управление", callback_data="admin_manage")],
        ]
    )
    await message.answer("🔐 <b>Панель администратора</b>\nВыберите раздел:", reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    async with async_session_maker() as session:
        # Общая статистика по пользователям
        total_users = await session.scalar(select(func.count(User.id)))
        active_today = await session.scalar(
            select(func.count(User.id)).where(
                func.date(User.last_activity) == datetime.date.today()
            )
        )
        total_balance = await session.scalar(select(func.sum(User.balance))) or 0
        
        # Статистика ставок
        total_bets = await session.scalar(select(func.count(Bet.id))) or 0
        total_bet_amount = await session.scalar(select(func.sum(Bet.amount))) or 0
        total_payout = await session.scalar(select(func.sum(Bet.payout))) or 0
        
        # Статистика раундов
        total_rounds = await session.scalar(select(func.count(Round.id))) or 0
        total_house_profit = await session.scalar(select(func.sum(Round.house_profit))) or 0
        
        # Сегодняшние данные
        today = datetime.date.today()
        today_bets = await session.scalar(
            select(func.count(Bet.id)).where(func.date(Bet.created_at) == today)
        ) or 0
        today_profit = await session.scalar(
            select(func.sum(Round.house_profit)).where(func.date(Round.created_at) == today)
        ) or 0
        
        text = (
            f"📊 <b>Общая статистика</b>\n\n"
            f"👥 Пользователи:\n"
            f"  • Всего: {total_users}\n"
            f"  • Активных сегодня: {active_today}\n"
            f"  • Суммарный баланс: {total_balance} ⭐\n\n"
            f"🎲 Ставки:\n"
            f"  • Всего ставок: {total_bets}\n"
            f"  • Общая сумма ставок: {total_bet_amount} ⭐\n"
            f"  • Выплачено: {total_payout} ⭐\n\n"
            f"💰 Финансы:\n"
            f"  • Прибыль проекта (всего): {total_house_profit} ⭐\n"
            f"  • Прибыль сегодня: {today_profit} ⭐\n"
            f"  • Сегодня ставок: {today_bets}\n\n"
            f"🔄 Раундов проведено: {total_rounds}"
        )
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="admin_back")]]
        ))
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_server")
async def admin_server(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    # Информация о системе
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Информация о Redis
    redis_info = await redis_client.info()
    redis_memory = redis_info.get('used_memory_human', 'N/A')
    redis_connected_clients = redis_info.get('connected_clients', 'N/A')
    
    # Информация о боте
    bot_info = await bot.get_me()
    
    # Состояние игрового движка
    game_engine_status = "🟢 Работает" if game_engine and game_engine.running else "🔴 Остановлен"
    
    text = (
        f"🖥️ <b>Состояние сервера</b>\n\n"
        f"<b>Система:</b>\n"
        f"  • ОС: {platform.system()} {platform.release()}\n"
        f"  • CPU: {cpu_percent}%\n"
        f"  • RAM: {memory.used / 1024**3:.1f}GB / {memory.total / 1024**3:.1f}GB ({memory.percent}%)\n"
        f"  • Диск: {disk.used / 1024**3:.1f}GB / {disk.total / 1024**3:.1f}GB ({disk.percent}%)\n\n"
        f"<b>Redis:</b>\n"
        f"  • Память: {redis_memory}\n"
        f"  • Клиентов: {redis_connected_clients}\n\n"
        f"<b>Бот:</b>\n"
        f"  • @{bot_info.username}\n"
        f"  • ID: {bot_info.id}\n"
        f"  • Игровой движок: {game_engine_status}\n"
    )
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="admin_back")]]
    ))
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_finance")
async def admin_finance(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    async with async_session_maker() as session:
        # Сводка за сегодня
        today = datetime.date.today()
        
        # Доходы: комиссия (house_profit)
        today_income = await session.scalar(
            select(func.sum(Round.house_profit)).where(func.date(Round.created_at) == today)
        ) or 0
        
        # Расходы: выплаты пользователям (выигрыши + кэшбеки)
        today_payout = await session.scalar(
            select(func.sum(Bet.payout)).where(
                and_(
                    func.date(Bet.created_at) == today,
                    Bet.payout > 0
                )
            )
        ) or 0
        
        # Общий объём ставок
        today_bets_amount = await session.scalar(
            select(func.sum(Bet.amount)).where(func.date(Bet.created_at) == today)
        ) or 0
        
        # Топ-10 по балансу
        top_users = await session.execute(
            select(User).order_by(User.balance.desc()).limit(10)
        )
        top_users = top_users.scalars().all()
        top_text = "\n".join([f"{i+1}. {u.first_name or 'Аноним'}: {u.balance} ⭐" for i, u in enumerate(top_users)])
        
        text = (
            f"💰 <b>Финансовая сводка</b>\n\n"
            f"📅 <b>Сегодня ({today}):</b>\n"
            f"  • Объём ставок: {today_bets_amount} ⭐\n"
            f"  • Выплачено игрокам: {today_payout} ⭐\n"
            f"  • Доход проекта: {today_income} ⭐\n"
            f"  • Маржа: {today_income/today_bets_amount*100:.1f}%" if today_bets_amount > 0 else "  • Маржа: 0%\n\n"
            f"\n🏆 <b>Топ-10 по балансу:</b>\n{top_text}"
        )
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="admin_back")]]
        ))
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_online")
async def admin_online(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    # Пользователи онлайн за последние 5 минут
    threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    async with async_session_maker() as session:
        online_users = await session.execute(
            select(User).where(User.last_activity >= threshold).order_by(User.last_activity.desc())
        )
        online_users = online_users.scalars().all()
        
        online_list = "\n".join([
            f"• {u.first_name or 'Аноним'} (@{u.username or 'нет'}) — активен {u.last_activity.strftime('%H:%M:%S')}"
            for u in online_users[:20]  # покажем максимум 20
        ]) or "Нет активных пользователей"
        
        text = (
            f"👥 <b>Пользователи онлайн (последние 5 минут)</b>\n\n"
            f"Всего: {len(online_users)}\n\n"
            f"{online_list}"
        )
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="admin_back")]]
        ))
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_manage")
async def admin_manage(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    text = "⚙️ <b>Управление</b>\n\nВыберите действие:"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Перезапустить игровой движок", callback_data="admin_restart_engine")],
            [InlineKeyboardButton(text="📢 Рассылку", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🎁 Выдать бонус пользователю", callback_data="admin_give_bonus")],
            [InlineKeyboardButton(text="⛔ Забанить пользователя", callback_data="admin_ban")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="admin_back")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_restart_engine")
async def admin_restart_engine(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    if game_engine:
        await game_engine.restart()
        await callback.answer("🔄 Игровой движок перезапущен", show_alert=True)
    else:
        await callback.answer("❌ Игровой движок не инициализирован", show_alert=True)
    
    # Возврат в управление
    await admin_manage(callback)

@router.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await cmd_admin(callback.message)
    await callback.answer()
