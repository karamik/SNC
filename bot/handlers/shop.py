# bot/handlers/shop.py

import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from bot.main import async_session_maker, bot
from bot.models.db import User, ShopItem, Purchase
from bot.models.booster import ActiveBooster
from bot.services.leveling import add_exp

router = Router()

@router.message(Command("shop"))
async def cmd_shop(message: types.Message):
    """Открыть магазин"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(ShopItem).where(ShopItem.is_active == True).order_by(ShopItem.price)
        )
        items = result.scalars().all()
        
        if not items:
            await message.answer("🛒 Магазин временно пуст. Загляни позже!")
            return
        
        text = "🛒 <b>Магазин</b>\n\nВыбери товар для покупки:\n\n"
        
        keyboard = []
        for item in items:
            text += f"<b>{item.name}</b> — {item.price} ⭐\n{item.description}\n\n"
            keyboard.append([InlineKeyboardButton(
                text=f"{item.name} ({item.price} ⭐)",
                callback_data=f"shop_buy_{item.id}"
            )])
        
        keyboard.append([InlineKeyboardButton(text="📋 Мои покупки", callback_data="shop_my")])
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(lambda c: c.data.startswith("shop_buy_"))
async def shop_buy(callback: types.CallbackQuery):
    """Покупка товара"""
    item_id = int(callback.data.split("_")[2])
    
    async with async_session_maker() as session:
        item = await session.get(ShopItem, item_id)
        if not item or not item.is_active:
            await callback.answer("Товар недоступен", show_alert=True)
            return
        
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала зарегистрируйся", show_alert=True)
            return
        
        if user.balance < item.price:
            await callback.answer(f"Недостаточно звёзд! Нужно {item.price} ⭐", show_alert=True)
            return
        
        # Списываем звёзды
        user.balance -= item.price
        
        # Создаём запись о покупке
        purchase = Purchase(
            user_id=user.id,
            item_id=item.id,
            price_paid=item.price,
            purchased_at=datetime.datetime.utcnow()
        )
        session.add(purchase)
        
        # Добавляем опыт за покупку
        add_exp(user, item.price // 10)
        
        # Если это бустер, создаём активный бустер
        if item.item_type == 'booster':
            booster_data = item.item_data
            expires_at = None
            uses_left = None
            
            if 'rounds' in booster_data:
                # Временный на количество раундов (храним как expires_at через время)
                expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=booster_data['rounds'] * 1)  # примерно минут на раунд
            elif 'duration_minutes' in booster_data:
                expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=booster_data['duration_minutes'])
            elif 'uses' in booster_data:
                uses_left = booster_data['uses']
            
            active_booster = ActiveBooster(
                user_id=user.id,
                booster_type=booster_data.get('booster_type', 'generic'),
                multiplier=booster_data.get('boost', 1.0),
                expires_at=expires_at,
                uses_left=uses_left
            )
            session.add(active_booster)
        
        # Если это титул или скин, можно сохранить в отдельную таблицу, но пока просто покупка
        # Для титулов/скинов можно добавить позже логику применения
        
        await session.commit()
        
        await callback.answer(f"✅ Ты приобрёл {item.name}!", show_alert=True)
        
        await callback.message.edit_text(
            f"✅ Покупка совершена!\n\n"
            f"Товар: {item.name}\n"
            f"Цена: {item.price} ⭐\n"
            f"Остаток на балансе: {user.balance} ⭐\n\n"
            f"Используй /profile, чтобы посмотреть свои бустеры и титулы.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ В магазин", callback_data="shop_back")]]
            )
        )

@router.callback_query(lambda c: c.data == "shop_my")
async def shop_my(callback: types.CallbackQuery):
    """Мои покупки"""
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return
        
        purchases = await session.execute(
            select(Purchase).where(Purchase.user_id == user.id).order_by(Purchase.purchased_at.desc()).limit(20)
        )
        purchases = purchases.scalars().all()
        
        if not purchases:
            await callback.message.edit_text(
                "📋 У тебя пока нет покупок.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ В магазин", callback_data="shop_back")]]
                )
            )
            await callback.answer()
            return
        
        text = "📋 <b>Мои покупки</b>\n\n"
        for p in purchases:
            item = await session.get(ShopItem, p.item_id)
            text += f"• {item.name if item else 'Неизвестный товар'} — {p.price_paid} ⭐ ({p.purchased_at.strftime('%d.%m.%Y')})\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ В магазин", callback_data="shop_back")]]
            )
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "shop_back")
async def shop_back(callback: types.CallbackQuery):
    """Возврат в магазин"""
    await cmd_shop(callback.message)
    await callback.answer()
