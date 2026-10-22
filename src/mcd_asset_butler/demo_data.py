"""离线演示数据：无 MCP Token 时完整跑通全流程。

DemoMCPClient 与 MCPClient 接口一致，返回与麦当劳 MCP Server 文档
描述相符的模拟数据（结构、字段命名遵循官方 README 的 Tool 说明）。
所有日期相对「今天」生成，保证演示素材始终有「临期」戏剧效果。

注意：演示数据仅用于本地演示与测试，不代表任何真实账户；
真实数据请配置 MCD_MCP_TOKEN 后去掉 --demo 使用。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .models import Meal


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d 23:59:59")


def _meals() -> List[Dict[str, Any]]:
    return [
        {"productId": "M1001", "productName": "巨无霸", "category": "汉堡", "price": 2350},
        {"productId": "M1002", "productName": "麦辣鸡腿堡", "category": "汉堡", "price": 2100},
        {"productId": "M1003", "productName": "板烧鸡腿堡", "category": "汉堡", "price": 1950},
        {"productId": "M1004", "productName": "双层吉士堡", "category": "汉堡", "price": 1650},
        {"productId": "M2001", "productName": "薯条（大）", "category": "小食", "price": 1350},
        {"productId": "M2002", "productName": "薯条（中）", "category": "小食", "price": 1050},
        {"productId": "M2003", "productName": "麦乐鸡（5块）", "category": "小食", "price": 1200},
        {"productId": "M2004", "productName": "菠萝派", "category": "小食", "price": 700},
        {"productId": "M3001", "productName": "可口可乐（中）", "category": "饮品", "price": 850},
        {"productId": "M3002", "productName": "香芋派", "category": "小食", "price": 700},
        {"productId": "M4001", "productName": "麦满分套餐", "category": "早餐", "price": 1750},
        {"productId": "M4002", "productName": "脆薯饼", "category": "早餐", "price": 600},
        {"productId": "M5001", "productName": "圆筒冰淇淋", "category": "甜品", "price": 600},
        {"productId": "M5002", "productName": "草莓新地", "category": "甜品", "price": 800},
    ]


class DemoMCPClient:
    """接口与 MCPClient 一致的离线演示客户端。"""

    def __init__(self, **_kwargs: Any) -> None:
        self.session_id = "demo-session"
        self.server_info = {"serverInfo": {"name": "mcd-mcp-demo", "version": "demo"}}

    # ------------------------------------------------------------------ #
    # 生命周期（空实现，保持接口兼容）
    # ------------------------------------------------------------------ #
    def initialize(self) -> Dict[str, Any]:
        return self.server_info

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": n, "description": d}
            for n, d in [
                ("query-my-account", "我的积分查询（演示）"),
                ("query-my-coupons", "我的优惠券查询（演示）"),
                ("query-my-prizes", "查看我的奖品（演示）"),
                ("query-lottery-info", "查看积分抽奖活动信息（演示）"),
                ("mall-points-products", "查询麦麦商城商品列表（演示）"),
                ("available-coupons", "麦麦省券列表查询（演示）"),
                ("auto-bind-coupons", "麦麦省一键领券（演示）"),
                ("campaign-calendar", "活动日历查询工具（演示）"),
                ("query-meals", "查询当前可售卖的餐品列表（演示）"),
                ("calculate-price", "商品价格计算（演示）"),
                ("now-time-info", "获取当前时间信息（演示）"),
                ("query-nearby-stores", "查询附近可用门店（演示）"),
            ]
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        handler = getattr(self, f"_call_{name.replace('-', '_')}", None)
        if handler is None:
            raise KeyError(f"演示模式暂不支持工具 {name}")
        return handler(arguments or {})

    # ------------------------------------------------------------------ #
    # 模拟返回（结构与官方 Tool 说明对齐）
    # ------------------------------------------------------------------ #
    def _call_query_my_account(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "availablePoints": 8642,
                "totalPoints": 23180,
                "frozenPoints": 0,
                "expiringPoints": 2000,
                "expiringTime": _d(7),
            },
        }

    def _call_query_my_coupons(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "coupons": [
                    {
                        "couponId": "C20261001",
                        "couponName": "麦麦省·圆筒冰淇淋立减6元券",
                        "amount": 600,
                        "threshold": 0,
                        "expireTime": _d(2),
                        "couponType": "麦麦省",
                        "status": "可用",
                    },
                    {
                        "couponId": "C20261002",
                        "couponName": "麦麦省·薯条（大）立减8元券",
                        "amount": 800,
                        "threshold": 0,
                        "expireTime": _d(3),
                        "couponType": "麦麦省",
                        "status": "可用",
                    },
                    {
                        "couponId": "C20261003",
                        "couponName": "麦麦省·板烧鸡腿堡半价券",
                        "amount": 975,
                        "threshold": 0,
                        "expireTime": _d(6),
                        "couponType": "麦麦省",
                        "status": "可用",
                    },
                    {
                        "couponId": "C20261004",
                        "couponName": "麦乐送满59减10元券",
                        "amount": 1000,
                        "threshold": 5900,
                        "expireTime": _d(14),
                        "couponType": "麦乐送",
                        "status": "可用",
                    },
                    {
                        "couponId": "C20261005",
                        "couponName": "早餐卡·满15减5元券",
                        "amount": 500,
                        "threshold": 1500,
                        "expireTime": _d(20),
                        "couponType": "早餐卡",
                        "status": "可用",
                    },
                    {
                        "couponId": "C20261006",
                        "couponName": "门店活动·家庭分享桶立减20元券",
                        "amount": 2000,
                        "threshold": 7900,
                        "expireTime": _d(25),
                        "couponType": "门店活动",
                        "status": "可用",
                    },
                    {
                        "couponId": "C20260999",
                        "couponName": "麦麦省·已过期示例券",
                        "amount": 500,
                        "threshold": 0,
                        "expireTime": _d(-3),
                        "couponType": "麦麦省",
                        "status": "已过期",
                    },
                ]
            },
        }

    def _call_query_my_prizes(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "list": [
                    {"prizeName": "圆筒冰淇淋兑换券", "winTime": _d(-10), "expireTime": _d(9)},
                    {"prizeName": "麦麦省满30减6券", "winTime": _d(-30), "expireTime": _d(-2)},
                ],
                "total": 2,
            },
        }

    def _call_query_lottery_info(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "activityName": "麦麦好运轮",
                "costPoints": 50,
                "prizes": [
                    {"prizeName": "谢谢参与", "probability": 0.90, "value": 0},
                    {"prizeName": "圆筒冰淇淋兑换券", "probability": 0.07, "value": 600},
                    {"prizeName": "薯条（中）兑换券", "probability": 0.025, "value": 1050},
                    {"prizeName": "巨无霸套餐兑换券", "probability": 0.005, "value": 3900},
                ],
            },
        }

    def _call_mall_points_products(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "products": [
                    {"productId": "P01", "productName": "麦辣鸡腿堡兑换券", "points": 1500, "marketValue": 2100, "category": "餐品券"},
                    {"productId": "P02", "productName": "巨无霸兑换券", "points": 1800, "marketValue": 2350, "category": "餐品券"},
                    {"productId": "P03", "productName": "薯条（小）兑换券", "points": 600, "marketValue": 750, "category": "餐品券"},
                    {"productId": "P04", "productName": "圆筒冰淇淋兑换券", "points": 400, "marketValue": 600, "category": "餐品券"},
                    {"productId": "P05", "productName": "10元无门槛券", "points": 900, "marketValue": 1000, "category": "优惠券"},
                    {"productId": "P06", "productName": "麦门限定帆布袋", "points": 3200, "marketValue": 2990, "category": "周边"},
                    {"productId": "P07", "productName": "麦乐送免配送费券", "points": 300, "marketValue": 600, "category": "优惠券"},
                ]
            },
        }

    def _call_available_coupons(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "coupons": [
                    {"couponId": "A01", "couponName": "麦麦省·满30减6元券", "amount": 600, "threshold": 3000},
                    {"couponId": "A02", "couponName": "麦麦省·麦乐送免配送费券", "amount": 600, "threshold": 0},
                    {"couponId": "A03", "couponName": "麦麦省·早餐咖啡第二杯半价券", "amount": 700, "threshold": 0},
                ]
            },
        }

    def _call_auto_bind_coupons(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {"code": 0, "data": {"claimed": 3, "message": "已为你领取 3 张麦麦省优惠券"}}

    def _call_campaign_calendar(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "campaigns": [
                    {"name": "麦麦省周三会员日", "startTime": _d(-1), "endTime": _d(60), "status": "进行中", "desc": "每周三会员专享券"},
                    {"name": "万圣节扭扭薯条回归", "startTime": _d(1), "endTime": _d(14), "status": "未开始", "desc": "限定口味限时回归"},
                    {"name": "麦金卡双倍积分日", "startTime": _d(3), "endTime": _d(4), "status": "未开始", "desc": "当天下单积分翻倍"},
                    {"name": "9月麦麦省满减季", "startTime": _d(-30), "endTime": _d(-2), "status": "已结束", "desc": "往期活动"},
                ]
            },
        }

    def _call_query_meals(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {"code": 0, "data": {"meals": _meals()}}

    def _call_calculate_price(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """模拟官方算价：按商品列表累加，抵扣优惠券金额。"""
        items = args.get("items") or args.get("products") or []
        total = 0
        for it in items:
            pid = it.get("productId") or it.get("id")
            qty = int(it.get("quantity", 1) or 1)
            meal = next((m for m in _meals() if m["productId"] == pid), None)
            if meal:
                total += meal["price"] * qty
        coupon = args.get("couponAmount") or args.get("coupon") or 0
        discount = min(int(coupon), total)
        return {
            "code": 0,
            "data": {
                "totalAmount": total,
                "discountAmount": discount,
                "payAmount": total - discount,
            },
        }

    def _call_now_time_info(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        from datetime import datetime

        now = datetime.now()
        return {
            "code": 0,
            "data": {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": "一二三四五六日"[now.weekday()],
                "timestamp": int(now.timestamp()),
            },
        }

    def _call_query_nearby_stores(self, _a: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": 0,
            "data": {
                "stores": [
                    {"storeId": "S001", "storeName": "麦当劳（科技路餐厅）", "distance": "480m"},
                    {"storeId": "S002", "storeName": "麦当劳（高新四路餐厅）", "distance": "1.2km"},
                ]
            },
        }

    # ------------------------------------------------------------------ #
    # 高层封装（与 MCPClient 同名）
    # ------------------------------------------------------------------ #
    def query_points_account(self):
        return self._call_query_my_account({})

    def query_my_coupons(self):
        return self._call_query_my_coupons({})

    def query_my_prizes(self):
        return self._call_query_my_prizes({})

    def query_lottery_info(self):
        return self._call_query_lottery_info({})

    def query_mall_products(self):
        return self._call_mall_points_products({})

    def query_available_coupons(self):
        return self._call_available_coupons({})

    def auto_bind_coupons(self):
        return self._call_auto_bind_coupons({})

    def query_campaign_calendar(self):
        return self._call_campaign_calendar({})

    def query_now_time(self):
        return self._call_now_time_info({})

    def query_meals(self):
        return self._call_query_meals({})
