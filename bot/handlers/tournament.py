import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func, and_

from bot.main import async_session_maker
from bot.models.db import User, Tournament, TournamentParticipant

router = Router()

@router.message(Command("tournaments"))
async def cmd_tournaments(message: types.Message):
    """Список активных турниров"""
    async with async_session_maker() as session:
        now = datetime.datetime.utcnow()
        # Активные турниры (текущие)
        active_tournaments = await session.execute(
            select(Tournament).where(
                and_(
                    Tournament.start_time <= now,
                    Tournament.end_time >= now,
                    Tournament.is_active == True
                )
            ).order_by(Tournament.end_time)
        )
        active = active_tournaments.scalars().all()
        
        # Предстоящие турниры
        upcoming_tournaments = await session.execute(
            select(Tournament).where(
                and_(
                    Tournament.start_time > now,
                    Tournament.is_active == True
                )
            ).order_by(Tournament.start_time)
        )
        upcoming = upcoming_tournaments.scalars().all()
        
        text = "🏆 <b>Турниры</b>\n\n"
        
        if active:
            text += "<b>🔥 Активные:</b>\n"
            for t in active:
                time_left = t.end_time - now
                hours = time_left.seconds // 3600
                minutes = (time_left.seconds % 3600) // 60
                text += f"• {t.name} — до окончания {hours}ч {minutes}м\n"
                text += f"  Призовой фонд: {t.prize_pool} ⭐\n"
                # Кнопка будет ниже
            text += "\n"
        else:
            text += "Нет активных турниров.\n\n"
        
        if upcoming:
            text += "<b>⏳ Предстоящие:</b>\n"
            for t in upcoming[:3]:
                start_str = t.start_time.strftime("%d.%m %H:%M")
                text += f"• {t.name} — старт {start_str}\n"
            text += "\n"
        
        # Кнопки для каждого активного турнира
        keyboard = []
        for t in active:
            keyboard.append([InlineKeyboardButton(
                text=f"📊 {t.name} — таблица",
                callback_data=f"tournament_view_{t.id}"
            )])
        
        if active:
            keyboard.append([InlineKeyboardButton(text="🏁 Моё участие", callback_data="tournament_my")])
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(lambda c: c.data.startswith("tournament_view_"))
async def tournament_view(callback: types.CallbackQuery):
    """Просмотр конкретного турнира и таблицы лидеров"""
    tournament_id = int(callback.data.split("_")[2])
    
    async with async_session_maker() as session:
        tournament = await session.get(Tournament, tournament_id)
        if not tournament:
            await callback.answer("Турнир не найден", show_alert=True)
            return
        
        # Получаем топ-10 участников
        top_participants = await session.execute(
            select(TournamentParticipant)
            .where(TournamentParticipant.tournament_id == tournament_id)
            .order_by(TournamentParticipant.score.desc())
            .limit(10)
        )
        top = top_participants.scalars().all()
        
        # Текущий пользователь
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        
        # Участие пользователя
        user_participation = None
        if user:
            user_part = await session.execute(
                select(TournamentParticipant)
                .where(
                    and_(
                        TournamentParticipant.tournament_id == tournament_id,
                        TournamentParticipant.user_id == user.id
                    )
                )
            )
            user_participation = user_part.scalar_one_or_none()
        
        now = datetime.datetime.utcnow()
        status = "🟢 Идёт" if tournament.start_time <= now <= tournament.end_time else "🔴 Завершён"
        
        text = (
            f"🏆 <b>{tournament.name}</b>\n\n"
            f"{tournament.description}\n\n"
            f"📅 Статус: {status}\n"
            f"⏳ Начало: {tournament.start_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Конец: {tournament.end_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"💰 Призовой фонд: {tournament.prize_pool} ⭐\n"
            f"🎲 Минимальная ставка: {tournament.min_bet} ⭐\n\n"
        )
        
        if top:
            text += "📊 <b>Топ-10 участников:</b>\n"
            for i, p in enumerate(top, 1):
                user_name = (await session.get(User, p.user_id)).first_name or f"Игрок {p.user_id}"
                text += f"{i}. {user_name} — {p.score} очков\n"
        else:
            text += "Пока нет участников.\n"
        
        if user_participation:
            text += f"\n📍 Твоё место: {user_participation.rank or 'не определено'}, очков: {user_participation.score}"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀ Назад к турнирам", callback_data="tournaments_back")],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"tournament_view_{tournament_id}")]
            ]
        )
        
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data == "tournament_my")
async def tournament_my(callback: types.CallbackQuery):
    """Мои турниры (участие)"""
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала зарегистрируйся", show_alert=True)
            return
        
        # Находим все участия пользователя в активных турнирах
        now = datetime.datetime.utcnow()
        participations = await session.execute(
            select(TournamentParticipant, Tournament)
            .join(Tournament, TournamentParticipant.tournament_id == Tournament.id)
            .where(
                and_(
                    TournamentParticipant.user_id == user.id,
                    Tournament.is_active == True,
                    Tournament.start_time <= now,
                    Tournament.end_time >= now
                )
            )
        )
        participations = participations.all()
        
        if not participations:
            await callback.message.edit_text(
                "Ты не участвуешь ни в одном активном турнире.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="tournaments_back")]]
                )
            )
            await callback.answer()
            return
        
        text = "🏁 <b>Мои турниры</b>\n\n"
        for p, t in participations:
            text += f"• {t.name} — очков: {p.score}, место: {p.rank or 'не определено'}\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="tournaments_back")]]
            )
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "tournaments_back")
async def tournaments_back(callback: types.CallbackQuery):
    await cmd_tournaments(callback.message)
    await callback.answer()
