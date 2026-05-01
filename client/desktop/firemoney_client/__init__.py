"""FireMoney desktop client skeleton."""

from .adapter import LocalMainChainAdapter
from .shell import FireMoneyShell

__all__ = [
    "FireMoneyShell",
    "LocalMainChainAdapter",
]
