# bot/services/bank.py
import datetime
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from bot.models.db import User
from bot.models.bank import Deposit, DepositTariff, DepositStatus

logger = logging.getLogger(__name__)

async def init_deposit_tariffs(session: AsyncSession):
    """Инициализация тарифов, если их нет."""
    count = await session.scalar(select(func.count(DepositTariff.id)))
    if count > 0:
        return
    tariffs = [
        DepositTariff(name="Краткосрочный", duration_days=7, interest_rate=5.0, min_amount=500, max_amount=5000),
        DepositTariff(name="Среднесрочный", duration_days=14, interest_rate=8.0, min_amount=1000, max_amount=10000),
        DepositTariff(name="Долгосрочный", duration_days=30, interest_rate=12.0, min_amount=2000, max_amount=50000),
    ]
    session.add_all(tariffs)
    await session.commit()
    logger.info("Deposit tariffs initialized")

async def create_deposit(session: AsyncSession, user: User, tariff_id: int, amount: int) -> Optional[Deposit]:
    """
    Создание нового депозита.
    Списание суммы с баланса пользователя.
    """
    # Проверяем тариф
    tariff = await session.get(DepositTariff, tariff_id)
    if not tariff or not tariff.is_active:
        logger.warning(f"Tariff {tariff_id} not found or inactive")
        return None
    
    # Проверяем лимиты тарифа
    if amount < tariff.min_amount:
        logger.warning(f"Amount {amount} less than min {tariff.min_amount}")
        return None
    if tariff.max_amount and amount > tariff.max_amount:
        logger.warning(f"Amount {amount} greater than max {tariff.max_amount}")
        return None
    
    # Проверяем баланс пользователя
    if user.balance < amount:
        logger.warning(f"Insufficient balance: {user.balance} < {amount}")
        return None
    
    # Списываем звёзды
    user.balance -= amount
    
    # Рассчитываем ожидаемый доход
    expected_interest = int(amount * tariff.interest_rate / 100)
    
    # Создаём депозит
    end_time = datetime.datetime.utcnow() + datetime.timedelta(days=tariff.duration_days)
    deposit = Deposit(
        user_id=user.id,
        tariff_id=tariff.id,
        amount=amount,
        interest_rate=tariff.interest_rate,
        expected_interest=expected_interest,
        end_time=end_time
    )
    session.add(deposit)
    await session.commit()
    logger.info(f"Deposit created for user {user.telegram_id}: {amount} stars, ends at {end_time}")
    return deposit

async def process_completed_deposits(session: AsyncSession):
    """
    Проверяет завершённые депозиты и начисляет проценты.
    Вызывается планировщиком, например, раз в час.
    """
    now = datetime.datetime.utcnow()
    deposits = await session.execute(
        select(Deposit).where(
            and_(
                Deposit.status == DepositStatus.ACTIVE,
                Deposit.end_time <= now
            )
        )
    )
    deposits = deposits.scalars().all()
    
    for dep in deposits:
        user = await session.get(User, dep.user_id)
        if user:
            # Начисляем основную сумму + проценты
            total = dep.amount + dep.expected_interest
            user.balance += total
            dep.status = DepositStatus.COMPLETED
            logger.info(f"Deposit {dep.id} completed for user {user.telegram_id}: +{total} stars")
        else:
            logger.error(f"User {dep.user_id} not found for deposit {dep.id}")
    
    await session.commit()
    return len(deposits)

async def early_withdraw(session: AsyncSession, deposit: Deposit) -> bool:
    """
    Досрочное снятие депозита (без процентов).
    Возвращает True, если успешно.
    """
    if deposit.status != DepositStatus.ACTIVE:
        logger.warning(f"Deposit {deposit.id} is not active")
        return False
    
    user = await session.get(User, deposit.user_id)
    if not user:
        logger.error(f"User {deposit.user_id} not found")
        return False
    
    # Возвращаем только тело вклада
    user.balance += deposit.amount
    deposit.status = DepositStatus.EARLY_WITHDRAWN
    deposit.early_withdrawn_at = datetime.datetime.utcnow()
    deposit.early_withdrawn_amount = deposit.amount
    
    await session.commit()
    logger.info(f"Deposit {deposit.id} early withdrawn by user {user.telegram_id}")
    return True

async def get_user_deposits(session: AsyncSession, user_id: int) -> List[Deposit]:
    """Получение всех депозитов пользователя."""
    deposits = await session.execute(
        select(Deposit).where(Deposit.user_id == user_id).order_by(Deposit.created_at.desc())
    )
    return deposits.scalars().all()

async def get_active_deposits(session: AsyncSession, user_id: int) -> List[Deposit]:
    """Получение активных депозитов пользователя."""
    deposits = await session.execute(
        select(Deposit).where(
            and_(Deposit.user_id == user_id, Deposit.status == DepositStatus.ACTIVE)
        )
    )
    return deposits.scalars().all()
