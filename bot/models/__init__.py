# bot/models/__init__.py
# Этот файл импортирует все модели, чтобы SQLAlchemy могла их обнаружить

from .db import Base, User, Bet, Round, Transaction, DailyBonus, ShopItem, Purchase, Tournament, TournamentParticipant, AdminLog
from .achievement import Achievement, UserAchievement
from .booster import ActiveBooster
from .event import GameEvent
from .clan import Clan, ClanMember, ClanBattle
from .bank import DepositTariff, Deposit
from .chat import ChatMessage

# Список всех моделей для удобства (необязательно)
__all__ = [
    'Base',
    'User', 'Bet', 'Round', 'Transaction', 'DailyBonus', 'ShopItem', 'Purchase',
    'Tournament', 'TournamentParticipant', 'AdminLog',
    'Achievement', 'UserAchievement',
    'ActiveBooster',
    'GameEvent',
    'Clan', 'ClanMember', 'ClanBattle',
    'DepositTariff', 'Deposit',
    'ChatMessage',
]
