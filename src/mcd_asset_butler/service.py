"""服务层：把 MCP 客户端返回的原始数据编排为统一资产账本。

每个工具调用都是独立容错的：单个工具失败（如权限、参数变化）只降级
该部分数据，不影响整体体检，保证「部分失败也能出报告」。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .mcp_client import MCPClient, MCPError
from .models import (
    AssetLedger,
    Coupon,
    LotteryInfo,
    MallProduct,
    Meal,
    PointsAccount,
    Prize,
    parse_coupons,
    parse_lottery,
    parse_mall_products,
    parse_meals,
    parse_points,
    parse_prizes,
)


class Collector:
    """资产账本采集器。"""

    def __init__(self, client, verbose: bool = False) -> None:
        self.client = client
        self.verbose = verbose
        self.warnings: List[str] = []

    def _safe(self, name: str, fn):
        try:
            return fn()
        except MCPError as e:
            self.warnings.append(f"{name}: {e}")
            return None
        except Exception as e:  # 解析异常也不应中断整体流程
            self.warnings.append(f"{name}: 数据解析异常 {e}")
            return None

    def collect(self, with_meals: bool = True) -> Tuple[AssetLedger, List[Meal]]:
        ledger = AssetLedger()
        meals: List[Meal] = []

        payload = self._safe("query-my-account", self.client.query_points_account)
        ledger.points = parse_points(payload)

        payload = self._safe("query-my-coupons", self.client.query_my_coupons)
        ledger.coupons = parse_coupons(payload)

        payload = self._safe("query-my-prizes", self.client.query_my_prizes)
        ledger.prizes = parse_prizes(payload)

        payload = self._safe("query-lottery-info", self.client.query_lottery_info)
        ledger.lottery = parse_lottery(payload)

        payload = self._safe("mall-points-products", self.client.query_mall_products)
        ledger.mall_products = parse_mall_products(payload)

        payload = self._safe("available-coupons", self.client.query_available_coupons)
        ledger.claimable_coupons = parse_coupons(payload)

        if with_meals:
            # 门店菜单用于临期券用法匹配；接口可能需要门店参数，失败则降级
            payload = self._safe("query-meals", getattr(self.client, "query_meals", lambda: None))
            meals = parse_meals(payload)

        return ledger, meals
