# bot/handlers/clan.py
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, and_

from bot.main import async_session_maker
from bot.models.db import User
from bot.models.clan import Clan, ClanMember, ClanBattle
from bot.services.clan import create_clan, add_member, remove_member, get_clan_rankings, start_clan_battle

router = Router()

# Вспомогательная функция для получения клана пользователя
async def get_user_clan(user_id: int):
    async with async_session_maker() as session:
        member = await session.execute(
            select(ClanMember).where(ClanMember.user_id == user_id)
        )
        member = member.scalar_one_or_none()
        if member:
            clan = await session.get(Clan, member.clan_id)
            return clan, member
        return None, None

@router.message(Command("clan"))
async def cmd_clan(message: types.Message):
    """Информация о своём клане"""
    clan, member = await get_user_clan(message.from_user.id)
    if not clan:
        await message.answer("❌ Ты не состоишь в клане. Используй /clan_create или /clan_join")
        return
    
    text = (
        f"🏰 <b>{clan.name}</b> [{clan.tag}]\n\n"
        f"{clan.description or ''}\n"
        f"📊 Уровень: {clan.level} (опыт: {clan.exp})\n"
        f"👥 Участников: {clan.total_members}\n"
        f"💰 Банк клана: {clan.bank} ⭐\n"
        f"🎲 Всего ставок: {clan.total_bets}\n"
        f"🏆 Побед: {clan.total_wins}\n\n"
        f"Твоя роль: {member.role}\n"
        f"Твой вклад: {member.contributed_stars} ⭐, {member.contributed_exp} опыта"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Участники", callback_data="clan_members")],
            [InlineKeyboardButton(text="💰 Банк", callback_data="clan_bank_menu")],
            [InlineKeyboardButton(text="⚔️ Битвы", callback_data="clan_battles")]
        ]
    )
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("clan_create"))
async def cmd_clan_create(message: types.Message):
    """Создание клана (пока просто заглушка, потом можно через FSM)"""
    # Проверяем, не состоит ли уже в клане
    clan, _ = await get_user_clan(message.from_user.id)
    if clan:
        await message.answer("❌ Ты уже состоишь в клане. Выйди из него, чтобы создать новый.")
        return
    
    # Для простоты сделаем создание через аргументы команды: /clan_create Название ТЕГ
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /clan_create <название> <тег>\nНапример: /clan_create Воины Света [WAR]")
        return
    
    name = args[1]
    tag = args[2].strip('[]')
    
    async with async_session_maker() as session:
        # Проверим, нет ли клана с таким именем или тегом
        existing = await session.execute(
            select(Clan).where((Clan.name == name) | (Clan.tag == tag))
        )
        if existing.scalar_one_or_none():
            await message.answer("❌ Клан с таким именем или тегом уже существует.")
            return
        
        # Создаём клан (используем функцию из сервиса)
        clan = await create_clan(session, message.from_user.id, name, tag)
        if clan:
            await message.answer(f"✅ Клан {name} [{tag}] успешно создан!")
        else:
            await message.answer("❌ Не удалось создать клан.")

@router.message(Command("clan_join"))
async def cmd_clan_join(message: types.Message):
    """Вступление в клан по тегу или приглашению"""
    # Упрощённо: /clan_join ТЕГ
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /clan_join <тег>\nНапример: /clan_join WAR")
        return
    
    tag = args[1].strip('[]')
    
    async with async_session_maker() as session:
        # Находим клан по тегу
        clan = await session.execute(select(Clan).where(Clan.tag == tag))
        clan = clan.scalar_one_or_none()
        if not clan:
            await message.answer("❌ Клан с таким тегом не найден.")
            return
        
        # Добавляем пользователя
        success = await add_member(session, clan.id, message.from_user.id)
        if success:
            await message.answer(f"✅ Ты вступил в клан {clan.name} [{clan.tag}]!")
        else:
            await message.answer("❌ Ты уже состоишь в другом клане.")

@router.message(Command("clan_leave"))
async def cmd_clan_leave(message: types.Message):
    """Выход из клана"""
    clan, member = await get_user_clan(message.from_user.id)
    if not clan:
        await message.answer("❌ Ты не в клане.")
        return
    
    if member.role == 'leader':
        # Лидер не может выйти, должен передать права или распустить клан
        await message.answer("❌ Лидер не может покинуть клан. Передай права другому участнику или распусти клан.")
        return
    
    async with async_session_maker() as session:
        success = await remove_member(session, clan.id, message.from_user.id)
        if success:
            await message.answer("✅ Ты покинул клан.")
        else:
            await message.answer("❌ Ошибка при выходе из клана.")

@router.message(Command("clan_rankings"))
async def cmd_clan_rankings(message: types.Message):
    """Топ кланов"""
    async with async_session_maker() as session:
        rankings = await get_clan_rankings(session)
        if not rankings:
            await message.answer("Пока нет кланов.")
            return
        
        text = "🏆 <b>Топ кланов</b>\n\n"
        for i, c in enumerate(rankings, 1):
            text += f"{i}. {c['name']} [{c['tag']}] – Ур. {c['level']}, опыта {c['exp']}, участников {c['members']}\n"
        
        await message.answer(text)

@router.callback_query(lambda c: c.data == "clan_members")
async def clan_members(callback: types.CallbackQuery):
    """Список участников клана"""
    clan, _ = await get_user_clan(callback.from_user.id)
    if not clan:
        await callback.answer("Ты не в клане", show_alert=True)
        return
    
    async with async_session_maker() as session:
        members = await session.execute(
            select(ClanMember, User).join(User, ClanMember.user_id == User.id).where(ClanMember.clan_id == clan.id)
        )
        members = members.all()
        
        text = f"📋 <b>Участники клана {clan.name}</b>\n\n"
        for m, u in members:
            role_emoji = "👑" if m.role == 'leader' else "⭐" if m.role == 'officer' else "👤"
            text += f"{role_emoji} {u.first_name or u.username or f'ID{u.telegram_id}'} – вклад: {m.contributed_stars}⭐\n"
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="clan_back")]]
        ))
    await callback.answer()

@router.callback_query(lambda c: c.data == "clan_back")
async def clan_back(callback: types.CallbackQuery):
    await cmd_clan(callback.message)
    await callback.answer()

# Другие callback'и для банка, битв можно добавить позже
