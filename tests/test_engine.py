"""引擎与解析器单元测试：python -m unittest discover -s tests -v"""

import unittest
from datetime import date, timedelta

from mcd_asset_butler.engine import build_strategy, disposal_options, plan_coupon_usages, summarize
from mcd_asset_butler.models import (
    AssetLedger,
    Coupon,
    LotteryInfo,
    LotteryPrize,
    MallProduct,
    Meal,
    PointsAccount,
    parse_coupons,
    parse_lottery,
    parse_mall_products,
    parse_meals,
    parse_points,
    to_date,
    to_fen,
    to_int,
)


class TestToFen(unittest.TestCase):
    def test_int_is_fen(self):
        self.assertEqual(to_fen(600), 600)       # 600 分 = ¥6
        self.assertEqual(to_fen(2350), 2350)

    def test_float_is_yuan(self):
        self.assertEqual(to_fen(6.0), 600)
        self.assertEqual(to_fen(13.5), 1350)

    def test_strings(self):
        self.assertEqual(to_fen("¥13.5"), 1350)
        self.assertEqual(to_fen("13.5元"), 1350)
        self.assertEqual(to_fen("600分"), 600)
        self.assertEqual(to_fen("1350"), 1350)
        self.assertIsNone(to_fen("abc"))
        self.assertIsNone(to_fen(None))


class TestToDate(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(to_date("2026-10-25 23:59:59"), date(2026, 10, 25))
        self.assertEqual(to_date("2026-10-25T10:00:00+08:00"), date(2026, 10, 25))
        self.assertEqual(to_date("2026/10/25"), date(2026, 10, 25))
        self.assertEqual(to_date("2026.10.25"), date(2026, 10, 25))

    def test_timestamps(self):
        import datetime as _dt

        ts = int(_dt.datetime(2026, 10, 25, 0, 0, 0).timestamp())
        self.assertEqual(to_date(ts), date(2026, 10, 25))  # 秒
        self.assertEqual(to_date(ts * 1000), date(2026, 10, 25))  # 毫秒


class TestParsers(unittest.TestCase):
    def test_parse_points_nested(self):
        payload = {"code": 0, "data": {"availablePoints": 8642, "expiringPoints": 2000, "expiringTime": "2026-11-01 00:00:00"}}
        p = parse_points(payload)
        self.assertEqual(p.available, 8642)
        self.assertEqual(p.expiring, 2000)
        self.assertEqual(p.expiring_date, date(2026, 11, 1))

    def test_parse_coupons_filters_expired(self):
        payload = {
            "data": {
                "coupons": [
                    {"couponId": "1", "couponName": "A券", "amount": 600, "threshold": 0, "expireTime": "2026-12-01", "status": "可用"},
                    {"couponId": "2", "couponName": "B券", "amount": 500, "expireTime": "2026-10-01", "status": "已过期"},
                ]
            }
        }
        coupons = parse_coupons(payload)
        self.assertEqual(len(coupons), 1)
        self.assertEqual(coupons[0].title, "A券")
        self.assertEqual(coupons[0].amount_fen, 600)

    def test_parse_lottery_nested(self):
        payload = {
            "data": {
                "activityName": "麦麦好运轮",
                "costPoints": 50,
                "prizes": [
                    {"prizeName": "谢谢参与", "probability": 0.9, "value": 0},
                    {"prizeName": "冰淇淋券", "probability": 0.1, "value": 600},
                ],
            }
        }
        lot = parse_lottery(payload)
        self.assertEqual(lot.title, "麦麦好运轮")
        self.assertEqual(lot.cost_points, 50)
        self.assertAlmostEqual(lot.ev_fen_per_draw, 60.0)

    def test_parse_lottery_percent(self):
        payload = {"data": {"costPoints": 20, "prizes": [{"prizeName": "券", "rate": "50%", "value": 400}]}}
        lot = parse_lottery(payload)
        self.assertEqual(lot.prizes[0].probability, 0.5)

    def test_parse_mall_products(self):
        payload = {"data": {"products": [{"productId": "P1", "productName": "汉堡券", "points": 1500, "marketValue": 2100}]}}
        products = parse_mall_products(payload)
        self.assertEqual(len(products), 1)
        self.assertAlmostEqual(products[0].value_per_100_points, 140.0)

    def test_parse_meals(self):
        payload = {"data": {"meals": [{"productId": "M1", "productName": "巨无霸", "price": 2350}]}}
        meals = parse_meals(payload)
        self.assertEqual(meals[0].name, "巨无霸")
        self.assertEqual(meals[0].price_fen, 2350)


class TestEngine(unittest.TestCase):
    def _ledger(self):
        ledger = AssetLedger()
        ledger.points = PointsAccount(available=8642, total_earned=23180, expiring=2000,
                                      expiring_date=date.today() + timedelta(days=7))
        ledger.coupons = [
            Coupon(id="1", title="麦麦省·圆筒冰淇淋立减6元券", amount_fen=600, threshold_fen=0,
                   expire=date.today() + timedelta(days=2)),
            Coupon(id="2", title="麦乐送满59减10元券", amount_fen=1000, threshold_fen=5900,
                   expire=date.today() + timedelta(days=14)),
        ]
        ledger.lottery = LotteryInfo(
            title="麦麦好运轮", cost_points=50,
            prizes=[LotteryPrize("谢谢参与", 0.9, 0), LotteryPrize("冰淇淋券", 0.1, 600)],
        )
        ledger.mall_products = [
            MallProduct(id="P1", name="麦辣鸡腿堡兑换券", points=1500, market_value_fen=2100),
            MallProduct(id="P2", name="限定周边", points=3200, market_value_fen=2990),
        ]
        return ledger

    def test_summarize(self):
        s = summarize(self._ledger())
        self.assertEqual(s.coupon_value_fen, 1600)
        self.assertEqual(s.coupon_at_risk_fen, 600)      # 只有 2 天过期的计入风险
        self.assertEqual(s.points_value_fen, 8642)       # 100 积分 = ¥1
        self.assertEqual(s.points_at_risk_fen, 2000)
        self.assertEqual(s.total_value_fen, 1600 + 8642)

    def test_disposal_ranking(self):
        options = disposal_options(self._ledger())
        names = [o.name for o in options]
        # 商城兑换 140 分/100积分 > 抽奖 EV 120 > 直接抵扣 100
        self.assertTrue(names[0].startswith("积分商城兑换"))
        self.assertTrue(any("积分抽奖" in n for n in names))
        self.assertGreater(options[0].value_fen_per_100_points, options[-1].value_fen_per_100_points)

    def test_scope_matching(self):
        meals = [
            Meal(id="M1", name="圆筒冰淇淋", price_fen=600),
            Meal(id="M2", name="菠萝派", price_fen=700),
        ]
        ledger = self._ledger()
        usages = plan_coupon_usages(ledger, meals)
        by_title = {u.coupon.title: u for u in usages}
        usage = by_title["麦麦省·圆筒冰淇淋立减6元券"]
        # 券面提及圆筒冰淇淋 → 只搭配圆筒，实付 0
        self.assertEqual(usage.combo[0].name, "圆筒冰淇淋")
        self.assertEqual(usage.pay_fen, 0)

    def test_threshold_respected(self):
        meals = [Meal(id="M1", name="巨无霸", price_fen=2350)]
        ledger = self._ledger()
        usages = plan_coupon_usages(ledger, meals)
        # 满59减10 无法用单品凑到门槛 → 无推荐用法
        self.assertNotIn("麦乐送满59减10元券", {u.coupon.title for u in usages})

    def test_strategy_notes(self):
        report = build_strategy(self._ledger(), [])
        self.assertTrue(any("过期" in n for n in report.notes))
        self.assertIsNotNone(report.best_disposal)


if __name__ == "__main__":
    unittest.main()
