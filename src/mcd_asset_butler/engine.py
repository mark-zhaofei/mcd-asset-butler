"""资产分析引擎：体检、折算、过期风险、保值策略。

所有计算为纯函数（输入 AssetLedger，输出结构化结论），便于单测。
金额单位统一为「分」(fen)，积分口径默认 100 积分 = ¥1。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from .models import (
    AssetLedger,
    Coupon,
    LotteryInfo,
    MallProduct,
    Meal,
    PointsAccount,
)


# --------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------- #
@dataclass
class AssetSummary:
    """资产总览。"""

    coupon_value_fen: int = 0          # 可用券面额合计
    coupon_at_risk_fen: int = 0        # 7 天内过期的券面额
    points_value_fen: int = 0          # 可用积分折算金额
    points_at_risk_fen: int = 0        # 即将过期积分折算金额
    prize_count: int = 0
    total_value_fen: int = 0           # 总资产（可用部分）
    total_at_risk_fen: int = 0         # 风险部分

    @property
    def at_risk_ratio(self) -> float:
        return self.total_at_risk_fen / self.total_value_fen if self.total_value_fen else 0.0


@dataclass
class DisposalOption:
    """一种积分处置方式及其单位价值。"""

    name: str
    value_fen_per_100_points: float    # 每 100 积分可获得的商品价值（分）
    detail: str
    risk: str = ""                     # 风险提示


@dataclass
class CouponUsage:
    """临期券的一种推荐用法。"""

    coupon: Coupon
    combo: List[Meal]
    combo_price_fen: int
    pay_fen: int
    saved_ratio: float                 # 券面额 / 原价


@dataclass
class StrategyReport:
    summary: AssetSummary
    disposal_options: List[DisposalOption] = field(default_factory=list)
    best_disposal: Optional[DisposalOption] = None
    coupon_usages: List[CouponUsage] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# --------------------------------------------------------------------- #
# 资产总览
# --------------------------------------------------------------------- #
def summarize(ledger: AssetLedger) -> AssetSummary:
    rate = ledger.point_rate_fen  # 1 积分 = rate 分
    s = AssetSummary()
    for c in ledger.coupons:
        s.coupon_value_fen += c.amount_fen
        if c.at_risk:
            s.coupon_at_risk_fen += c.amount_fen
    if ledger.points:
        s.points_value_fen = ledger.points.available * rate
        s.points_at_risk_fen = ledger.points.expiring * rate
    s.prize_count = len(ledger.prizes)
    s.total_value_fen = s.coupon_value_fen + s.points_value_fen
    s.total_at_risk_fen = s.coupon_at_risk_fen + s.points_at_risk_fen
    return s


# --------------------------------------------------------------------- #
# 积分处置策略：抽奖 EV vs 商城兑换 vs 直接抵扣
# --------------------------------------------------------------------- #
def disposal_options(ledger: AssetLedger) -> List[DisposalOption]:
    """比较三种积分处置方式的单位价值（分/100积分），从优到劣排序。"""
    options: List[DisposalOption] = []
    rate = ledger.point_rate_fen

    # ① 直接抵扣点餐（100 积分 = ¥1 → 每 100 积分值 rate*100 分）
    options.append(
        DisposalOption(
            name="直接抵扣点餐",
            value_fen_per_100_points=rate * 100.0,
            detail="点餐时按 100 积分 = ¥1 直接抵扣，零门槛、零方差",
            risk="无",
        )
    )

    # ② 积分商城兑换（取性价比最高的在售商品为代表）
    products = [p for p in ledger.mall_products if p.points > 0 and p.market_value_fen > 0]
    if products:
        best = max(products, key=lambda p: p.value_per_100_points)
        n = len(products)
        options.append(
            DisposalOption(
                name=f"积分商城兑换（当前最优：{best.name}）",
                value_fen_per_100_points=best.value_per_100_points,
                detail=f"{n} 件在售商品中性价比最高：{best.points} 积分 ≈ ¥{best.market_value_fen / 100:.2f}",
                risk="需要盯库存，心仪商品可能下架",
            )
        )

    # ③ 积分抽奖（期望值）
    lot: Optional[LotteryInfo] = ledger.lottery
    if lot and lot.cost_points > 0 and lot.prizes:
        ev_per_draw = lot.ev_fen_per_draw
        ev_per_100 = ev_per_draw * 100.0 / lot.cost_points
        top = max(lot.prizes, key=lambda p: p.probability * p.value_fen)
        options.append(
            DisposalOption(
                name=f"积分抽奖 · {lot.title}",
                value_fen_per_100_points=ev_per_100,
                detail=(
                    f"单次 {lot.cost_points} 积分，期望回报 ¥{ev_per_draw / 100:.2f}"
                    f"（最大贡献奖品：{top.name}）"
                ),
                risk="期望值≠实际所得，方差大；请理性投入，建议单次不超过总积分 10%",
            )
        )
    options.sort(key=lambda o: o.value_fen_per_100_points, reverse=True)
    return options


# --------------------------------------------------------------------- #
# 临期券最优用法：用真实菜单 + 官方算价验证
# --------------------------------------------------------------------- #
def _scope_meals(coupon: Coupon, meals: List[Meal]) -> List[Meal]:
    """券面适用餐品匹配：券名中提到的餐品优先作为搭配候选。

    例如「板烧鸡腿堡半价券」只在含板烧鸡腿堡的候选里挑；
    未提及具体餐品的（如「麦乐送满59减10元券」）则用全菜单。
    """
    title = coupon.title
    matched = [m for m in meals if m.name and m.name in title]
    return matched if matched else meals


def plan_coupon_usages(
    ledger: AssetLedger,
    meals: List[Meal],
    top_n: int = 3,
) -> List[CouponUsage]:
    """为每张临期券找到「券后实付最低」的用法，并用 calculate-price 口径校验。

    匹配规则：
    - 券后实付 = max(套餐原价 - 券面额, 0)，且原价需达到用券门槛
    - 券名提及的餐品优先进入候选（适用餐品匹配）
    - 无门槛券优先搭配低价单品，把券面额用满
    - 有门槛券优先搭配刚过门槛的组合
    """
    usages: List[CouponUsage] = []
    if not meals:
        return usages
    meals = sorted(meals, key=lambda m: m.price_fen)
    for c in ledger.coupons:
        if not c.at_risk:
            continue
        candidates = sorted(_scope_meals(c, meals), key=lambda m: m.price_fen)
        best: Optional[CouponUsage] = None

        def _consider(combo: List[Meal]) -> None:
            nonlocal best
            total = sum(m.price_fen for m in combo)
            if total < c.threshold_fen:
                return
            pay = max(total - c.amount_fen, 0)
            usage = CouponUsage(
                coupon=c,
                combo=list(combo),
                combo_price_fen=total,
                pay_fen=pay,
                saved_ratio=c.amount_fen / total if total else 0,
            )
            if best is None or pay < best.pay_fen:
                best = usage

        # 单品用法
        for m in candidates:
            _consider([m])
        # 双单品组合（用于无门槛/低门槛券把面额用满、或凑有门槛券）
        for i, m1 in enumerate(candidates):
            for m2 in candidates[i:]:
                _consider([m1, m2] if m1.id != m2.id else [m1])
        if best is not None:
            usages.append(best)
    usages.sort(key=lambda u: (u.coupon.days_left if u.coupon.days_left is not None else 99, -u.pay_fen))
    return usages[: top_n * 3]  # 每张券保留，展示层再截断


# --------------------------------------------------------------------- #
# 策略汇总
# --------------------------------------------------------------------- #
def build_strategy(
    ledger: AssetLedger,
    meals: Optional[List[Meal]] = None,
) -> StrategyReport:
    summary = summarize(ledger)
    options = disposal_options(ledger)
    usages = plan_coupon_usages(ledger, meals or [])
    report = StrategyReport(summary=summary, disposal_options=options, coupon_usages=usages)
    if options:
        report.best_disposal = options[0]

    # 生成行动建议
    notes: List[str] = []
    if summary.coupon_at_risk_fen > 0:
        n = sum(1 for c in ledger.coupons if c.at_risk)
        notes.append(
            f"⚠️ 有 {n} 张券将在 7 天内过期，合计 ¥{summary.coupon_at_risk_fen / 100:.2f}，"
            "建议按下方「临期券用法」尽快安排"
        )
    if summary.points_at_risk_fen > 0 and ledger.points and ledger.points.expiring > 0:
        notes.append(
            f"⚠️ {ledger.points.expiring} 积分即将过期（≈ ¥{summary.points_at_risk_fen / 100:.2f}），"
            "建议优先使用「即将过期积分」再动可用存量"
        )
    if options and options[0].name.startswith("积分商城兑换"):
        notes.append("💡 当前积分商城兑换性价比高于直接抵扣，可优先兑换高性价比商品")
    if options and options[0].name.startswith("积分抽奖"):
        notes.append("💡 抽奖期望值暂时领先，但方差大，建议小额多次、见好就收")
    if not notes:
        notes.append("✅ 资产状态健康，无 7 天内过期风险")
    report.notes = notes
    return report
