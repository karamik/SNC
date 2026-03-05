import asyncio
import datetime
import json
import logging
import random
from typing import Dict, List, Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select, update
import redis.asyncio as redis

from bot.models.db import User, Bet, Round, Transaction

logger = logging.getLogger(__name__)

class GameEngine:
    def __init__(self, bot: Bot, redis_client: redis.Redis, session_maker: async_sessionmaker):
        self.bot = bot
        self.redis = redis_client
        self.session_maker = session_maker
        self.running = True
        self.current_round_task = None

    async def run(self):
        """Запуск цикла обработки раундов каждую минуту."""
        logger.info("Game engine started")
        while self.running:
            try:
                now = datetime.datetime.utcnow()
                # Ждём до начала следующей минуты (ровно в 0 секунд)
                next_minute = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
                sleep_seconds = (next_minute - now).total_seconds()
                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)
                
                # Обрабатываем раунд для этой минуты
                await self.process_round(next_minute)
            except asyncio.CancelledError:
                logger.info("Game engine cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in game engine loop: {e}")
                await asyncio.sleep(5)  # небольшая пауза перед повторной попыткой

    async def stop(self):
        """Остановка движка."""
        self.running = False

    async def restart(self):
        """Перезапуск движка (для админки)."""
        logger.info("Restarting game engine...")
        self.running = False
        if self.current_round_task:
            self.current_round_task.cancel()
        # Даём время завершиться
        await asyncio.sleep(2)
        self.running = True
        asyncio.create_task(self.run())

    async def process_round(self, round_time: datetime.datetime):
        """Обработка одного раунда."""
        logger.info(f"Processing round for {round_time}")
        round_timestamp = int(round_time.timestamp())
        round_key = f"round:{round_timestamp}:bets"

        # Получаем все ставки за эту минуту из Redis
        bets_data = await self.redis.zrange(round_key, 0, -1, withscores=True)
        if not bets_data:
            logger.info("No bets this round")
            return

        # Парсим ставки
        bets = []
        for bet_json, _ in bets_data:
            try:
                bet_info = json.loads(bet_json)
                bets.append(bet_info)
            except json.JSONDecodeError:
                logger.error(f"Invalid bet JSON: {bet_json}")

        if not bets:
            return

        # Общая сумма ставок
        total_amount = sum(b['amount'] for b in bets)
        num_bets = len(bets)

        # Определяем количество победителей (40%), кэшбек (50%), проигравших (10%)
        # Округление вниз, но минимум 1 победитель
        num_winners = max(1, int(num_bets * 0.4))
        num_refunds = int(num_bets * 0.5)
        num_losers = num_bets - num_winners - num_refunds  # оставшиеся

        # Перемешиваем список для случайного выбора
        random.shuffle(bets)

        winners = bets[:num_winners]
        refunds = bets[num_winners:num_winners + num_refunds]
        losers = bets[num_winners + num_refunds:]  # эти не получают ничего

        # Собираем результаты
        total_payout = 0
        for b in winners:
            b['result'] = 'win'
            b['payout'] = b['amount'] * 2
            total_payout += b['payout']
        for b in refunds:
            b['result'] = 'refund'
            b['payout'] = int(b['amount'] * 0.1)  # 10% кэшбек
            total_payout += b['payout']
        for b in losers:
            b['result'] = 'loss'
            b['payout'] = 0

        house_profit = total_amount - total_payout

        # Сохраняем результаты в БД в фоновом режиме
        asyncio.create_task(self.save_round_results(round_time, round_timestamp, bets, total_amount, total_payout, house_profit))

        # Очищаем ключ раунда (можно не удалять сразу, а установить expire на всякий случай)
        await self.redis.delete(round_key)

        # Логируем результаты
        logger.info(f"Round {round_time}: bets={num_bets}, total={total_amount}, payout={total_payout}, profit={house_profit}")

    async def save_round_results(self, round_time: datetime.datetime, round_timestamp: int,
                                  bets: List[Dict], total_amount: int, total_payout: int, house_profit: int):
        """Сохранение результатов раунда в БД и обновление балансов пользователей."""
        async with self.session_maker() as session:
            # Создаём запись раунда
            round_db = Round(
                round_time=round_time,
                total_bets=len(bets),
                total_amount=total_amount,
                winners_count=sum(1 for b in bets if b['result'] == 'win'),
                winners_amount=sum(b['payout'] for b in bets if b['result'] == 'win'),
                refunds_count=sum(1 for b in bets if b['result'] == 'refund'),
                refunds_amount=sum(b['payout'] for b in bets if b['result'] == 'refund'),
                losers_count=sum(1 for b in bets if b['result'] == 'loss'),
                house_profit=house_profit
            )
            session.add(round_db)
            await session.flush()  # чтобы получить id

            # Для каждой ставки обновляем баланс пользователя
            for bet_info in bets:
                # Находим пользователя по telegram_id
                user = await session.execute(
                    select(User).where(User.telegram_id == bet_info['user_id'])
                )
                user = user.scalar_one_or_none()
                if not user:
                    logger.warning(f"User {bet_info['user_id']} not found, skipping bet")
                    continue

                # Обновляем баланс
                if bet_info['result'] == 'win':
                    user.balance += bet_info['payout']
                    user.total_wins += 1
                    user.total_stars_won += bet_info['payout']
                elif bet_info['result'] == 'refund':
                    user.balance += bet_info['payout']
                    user.total_refunds += 1
                    user.total_stars_refunded += bet_info['payout']
                else:
                    user.total_losses += 1
                    user.total_stars_lost += bet_info['amount']

                user.total_bets += 1
                user.total_stars_bet += bet_info['amount']
                user.exp += bet_info['amount'] // 10  # простой расчёт опыта
                # Обновление уровня будет происходить отдельно (можно в триггере или позже)

                # Создаём запись ставки
                bet_db = Bet(
                    user_id=user.id,
                    round_id=round_db.id,
                    amount=bet_info['amount'],
                    result=bet_info['result'],
                    payout=bet_info['payout']
                )
                session.add(bet_db)

                # Транзакция для списания (ставка) уже была при размещении, но здесь добавим транзакцию выигрыша/кэшбека
                if bet_info['payout'] > 0:
                    trans = Transaction(
                        user_id=user.id,
                        amount=bet_info['payout'],
                        type='win' if bet_info['result'] == 'win' else 'refund',
                        description=f"Раунд {round_time.strftime('%H:%M')}"
                    )
                    session.add(trans)

            await session.commit()
            logger.info(f"Round {round_time} saved to DB")
