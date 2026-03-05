# bot/services/game_engine.py

import asyncio
import datetime
import json
import logging
import random
from typing import Dict, List, Any, Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select, update, and_
import redis.asyncio as redis

from bot.models.db import User, Bet, Round, Transaction
from bot.models.booster import ActiveBooster
from bot.services.achievements import check_achievements
from bot.services.leveling import add_exp

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
                next_minute = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
                sleep_seconds = (next_minute - now).total_seconds()
                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)
                
                await self.process_round(next_minute)
            except asyncio.CancelledError:
                logger.info("Game engine cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in game engine loop: {e}")
                await asyncio.sleep(5)

    async def stop(self):
        self.running = False

    async def restart(self):
        logger.info("Restarting game engine...")
        self.running = False
        if self.current_round_task:
            self.current_round_task.cancel()
        await asyncio.sleep(2)
        self.running = True
        asyncio.create_task(self.run())

    async def load_active_boosters(self, user_ids: List[int]) -> Dict[int, List[ActiveBooster]]:
        """Загружает активные бустеры для списка пользователей."""
        if not user_ids:
            return {}
        async with self.session_maker() as session:
            now = datetime.datetime.utcnow()
            result = await session.execute(
                select(ActiveBooster).where(
                    ActiveBooster.user_id.in_(user_ids),
                    ((ActiveBooster.expires_at > now) | (ActiveBooster.expires_at == None))
                )
            )
            boosters = result.scalars().all()
            boosters_dict = {}
            for b in boosters:
                boosters_dict.setdefault(b.user_id, []).append(b)
            return boosters_dict

    async def process_round(self, round_time: datetime.datetime):
        """Обработка одного раунда."""
        logger.info(f"Processing round for {round_time}")
        round_timestamp = int(round_time.timestamp())
        round_key = f"round:{round_timestamp}:bets"

        bets_data = await self.redis.zrange(round_key, 0, -1, withscores=True)
        if not bets_data:
            logger.info("No bets this round")
            return

        bets = []
        for bet_json, _ in bets_data:
            try:
                bet_info = json.loads(bet_json)
                bets.append(bet_info)
            except json.JSONDecodeError:
                logger.error(f"Invalid bet JSON: {bet_json}")

        if not bets:
            return

        # Загружаем бустеры для всех участников
        user_ids = list(set(b['user_id'] for b in bets))
        boosters_dict = await self.load_active_boosters(user_ids)

        # Вычисляем веса для взвешенного выбора победителей
        weights = []
        for bet in bets:
            weight = 1.0
            user_boosters = boosters_dict.get(bet['user_id'], [])
            for booster in user_boosters:
                if booster.booster_type == 'win_chance' and booster.multiplier > 1:
                    weight *= booster.multiplier
            weights.append(weight)

        # Определяем количество победителей (40%)
        num_winners = max(1, int(len(bets) * 0.4))
        indices = list(range(len(bets)))
        selected_winners = []

        # Взвешенный случайный выбор без возвращения
        for _ in range(num_winners):
            if not indices:
                break
            # Нормализуем веса для оставшихся индексов
            total_weight = sum(weights[i] for i in indices)
            if total_weight <= 0:
                idx = random.choice(indices)
            else:
                r = random.random() * total_weight
                cum = 0
                for i in indices:
                    cum += weights[i]
                    if r < cum:
                        idx = i
                        break
            selected_winners.append(idx)
            indices.remove(idx)

        # Оставшиеся индексы
        remaining_indices = indices
        num_refunds = int(len(remaining_indices) * 0.5)
        if num_refunds > 0 and remaining_indices:
            refund_indices = random.sample(remaining_indices, min(num_refunds, len(remaining_indices)))
        else:
            refund_indices = []
        loss_indices = [i for i in remaining_indices if i not in refund_indices]

        # Применяем страховку к проигравшим
        boosters_to_update = []
        for i in loss_indices[:]:
            user_boosters = boosters_dict.get(bets[i]['user_id'], [])
            for booster in user_boosters:
                if booster.booster_type == 'insurance' and (booster.uses_left is None or booster.uses_left > 0):
                    # Используем страховку
                    if booster.uses_left:
                        booster.uses_left -= 1
                        if booster.uses_left <= 0:
                            boosters_to_update.append(booster)  # пометим на удаление
                    bets[i]['result'] = 'refund'
                    bets[i]['payout'] = bets[i]['amount']
                    loss_indices.remove(i)
                    break

        # Устанавливаем результаты для остальных
        for i in selected_winners:
            bets[i]['result'] = 'win'
            bets[i]['payout'] = bets[i]['amount'] * 2
        for i in refund_indices:
            bets[i]['result'] = 'refund'
            bets[i]['payout'] = int(bets[i]['amount'] * 0.1)
        for i in loss_indices:
            bets[i]['result'] = 'loss'
            bets[i]['payout'] = 0

        # Подсчёт итогов
        total_amount = sum(b['amount'] for b in bets)
        total_payout = sum(b['payout'] for b in bets)
        house_profit = total_amount - total_payout

        # Сохраняем результаты в БД
        asyncio.create_task(self.save_round_results(
            round_time, round_timestamp, bets, total_amount, total_payout, house_profit, boosters_to_update
        ))

        await self.redis.delete(round_key)
        logger.info(f"Round {round_time}: bets={len(bets)}, total={total_amount}, payout={total_payout}, profit={house_profit}")

    async def save_round_results(self, round_time: datetime.datetime, round_timestamp: int,
                                 bets: List[Dict], total_amount: int, total_payout: int, house_profit: int,
                                 boosters_to_update: List[ActiveBooster]):
        """Сохранение результатов раунда в БД и обновление балансов пользователей."""
        async with self.session_maker() as session:
            # Запись раунда
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
            await session.flush()

            # Для каждой ставки
            for bet_info in bets:
                user = await session.execute(
                    select(User).where(User.telegram_id == bet_info['user_id'])
                )
                user = user.scalar_one_or_none()
                if not user:
                    logger.warning(f"User {bet_info['user_id']} not found, skipping bet")
                    continue

                # Обновляем статистику пользователя
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

                # Опыт с учётом бустеров
                exp_gain = bet_info['amount'] // 10
                user_boosters = await self.load_active_boosters([user.telegram_id])  # можно закешировать, но для простоты так
                for booster in user_boosters.get(user.telegram_id, []):
                    if booster.booster_type == 'exp_boost' and booster.multiplier > 1:
                        exp_gain = int(exp_gain * booster.multiplier)
                        # Если бустер временный, уменьшаем или удаляем (упрощённо)
                add_exp(user, exp_gain)

                # Сохраняем ставку
                bet_db = Bet(
                    user_id=user.id,
                    round_id=round_db.id,
                    amount=bet_info['amount'],
                    result=bet_info['result'],
                    payout=bet_info['payout']
                )
                session.add(bet_db)

                # Транзакция выигрыша/кэшбека
                if bet_info['payout'] > 0:
                    trans = Transaction(
                        user_id=user.id,
                        amount=bet_info['payout'],
                        type='win' if bet_info['result'] == 'win' else 'refund',
                        description=f"Раунд {round_time.strftime('%H:%M')}"
                    )
                    session.add(trans)

                # Проверяем достижения
                new_achs = await check_achievements(user, session)
                if new_achs:
                    for ach in new_achs:
                        try:
                            await self.bot.send_message(
                                user.telegram_id,
                                f"🏆 <b>Новое достижение!</b>\n\n"
                                f"<b>{ach.name}</b>\n{ach.description}\n"
                                f"Награда: {ach.reward_stars} ⭐, {ach.reward_exp} опыта"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send achievement to {user.telegram_id}: {e}")

                # Уведомление о крупном выигрыше
                if bet_info['result'] == 'win' and bet_info['payout'] >= 2000:
                    if user.notifications_enabled:
                        try:
                            await self.bot.send_message(
                                user.telegram_id,
                                f"🎉 <b>Поздравляем с крупным выигрышем!</b>\n"
                                f"Вы выиграли {bet_info['payout']} ⭐ в раунде {round_time.strftime('%H:%M')}!"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send win notification to {user.telegram_id}: {e}")

            # Обновляем/удаляем использованные бустеры
            for booster in boosters_to_update:
                if booster.uses_left == 0:
                    await session.delete(booster)
                else:
                    session.add(booster)

            await session.commit()
            logger.info(f"Round {round_time} saved to DB")
