"""命令行入口。

用法：
    python -m mcd_asset_butler <命令> [--demo] [--token xxx] [--out report.html]

命令：
    checkup    资产体检：券 / 积分 / 奖品 / 过期风险
    strategy   保值策略：积分处置性价比 + 临期券推荐用法
    claim      一键领取麦麦省全部可领优惠券
    exchange   积分商城兑换性价比排行榜
    lottery    积分抽奖期望值分析（--draw 执行一次抽奖）
    report     生成 HTML 可视化体检报告
    dashboard  一键全流程：体检 + 策略 + 报告
    tools      列出麦当劳 MCP Server 当前可用工具

未配置 Token 时自动进入 --demo 离线演示模式（数据为模拟）。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import List, Optional

from . import __version__
from .engine import build_strategy
from .mcp_client import MCPClient, MCPError
from .models import AssetLedger, Meal, parse_meals
from .report import render_report
from .service import Collector


# --------------------------------------------------------------------- #
# 终端渲染 helpers
# --------------------------------------------------------------------- #
def _fen(v: int) -> str:
    return f"¥{v / 100:.2f}"


def _disp_width(s: str) -> int:
    """字符串显示宽度：CJK 全角字符按 2 列计。"""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _disp_width(s))


def _hr(ch: str = "─", n: int = 64) -> str:
    return ch * n


def _table(headers: List[str], rows: List[List[str]], widths: Optional[List[int]] = None) -> str:
    if widths is None:
        widths = [max(_disp_width(str(r[i])) for r in rows + [headers]) for i in range(len(headers))]
    line = "  ".join(_pad(h, widths[i]) for i, h in enumerate(headers))
    sep = "  ".join("─" * widths[i] for i in range(len(headers)))
    body = "\n".join("  ".join(_pad(str(c), widths[i]) for i, c in enumerate(r)) for r in rows)
    return f"{line}\n{sep}\n{body}"


def _days_text(d: Optional[int]) -> str:
    if d is None:
        return "长期有效"
    if d < 0:
        return "已过期"
    return f"{d} 天后"


# --------------------------------------------------------------------- #
# 客户端工厂
# --------------------------------------------------------------------- #
def make_client(args) -> object:
    if args.demo or not (args.token or os.environ.get("MCD_MCP_TOKEN")):
        from .demo_data import DemoMCPClient

        return DemoMCPClient()
    return MCPClient(token=args.token, url=args.url)


# --------------------------------------------------------------------- #
# 各命令
# --------------------------------------------------------------------- #
def cmd_checkup(ledger: AssetLedger, args) -> None:
    from .engine import summarize

    s = summarize(ledger)
    print()
    print("🍔 麦麦资产体检".center(60, " "))
    print(_hr())
    print(f"  优惠券可用 {len(ledger.coupons):>3} 张   面额合计 {_fen(s.coupon_value_fen):>10}")
    if ledger.points:
        p = ledger.points
        print(
            f"  积分可用 {p.available:>7,}   折算金额 {_fen(s.points_value_fen):>10}"
            f"（累计 {p.total_earned:,} / 冻结 {p.frozen:,}）"
        )
        if p.expiring > 0:
            print(f"  ⚠️ 即将过期 {p.expiring:,} 积分（{_days_text(p.days_left)}，≈ {_fen(s.points_at_risk_fen)}）")
    print(f"  奖品记录 {s.prize_count:>3} 件")
    print(f"  ── 资产总价值 {_fen(s.total_value_fen)}，其中 7 天内过期风险 {_fen(s.total_at_risk_fen)}"
          f"（{s.at_risk_ratio * 100:.1f}%）")
    print(_hr())
    if ledger.coupons:
        rows = []
        for c in sorted(ledger.coupons, key=lambda x: (x.days_left if x.days_left is not None else 999)):
            flag = "⚠️" if c.at_risk else "  "
            rows.append(
                [
                    flag + " " + c.title[:26],
                    _fen(c.amount_fen),
                    _fen(c.threshold_fen) if c.threshold_fen else "无门槛",
                    _days_text(c.days_left),
                ]
            )
        print(_table(["优惠券", "面额", "门槛", "到期"], rows, [30, 10, 10, 12]))
    if s.total_at_risk_fen == 0:
        print("\n✅ 7 天内无过期风险，资产状态健康。")


def cmd_strategy(report, args) -> None:
    print()
    print("🧮 积分处置性价比（每 100 积分可换价值，从优到劣）".center(60, " "))
    print(_hr())
    rows = []
    for i, o in enumerate(report.disposal_options):
        mark = "★" if i == 0 else " "
        rows.append(
            [
                mark + " " + o.name[:32],
                f"¥{o.value_fen_per_100_points / 100:.2f}",
                o.detail[:40],
            ]
        )
    if rows:
        print(_table(["处置方式", "性价比", "说明"], rows, [36, 10, 42]))
    if report.best_disposal:
        print(f"\n💡 当前最优：{report.best_disposal.name}")
        if report.best_disposal.risk:
            print(f"   风险提示：{report.best_disposal.risk}")
    print()
    print("🧾 临期券推荐用法".center(60, " "))
    print(_hr())
    if report.coupon_usages:
        rows = []
        for u in report.coupon_usages[:8]:
            combo = "+".join(m.name for m in u.combo)
            rows.append(
                [
                    u.coupon.title[:24],
                    _days_text(u.coupon.days_left),
                    combo[:20],
                    _fen(u.combo_price_fen),
                    _fen(u.pay_fen),
                    f"{u.saved_ratio * 100:.0f}%",
                ]
            )
        print(_table(["优惠券", "剩余", "推荐搭配", "原价", "券后实付", "力度"], rows, [26, 10, 22, 9, 10, 7]))
    else:
        print("  （无临期券或未获取到门店菜单数据）")


def cmd_exchange(ledger: AssetLedger, args) -> None:
    print()
    print("🏪 积分商城兑换性价比排行榜".center(60, " "))
    print(_hr())
    ranked = sorted(ledger.mall_products, key=lambda p: p.value_per_100_points, reverse=True)
    if not ranked:
        print("  未获取到商城商品数据（可能接口需要更多参数，已跳过）")
        return
    rows = []
    for i, p in enumerate(ranked[:12], 1):
        rows.append([str(i), p.name[:24], f"{p.points:,}", _fen(p.market_value_fen), f"¥{p.value_per_100_points / 100:.2f}"])
    print(_table(["#", "商品", "积分", "参考价值", "每100积分价值"], rows, [4, 26, 8, 10, 14]))
    print("\n  性价比 = 参考价值 ÷ 所需积分 × 100；数值越高越划算")


def cmd_lottery(ledger: AssetLedger, client, args) -> None:
    print()
    print("🎰 积分抽奖期望值分析".center(60, " "))
    print(_hr())
    lot = ledger.lottery
    if not lot or not lot.prizes:
        print("  未获取到抽奖活动信息")
        return
    print(f"  活动：{lot.title}    单次消耗：{lot.cost_points} 积分")
    print(_hr())
    rows = []
    for p in sorted(lot.prizes, key=lambda x: -x.probability):
        rows.append([p.name[:24], f"{p.probability * 100:.2f}%", _fen(p.value_fen), f"{p.probability * p.value_fen / 100:.3f}"])
    print(_table(["奖品", "概率", "估值", "期望贡献"], rows, [26, 10, 10, 12]))
    ev = lot.ev_fen_per_draw
    cost_fen = lot.cost_points * ledger.point_rate_fen
    print(f"\n  单次期望回报：{_fen(round(ev))}    单次成本：{_fen(cost_fen)}")
    ratio = ev / cost_fen if cost_fen else 0
    verdict = (
        "期望值高于成本，可以小额尝试" if ratio > 1.05
        else "期望值≈成本，纯娱乐" if ratio > 0.95
        else "期望值低于成本，不建议投入"
    )
    print(f"  期望成本比：{ratio:.2f}  →  {verdict}")
    print("  ⚠️ 期望值不代表实际所得，请理性投入，量力而行")
    if args.draw:
        try:
            result = client.call_tool("draw-lottery", {})
            print(f"\n  🎲 抽奖结果：{result}")
        except MCPError as e:
            print(f"\n  ❌ 抽奖失败：{e}")


def cmd_claim(client, args) -> None:
    print()
    print("🎁 一键领取麦麦省优惠券".center(60, " "))
    print(_hr())
    try:
        result = client.auto_bind_coupons()
        print(f"  {result}")
    except MCPError as e:
        print(f"  ❌ 领取失败：{e}")


def cmd_tools(client, args) -> None:
    print()
    print("🔧 麦当劳 MCP Server 工具列表".center(60, " "))
    print(_hr())
    try:
        tools = client.list_tools()
    except MCPError as e:
        print(f"  ❌ 获取失败：{e}")
        return
    if not tools:
        print("  （无工具或未初始化）")
        return
    rows = [[t.get("name", "?"), (t.get("description") or "")[:44]] for t in tools]
    print(_table(["Tool", "Description"], rows, [28, 48]))
    print(f"\n  共 {len(tools)} 个工具")


# --------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    # 公共参数：主解析器与子解析器均可识别（两种位置都能写）
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--token", default=argparse.SUPPRESS, help="麦当劳 MCP Token（或设置环境变量 MCD_MCP_TOKEN）")
    common.add_argument("--url", default=argparse.SUPPRESS, help="MCP Server 地址")
    common.add_argument("--demo", action="store_true", default=argparse.SUPPRESS, help="离线演示模式（模拟数据，无需 Token）")
    common.add_argument("--out", default=argparse.SUPPRESS, help="HTML 报告输出路径")

    p = argparse.ArgumentParser(
        prog="mcd-asset-butler",
        parents=[common],
        description="麦当劳积分 & 优惠券资产管家：体检 / 保值策略 / 一键执行 / 可视化报告",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.set_defaults(token=None, url="https://mcp.mcd.cn", demo=False, out="mcd-asset-report.html")

    sub = p.add_subparsers(dest="command")

    sub.add_parser("checkup", parents=[common], help="资产体检")
    sub.add_parser("strategy", parents=[common], help="保值策略")
    sub.add_parser("claim", parents=[common], help="一键领麦麦省券")
    sub.add_parser("exchange", parents=[common], help="商城兑换性价比榜")
    lot = sub.add_parser("lottery", parents=[common], help="抽奖期望值分析")
    lot.add_argument("--draw", action="store_true", help="执行一次抽奖")
    sub.add_parser("report", parents=[common], help="生成 HTML 报告")
    sub.add_parser("dashboard", parents=[common], help="一键全流程")
    sub.add_parser("tools", parents=[common], help="列出 MCP 工具")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "dashboard"

    if command == "tools":
        cmd_tools(make_client(args), args)
        return 0

    client = make_client(args)
    demo = not (args.token or os.environ.get("MCD_MCP_TOKEN")) or args.demo

    if command == "claim":
        cmd_claim(client, args)
        return 0

    print(f"\n🔗 正在连接麦当劳 MCP Server（{'演示模式' if demo else '真实账户'}）...")
    collector = Collector(client)
    ledger, meals = collector.collect(with_meals=command in ("strategy", "report", "dashboard"))
    for w in collector.warnings:
        print(f"  ⚠️ {w}")

    if command == "checkup":
        cmd_checkup(ledger, args)
    elif command == "strategy":
        cmd_strategy(build_strategy(ledger, meals), args)
    elif command == "exchange":
        cmd_exchange(ledger, args)
    elif command == "lottery":
        cmd_lottery(ledger, client, args)
    elif command == "report":
        report = build_strategy(ledger, meals)
        html_text = render_report(ledger, report, meals_count=len(meals), demo=demo, warnings=collector.warnings)
        out = args.out or "mcd-asset-report.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"\n📊 报告已生成：{os.path.abspath(out)}")
        print("   用浏览器打开即可查看资产体检可视化报告")
    else:  # dashboard
        cmd_checkup(ledger, args)
        report = build_strategy(ledger, meals)
        cmd_strategy(report, args)
        html_text = render_report(ledger, report, meals_count=len(meals), demo=demo, warnings=collector.warnings)
        out = args.out or "mcd-asset-report.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"\n📊 HTML 报告已生成：{os.path.abspath(out)}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
