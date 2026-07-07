"""积分服务：扣费/充值，写只追加账本并同步余额，单事务保证一致。"""
from ..extensions import db
from ..models import CreditLedger, User


class InsufficientCredits(Exception):
    pass


def _apply(user: User, delta: int, reason: str):
    new_balance = user.credits + delta
    if new_balance < 0:
        raise InsufficientCredits("积分余额不足")
    user.credits = new_balance
    db.session.add(CreditLedger(
        user_id=user.id, delta=delta, balance_after=new_balance, reason=reason
    ))


def charge(user: User, amount: int, reason: str):
    """扣费。amount 为正数，内部转为负 delta。余额不足抛 InsufficientCredits。"""
    if amount <= 0:
        return
    _apply(user, -amount, reason)
    db.session.commit()


def grant(user: User, amount: int, reason: str = "admin.adjust"):
    """充值/发放积分。amount 可正可负（管理员调整）。"""
    _apply(user, amount, reason)
    db.session.commit()
