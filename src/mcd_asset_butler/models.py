"""领域模型：麦当劳个人资产账本。

设计原则：
- 所有金额内部一律用「分」(fen) 存储，避免浮点误差；展示时再格式化为 ¥
- 麦当劳积分口径：100 积分 ≈ ¥1（可在引擎中覆盖）
- 字段提取全部容错：MCP 返回结构未完全公开，解析器在嵌套结构中定位关键字段
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------- #
# 容错字段定位：在任意嵌套结构里找第一个含目标键的 dict
# --------------------------------------------------------------------- #
def find_dicts(node: Any, *keys: str, _depth: int = 0) -> List[Dict[str, Any]]:
    """深度优先找出所有「至少包含一个目标键」的 dict。"""
    out: List[Dict[str, Any]] = []
    if _depth > 8:
        return out
    if isinstance(node, dict):
        if any(k in node for k in keys):
            out.append(node)
        for v in node.values():
            out.extend(find_dicts(v, *keys, _depth=_depth + 1))
    elif isinstance(node, list):
        for v in node:
            out.extend(find_dicts(v, *keys, _depth=_depth + 1))
    return out


def find_lists(node: Any, *keys: str, _depth: int = 0) -> List[List[Any]]:
    """找出元素 dict 含目标键的列表（如优惠券列表、商品列表）。"""
    out: List[List[Any]] = []
    if _depth > 8:
        return out
    if isinstance(node, list) and node and all(isinstance(v, dict) for v in node):
        if any(any(k in v for k in keys) for v in node):
            out.append(node)
            return out
    if isinstance(node, dict):
        for v in node.values():
            out.extend(find_lists(v, *keys, _depth=_depth + 1))
    elif isinstance(node, list):
        for v in node:
            out.extend(find_lists(v, *keys, _depth=_depth + 1))
    return out


def pick(d: Dict[str, Any], *names: str, default: Any = None) -> Any:
    """按候选键名取第一个非空值。"""
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return default


def to_fen(value: Any) -> Optional[int]:
    """把 元/分/字符串金额 统一转为分。

    口径约定（与国内支付类 API 惯例一致）：
    - 纯整数视为「分」（如 600 = ¥6.00）
    - 小数视为「元」（如 6.0 = ¥6.00）
    - 字符串带「分」字样视为分；带小数点或「元」视为元；纯数字字符串视为分
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            return int(round(value * 100))
        return int(value)
    s = str(value).strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    num = float(m.group(1))
    if "分" in s and "元" not in s:
        return int(round(num))
    if "." in m.group(1) or "元" in s:
        return int(round(num * 100))
    return int(round(num))


def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"-?\d+", str(value))
    return int(m.group()) if m else default


_DATE_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y.%m.%d",
)


def to_date(value: Any) -> Optional[date]:
    """解析多种日期/时间格式；支持 10 位时间戳（秒）与 13 位（毫秒）。"""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ts = float(value)
        if ts > 1e11:  # 毫秒
            ts /= 1000.0
        if ts > 1e8:
            return datetime.fromtimestamp(ts).date()
    s = str(value).strip()
    s = re.sub(r"(\.\d+)?([+-]\d{2}:?\d{2}|Z)$", "", s)  # 去时区/毫秒
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------- #
# 资产模型
# --------------------------------------------------------------------- #
@dataclass
class Coupon:
    """优惠券资产。"""

    id: str = ""
    title: str = ""
    amount_fen: int = 0          # 面额（分）
    threshold_fen: int = 0       # 使用门槛（分）
    expire: Optional[date] = None
    source: str = ""             # 麦麦省 / 门店活动
    usable: bool = True
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def days_left(self) -> Optional[int]:
        if not self.expire:
            return None
        return (self.expire - date.today()).days

    @property
    def at_risk(self) -> bool:
        d = self.days_left
        return d is not None and d <= 7 and d >= 0


@dataclass
class PointsAccount:
    """积分资产账户。"""

    available: int = 0        # 可用积分
    total_earned: int = 0     # 累计积分
    frozen: int = 0           # 冻结积分
    expiring: int = 0         # 即将过期积分
    expiring_date: Optional[date] = None

    @property
    def days_left(self) -> Optional[int]:
        if not self.expiring_date or self.expiring <= 0:
            return None
        return (self.expiring_date - date.today()).days


@dataclass
class Prize:
    """抽奖奖品记录。"""

    name: str = ""
    won_at: Optional[date] = None
    expire: Optional[date] = None


@dataclass
class LotteryPrize:
    """抽奖活动奖品项。"""

    name: str = ""
    probability: float = 0.0   # 0~1
    value_fen: int = 0         # 估值（分）


@dataclass
class LotteryInfo:
    """积分抽奖活动。"""

    title: str = "积分抽奖"
    cost_points: int = 0       # 单次消耗积分
    prizes: List[LotteryPrize] = field(default_factory=list)

    @property
    def ev_fen_per_draw(self) -> float:
        return sum(p.probability * p.value_fen for p in self.prizes)


@dataclass
class MallProduct:
    """积分商城商品。"""

    id: str = ""
    name: str = ""
    points: int = 0
    market_value_fen: int = 0
    category: str = ""

    @property
    def value_per_100_points(self) -> float:
        """每 100 积分可换得的商品价值（分），越大越划算。"""
        if self.points <= 0:
            return 0.0
        return self.market_value_fen * 100.0 / self.points


@dataclass
class Meal:
    """门店餐品（用于临期券用法匹配）。"""

    id: str = ""
    name: str = ""
    price_fen: int = 0
    category: str = ""


@dataclass
class AssetLedger:
    """统一资产账本：券 + 积分 + 奖品。"""

    coupons: List[Coupon] = field(default_factory=list)
    points: Optional[PointsAccount] = None
    prizes: List[Prize] = field(default_factory=list)
    lottery: Optional[LotteryInfo] = None
    mall_products: List[MallProduct] = field(default_factory=list)
    claimable_coupons: List[Coupon] = field(default_factory=list)
    point_rate_fen: int = 1    # 1 积分折合多少分（默认 100 积分=¥1 → 1 分）


# --------------------------------------------------------------------- #
# MCP 原始返回 → 模型（容错解析）
# --------------------------------------------------------------------- #
def parse_coupons(payload: Any) -> List[Coupon]:
    if payload is None:
        return []
    rows: List[Dict[str, Any]] = []
    for keys in (("couponId", "couponName"), ("id", "title"), ("couponId", "name")):
        rows = [r for lst in find_lists(payload, *keys) for r in lst]
        if rows:
            break
    out: List[Coupon] = []
    for r in rows:
        amount = to_fen(pick(r, "amount", "amountFen", "couponAmount", "value", "faceValue", "denomination"))
        threshold = to_fen(pick(r, "threshold", "thresholdFen", "minAmount", "useThreshold", "limitAmount"))
        status = str(pick(r, "status", "couponStatus", "state", default=""))
        usable = not any(w in status for w in ("已使用", "已过期", "USED", "EXPIRED", "已失效"))
        out.append(
            Coupon(
                id=str(pick(r, "couponId", "id", default="")),
                title=str(pick(r, "couponName", "name", "title", default="未命名券")),
                amount_fen=amount or 0,
                threshold_fen=threshold or 0,
                expire=to_date(pick(r, "expireTime", "expiryTime", "endTime", "validEndTime", "expireDate", "endDate")),
                source=str(pick(r, "source", "channel", "couponType", default="")),
                usable=usable,
                raw=r,
            )
        )
    return [c for c in out if c.usable and c.amount_fen > 0]


def parse_points(payload: Any) -> Optional[PointsAccount]:
    if payload is None:
        return None
    cands = find_dicts(payload, "availablePoints", "available", "points", "totalPoints", "balance")
    if not cands:
        return None
    d = cands[0]
    expiring_date = to_date(
        pick(
            d,
            "expiringTime",
            "expireTime",
            "expiringDate",
            "willExpireTime",
            "nearestExpireTime",
        )
    )
    return PointsAccount(
        available=to_int(pick(d, "availablePoints", "available", "points", "balance", "currentPoints")),
        total_earned=to_int(pick(d, "totalPoints", "totalEarnedPoints", "cumulativePoints", "total")),
        frozen=to_int(pick(d, "frozenPoints", "frozen", "freezePoints")),
        expiring=to_int(pick(d, "expiringPoints", "willExpirePoints", "expiring", "nearExpirePoints")),
        expiring_date=expiring_date,
    )


def parse_lottery(payload: Any) -> Optional[LotteryInfo]:
    if payload is None:
        return None
    # 单次消耗积分可能在顶层或 data 节点，做嵌套查找
    cost = 0
    title = "积分抽奖"
    for keys in (("costPoints",), ("pointsPerDraw",), ("consumePoints",), ("drawCost",)):
        for d in find_dicts(payload, *keys):
            cost = to_int(pick(d, *keys))
            title = str(pick(d, "activityName", "name", "activityTitle", "title", default=title)) or title
            if cost:
                break
        if cost:
            break
    prize_dicts: List[Dict[str, Any]] = []
    for keys in (("prizeName", "probability"), ("name", "probability"), ("prizeName", "rate")):
        for lst in find_lists(payload, *keys):
            prize_dicts = lst
            break
        if prize_dicts:
            break
    if not prize_dicts:
        return None
    prizes: List[LotteryPrize] = []
    for p in prize_dicts:
        prob = pick(p, "probability", "rate", "chance", "winRate")
        if isinstance(prob, str) and "%" in prob:
            m = re.search(r"(\d+(?:\.\d+)?)", prob)
            prob_f = float(m.group(1)) / 100.0 if m else 0.0
        elif isinstance(prob, (int, float)) and not isinstance(prob, bool):
            prob_f = float(prob)
        else:
            prob_f = 0.0
        if prob_f > 1:  # 百分数
            prob_f /= 100.0
        value = to_fen(pick(p, "value", "prizeValue", "marketValue", "price")) or 0
        if value == 0:  # 用所需积分反推价值（100 积分=¥1）
            pts = to_int(pick(p, "points", "exchangePoints", "needPoints"))
            value = pts
        prizes.append(
            LotteryPrize(
                name=str(pick(p, "prizeName", "name", "title", default="奖品")),
                probability=prob_f,
                value_fen=value,
            )
        )
    return LotteryInfo(title=title, cost_points=cost, prizes=prizes)


def parse_mall_products(payload: Any) -> List[MallProduct]:
    if payload is None:
        return []
    rows: List[Dict[str, Any]] = []
    for keys in (("productId", "productName"), ("id", "name"), ("productId", "name")):
        for lst in find_lists(payload, *keys):
            rows = lst
            break
        if rows:
            break
    out: List[MallProduct] = []
    for r in rows:
        points = to_int(pick(r, "points", "pointsPrice", "exchangePoints", "needPoints", "score"))
        if points <= 0:
            continue
        value = (
            to_fen(pick(r, "marketValue", "value", "price", "originalPrice", "referencePrice"))
            or points  # 无参考价时按 100 积分=¥1 折算
        )
        out.append(
            MallProduct(
                id=str(pick(r, "productId", "id", default="")),
                name=str(pick(r, "productName", "name", "title", default="商城商品")),
                points=points,
                market_value_fen=value,
                category=str(pick(r, "category", "type", default="")),
            )
        )
    return out


def parse_meals(payload: Any) -> List[Meal]:
    if payload is None:
        return []
    rows: List[Dict[str, Any]] = []
    for keys in (("productId", "productName"), ("id", "name"), ("mealId", "name")):
        for lst in find_lists(payload, *keys):
            rows = lst
            break
        if rows:
            break
    out: List[Meal] = []
    for r in rows:
        price = to_fen(pick(r, "price", "currentPrice", "salePrice", "amount"))
        if price is None:
            continue
        out.append(
            Meal(
                id=str(pick(r, "productId", "id", "mealId", default="")),
                name=str(pick(r, "productName", "name", "title", default="餐品")),
                price_fen=price,
                category=str(pick(r, "category", "categoryName", default="")),
            )
        )
    return out


def parse_prizes(payload: Any) -> List[Prize]:
    if payload is None:
        return []
    rows: List[Dict[str, Any]] = []
    for keys in (("prizeName",), ("name",)):
        for lst in find_lists(payload, *keys):
            rows = lst
            break
        if rows:
            break
    out: List[Prize] = []
    for r in rows:
        out.append(
            Prize(
                name=str(pick(r, "prizeName", "name", default="奖品")),
                won_at=to_date(pick(r, "winTime", "wonTime", "createTime")),
                expire=to_date(pick(r, "expireTime", "expiryTime", "endTime")),
            )
        )
    return out
