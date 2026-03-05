# bot/handlers/bank.py
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from bot.main import async_session_maker
from bot.models.db import User
from bot.models.bank import Deposit, DepositTariff, DepositStatus
from bot.services.bank import create_deposit, early_withdraw, get_user_deposits, get_active_deposits

router = Router()

# Состояния для создания депозита
class DepositStates(StatesGroup):
    choosing_tariff = State()
    entering_amount = State()

@router.message(Command("bank"))
async def cmd_bank(message: types.Message):
    """Главное меню банка"""
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся через /start")
            return
        
        # Активные депозиты
        active = await get_active_deposits(session, user.id)
        
        # Все депозиты
        all_deps = await get_user_deposits(session, user.id)
        total_deposited = sum(d.amount for d in all_deps if d.status == DepositStatus.COMPLETED)
        total_interest = sum(d.expected_interest for d in all_deps if d.status == DepositStatus.COMPLETED)
        
        text = (
            f"🏦 <b>Звёздный банк</b>\n\n"
            f"💰 Твой баланс: {user.balance} ⭐\n"
            f"📦 Активных вкладов: {len(active)}\n"
            f"📊 Всего вложено: {total_deposited} ⭐\n"
            f"💸 Получено процентов: {total_interest} ⭐\n\n"
            f"Выбери действие:"
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Открыть вклад", callback_data="bank_new")],
                [InlineKeyboardButton(text="📋 Мои вклады", callback_data="bank_list")],
                [InlineKeyboardButton(text="📊 Тарифы", callback_data="bank_tariffs")]
            ]
        )
        await message.answer(text, reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "bank_tariffs")
async def bank_tariffs(callback: types.CallbackQuery):
    """Показать доступные тарифы"""
    async with async_session_maker() as session:
        tariffs = await session.execute(
            select(DepositTariff).where(DepositTariff.is_active == True).order_by(DepositTariff.duration_days)
        )
        tariffs = tariffs.scalars().all()
        
        text = "📊 <b>Доступные тарифы</b>\n\n"
        for t in tariffs:
            max_str = f"до {t.max_amount}" if t.max_amount else "без ограничений"
            text += (
                f"• <b>{t.name}</b>\n"
                f"  Срок: {t.duration_days} дней\n"
                f"  Ставка: {t.interest_rate}%\n"
                f"  Сумма: от {t.min_amount} до {max_str} ⭐\n\n"
            )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="bank_back")]]
        )
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data == "bank_new")
async def bank_new_start(callback: types.CallbackQuery, state: FSMContext):
    """Начать создание вклада: выбор тарифа"""
    async with async_session_maker() as session:
        tariffs = await session.execute(
            select(DepositTariff).where(DepositTariff.is_active == True).order_by(DepositTariff.duration_days)
        )
        tariffs = tariffs.scalars().all()
        
        if not tariffs:
            await callback.answer("Нет доступных тарифов", show_alert=True)
            return
        
        keyboard = []
        for t in tariffs:
            keyboard.append([InlineKeyboardButton(
                text=f"{t.name} ({t.duration_days} дн., {t.interest_rate}%)",
                callback_data=f"bank_tariff_{t.id}"
            )])
        keyboard.append([InlineKeyboardButton(text="◀ Отмена", callback_data="bank_back")])
        
        await callback.message.edit_text(
            "Выбери тариф для вклада:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("bank_tariff_"))
async def bank_tariff_selected(callback: types.CallbackQuery, state: FSMContext):
    """Тариф выбран, запрашиваем сумму"""
    tariff_id = int(callback.data.split("_")[2])
    await state.update_data(tariff_id=tariff_id)
    
    async with async_session_maker() as session:
        tariff = await session.get(DepositTariff, tariff_id)
        if not tariff:
            await callback.answer("Тариф не найден", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"Тариф: {tariff.name}\n"
            f"Срок: {tariff.duration_days} дней\n"
            f"Ставка: {tariff.interest_rate}%\n"
            f"Мин. сумма: {tariff.min_amount} ⭐\n"
            f"Макс. сумма: {tariff.max_amount or '∞'} ⭐\n\n"
            f"Введи сумму вклада (целое число):"
        )
    await state.set_state(DepositStates.entering_amount)
    await callback.answer()

@router.message(DepositStates.entering_amount)
async def bank_enter_amount(message: types.Message, state: FSMContext):
    """Получение суммы и создание депозита"""
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое положительное число.")
        return
    
    data = await state.get_data()
    tariff_id = data.get('tariff_id')
    
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся")
            await state.clear()
            return
        
        tariff = await session.get(DepositTariff, tariff_id)
        if not tariff:
            await message.answer("Тариф не найден")
            await state.clear()
            return
        
        # Проверка лимитов
        if amount < tariff.min_amount:
            await message.answer(f"❌ Минимальная сумма для этого тарифа: {tariff.min_amount} ⭐")
            return
        if tariff.max_amount and amount > tariff.max_amount:
            await message.answer(f"❌ Максимальная сумма для этого тарифа: {tariff.max_amount} ⭐")
            return
        
        # Создаём депозит
        deposit = await create_deposit(session, user, tariff_id, amount)
        if deposit:
            await message.answer(
                f"✅ Вклад открыт!\n\n"
                f"Сумма: {amount} ⭐\n"
                f"Срок: {tariff.duration_days} дней\n"
                f"Доход: {deposit.expected_interest} ⭐\n"
                f"Дата окончания: {deposit.end_time.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await message.answer("❌ Не удалось открыть вклад. Возможно, недостаточно средств.")
    
    await state.clear()

@router.callback_query(lambda c: c.data == "bank_list")
async def bank_list(callback: types.CallbackQuery):
    """Список вкладов пользователя"""
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return
        
        deposits = await get_user_deposits(session, user.id)
        
        if not deposits:
            await callback.message.edit_text(
                "У тебя пока нет вкладов.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="bank_back")]]
                )
            )
            await callback.answer()
            return
        
        text = "📋 <b>Мои вклады</b>\n\n"
        now = datetime.datetime.utcnow()
        for d in deposits:
            status_emoji = {
                DepositStatus.ACTIVE: "🟢",
                DepositStatus.COMPLETED: "✅",
                DepositStatus.EARLY_WITHDRAWN: "⚠️"
            }.get(d.status, "❓")
            
            time_left = ""
            if d.status == DepositStatus.ACTIVE:
                remaining = d.end_time - now
                days = remaining.days
                hours = remaining.seconds // 3600
                time_left = f" (осталось {days}д {hours}ч)"
            
            text += (
                f"{status_emoji} <b>{d.tariff.name if d.tariff else 'Тариф'}</b>\n"
                f"  Сумма: {d.amount} ⭐\n"
                f"  Доход: {d.expected_interest} ⭐\n"
                f"  До: {d.end_time.strftime('%d.%m.%Y')}{time_left}\n\n"
            )
        
        # Кнопка для досрочного снятия (если есть активные)
        active = [d for d in deposits if d.status == DepositStatus.ACTIVE]
        keyboard = []
        if active:
            for d in active[:5]:  # максимум 5 кнопок
                keyboard.append([InlineKeyboardButton(
                    text=f"⚠️ Досрочно снять {d.amount}⭐",
                    callback_data=f"bank_withdraw_{d.id}"
                )])
        
        keyboard.append([InlineKeyboardButton(text="◀ Назад", callback_data="bank_back")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("bank_withdraw_"))
async def bank_withdraw(callback: types.CallbackQuery):
    """Досрочное снятие депозита"""
    deposit_id = int(callback.data.split("_")[2])
    
    async with async_session_maker() as session:
        deposit = await session.get(Deposit, deposit_id)
        if not deposit:
            await callback.answer("Депозит не найден", show_alert=True)
            return
        
        if deposit.user.telegram_id != callback.from_user.id:
            await callback.answer("Это не твой депозит", show_alert=True)
            return
        
        if deposit.status != DepositStatus.ACTIVE:
            await callback.answer("Этот депозит уже завершён", show_alert=True)
            return
        
        success = await early_withdraw(session, deposit)
        if success:
            await callback.answer(f"✅ Депозит досрочно снят. Возвращено {deposit.amount} ⭐", show_alert=True)
        else:
            await callback.answer("❌ Ошибка при снятии", show_alert=True)
    
    # Обновляем список
    await bank_list(callback)

@router.callback_query(lambda c: c.data == "bank_back")
async def bank_back(callback: types.CallbackQuery, state: FSMContext = None):
    """Возврат в главное меню банка"""
    if state:
        await state.clear()
    await cmd_bank(callback.message)
    await callback.answer()
