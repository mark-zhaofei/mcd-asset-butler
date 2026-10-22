"""HTML 可视化报告生成器：单文件、零外部资源、浅色主题。

产出 examples/report.html 风格的「资产体检报告」：
- 资产总览卡片（券 / 积分 / 奖品 / 总价值 / 风险）
- 过期时间线（SVG 横条，7 天内到期高亮）
- 积分处置性价比对比（抽奖 EV vs 商城兑换 vs 直接抵扣）
- 商城兑换排行榜
- 临期券推荐用法
"""

from __future__ import annotations

import html
from datetime import date
from typing import List, Optional

from .engine import AssetSummary, DisposalOption, CouponUsage, StrategyReport
from .models import AssetLedger

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
       background: #faf7f2; color: #2b2b2b; padding: 32px 20px; }
.wrap { max-width: 920px; margin: 0 auto; }
.header { background: linear-gradient(135deg, #da291c, #ff8a1e); color: #fff;
          border-radius: 16px; padding: 28px 32px; margin-bottom: 20px; }
.header h1 { font-size: 26px; margin-bottom: 6px; }
.header p { opacity: .92; font-size: 13px; }
.badge { display: inline-block; background: rgba(255,255,255,.22); border-radius: 999px;
         padding: 2px 12px; font-size: 12px; margin-left: 8px; vertical-align: middle; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
.card { background: #fff; border-radius: 12px; padding: 16px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.card .label { font-size: 12px; color: #8a8a8a; margin-bottom: 6px; }
.card .value { font-size: 22px; font-weight: 700; }
.card .sub { font-size: 12px; color: #a0a0a0; margin-top: 4px; }
.card.risk .value { color: #da291c; }
section { background: #fff; border-radius: 12px; padding: 22px 24px; margin-bottom: 16px;
          box-shadow: 0 1px 4px rgba(0,0,0,.06); }
h2 { font-size: 17px; margin-bottom: 14px; padding-left: 10px; border-left: 4px solid #da291c; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: #8a8a8a; font-weight: 500; padding: 8px 10px; border-bottom: 2px solid #f0ebe3; }
td { padding: 9px 10px; border-bottom: 1px solid #f5f1ea; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.bar-wrap { background: #f3efe8; border-radius: 6px; height: 10px; overflow: hidden; min-width: 90px; }
.bar { height: 100%; border-radius: 6px; background: linear-gradient(90deg, #ffc72c, #da291c); }
.bar.blue { background: linear-gradient(90deg, #7db8ff, #3a7bd5); }
.bar.green { background: linear-gradient(90deg, #9be15d, #00b894); }
.tag { display: inline-block; font-size: 11px; border-radius: 4px; padding: 1px 7px; margin-left: 6px; }
.tag.risk { background: #fdecea; color: #da291c; }
.tag.ok { background: #e8f8ef; color: #00a060; }
.tag.warn { background: #fff6e0; color: #b8860b; }
.note { background: #fff8e6; border: 1px solid #ffe9b0; border-radius: 8px;
        padding: 10px 14px; font-size: 13px; margin: 6px 0; }
.timeline { margin: 10px 0; }
.tl-row { display: flex; align-items: center; margin: 7px 0; font-size: 13px; }
.tl-name { width: 260px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tl-track { flex: 1; background: #f3efe8; border-radius: 6px; height: 18px; position: relative; }
.tl-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px;
           background: linear-gradient(90deg, #ffc72c, #da291c); }
.tl-fill.far { background: linear-gradient(90deg, #b8e0ff, #3a7bd5); }
.tl-days { width: 76px; text-align: right; flex-shrink: 0; color: #666; font-size: 12px; }
.footer { text-align: center; color: #a8a8a8; font-size: 12px; margin-top: 24px; line-height: 1.8; }
code { background: #f6f2eb; border-radius: 4px; padding: 1px 6px; font-size: 12px; }
"""


def _fen(v: int) -> str:
    return f"¥{v / 100:.2f}"


def _esc(s: str) -> str:
    return html.escape(str(s))


def _bar_ratio(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return max(0.02, min(1.0, value / max_value))


def render_report(
    ledger: AssetLedger,
    report: StrategyReport,
    meals_count: int = 0,
    demo: bool = True,
    warnings: Optional[List[str]] = None,
) -> str:
    s: AssetSummary = report.summary
    parts: List[str] = []
    parts.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append("<title>麦麦资产体检报告</title>")
    parts.append(f"<style>{_CSS}</style></head><body><div class='wrap'>")

    # ---------- 头部 ----------
    mode = "离线演示数据" if demo else "真实账户数据"
    parts.append(
        f"<div class='header'><h1>🍔 麦麦资产体检报告"
        f"<span class='badge'>{mode}</span></h1>"
        f"<p>生成日期 {date.today().isoformat()} · 麦当劳积分 &amp; 优惠券资产一站式管理</p></div>"
    )

    # ---------- 总览卡片 ----------
    parts.append("<div class='cards'>")
    parts.append(
        f"<div class='card'><div class='label'>资产总价值</div>"
        f"<div class='value'>{_fen(s.total_value_fen)}</div>"
        f"<div class='sub'>券 {len(ledger.coupons)} 张 + 积分 {ledger.points.available if ledger.points else 0:,}</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>优惠券资产</div>"
        f"<div class='value'>{_fen(s.coupon_value_fen)}</div>"
        f"<div class='sub'>{len(ledger.coupons)} 张可用</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>积分资产（100积分=¥1）</div>"
        f"<div class='value'>{_fen(s.points_value_fen)}</div>"
        f"<div class='sub'>冻结 {ledger.points.frozen if ledger.points else 0:,} · 奖品 {s.prize_count} 件</div></div>"
    )
    risk_pct = f"{s.at_risk_ratio * 100:.1f}%"
    parts.append(
        f"<div class='card risk'><div class='label'>⚠️ 7 天内过期风险</div>"
        f"<div class='value'>{_fen(s.total_at_risk_fen)}</div>"
        f"<div class='sub'>占总资产 {risk_pct}</div></div>"
    )
    parts.append("</div>")

    # ---------- 行动建议 ----------
    parts.append("<section><h2>📋 行动建议</h2>")
    for n in report.notes:
        parts.append(f"<div class='note'>{_esc(n)}</div>")
    parts.append("</section>")

    # ---------- 过期时间线 ----------
    at_risk: List[tuple] = []
    for c in ledger.coupons:
        if c.at_risk and c.days_left is not None:
            at_risk.append((c.title, f"券 · {_fen(c.amount_fen)}", c.days_left))
    if ledger.points and ledger.points.expiring > 0 and ledger.points.days_left is not None:
        at_risk.append(
            (f"{ledger.points.expiring:,} 积分即将过期", "积分", ledger.points.days_left)
        )
    if at_risk:
        parts.append("<section><h2>⏰ 过期时间线</h2><div class='timeline'>")
        max_days = 14
        for name, kind, days in at_risk:
            ratio = _bar_ratio(max(days, 0), max_days)
            cls = "" if days <= 7 else "far"
            parts.append(
                f"<div class='tl-row'><div class='tl-name' title='{_esc(name)}'>{_esc(name)}"
                f"<span class='tag {'risk' if days <= 3 else 'warn'}'>{kind}</span></div>"
                f"<div class='tl-track'><div class='tl-fill {cls}' style='width:{ratio * 100:.0f}%'></div></div>"
                f"<div class='tl-days'>{days} 天</div></div>"
            )
        parts.append("</div></section>")

    # ---------- 积分处置性价比 ----------
    if report.disposal_options:
        parts.append("<section><h2>🧮 积分处置性价比（每 100 积分可换价值）</h2><table>")
        parts.append(
            "<tr><th style='width:34%'>处置方式</th><th style='width:26%'>性价比</th>"
            "<th style='width:22%'>对比</th><th>说明</th></tr>"
        )
        max_v = max(o.value_fen_per_100_points for o in report.disposal_options)
        for i, o in enumerate(report.disposal_options):
            bar_cls = ["", "blue", "green"][i % 3]
            tag = "<span class='tag ok'>推荐</span>" if i == 0 else ""
            parts.append(
                f"<tr><td>{_esc(o.name)}{tag}</td>"
                f"<td><b>¥{o.value_fen_per_100_points / 100:.2f}</b></td>"
                f"<td><div class='bar-wrap'><div class='bar {bar_cls}' "
                f"style='width:{_bar_ratio(o.value_fen_per_100_points, max_v) * 100:.0f}%'></div></div></td>"
                f"<td>{_esc(o.detail)}</td></tr>"
            )
        parts.append("</table>")
        if report.best_disposal:
            parts.append(
                f"<div class='note'>💡 当前最优：{_esc(report.best_disposal.name)}"
                f"（每 100 积分 ≈ ¥{report.best_disposal.value_fen_per_100_points / 100:.2f}）"
                f"{('，风险提示：' + _esc(report.best_disposal.risk)) if report.best_disposal.risk else ''}</div>"
            )
        parts.append("</section>")

    # ---------- 商城兑换排行榜 ----------
    if ledger.mall_products:
        ranked = sorted(ledger.mall_products, key=lambda p: p.value_per_100_points, reverse=True)
        parts.append("<section><h2>🏪 积分商城兑换排行榜</h2><table>")
        parts.append(
            "<tr><th>#</th><th>商品</th><th>所需积分</th><th>参考价值</th>"
            "<th style='width:24%'>性价比（每100积分）</th></tr>"
        )
        max_v = max(p.value_per_100_points for p in ranked)
        for i, p in enumerate(ranked[:10], 1):
            parts.append(
                f"<tr><td>{i}</td><td>{_esc(p.name)}</td><td>{p.points:,}</td>"
                f"<td>{_fen(p.market_value_fen)}</td>"
                f"<td><div style='display:flex;align-items:center;gap:8px'>"
                f"<div class='bar-wrap' style='flex:1'><div class='bar' "
                f"style='width:{_bar_ratio(p.value_per_100_points, max_v) * 100:.0f}%'></div></div>"
                f"<span>¥{p.value_per_100_points / 100:.2f}</span></div></td></tr>"
            )
        parts.append("</table></section>")

    # ---------- 临期券推荐用法 ----------
    if report.coupon_usages:
        parts.append("<section><h2>🧾 临期券推荐用法（官方算价口径校验）</h2><table>")
        parts.append(
            "<tr><th>优惠券</th><th>剩余</th><th>推荐搭配</th><th>原价</th>"
            "<th>券后实付</th><th>优惠力度</th></tr>"
        )
        for u in report.coupon_usages[:8]:
            combo = " + ".join(m.name for m in u.combo)
            days = u.coupon.days_left
            days_txt = f"{days} 天" if days is not None else "—"
            parts.append(
                f"<tr><td>{_esc(u.coupon.title)}</td>"
                f"<td><span class='tag {'risk' if (days or 99) <= 3 else 'warn'}'>{days_txt}</span></td>"
                f"<td>{_esc(combo)}</td><td>{_fen(u.combo_price_fen)}</td>"
                f"<td><b style='color:#da291c'>{_fen(u.pay_fen)}</b></td>"
                f"<td>{u.saved_ratio * 100:.0f}%</td></tr>"
            )
        parts.append("</table>")
        parts.append(
            f"<div class='note'>搭配基于 {meals_count} 个在售餐品计算，"
            "下单前请以 App 内 calculate-price 实时结果为准。</div>"
        )
        parts.append("</section>")

    # ---------- 可领取 ----------
    if ledger.claimable_coupons:
        parts.append("<section><h2>🎁 麦麦省待领取优惠券</h2><table>")
        parts.append("<tr><th>优惠券</th><th>面额</th><th>门槛</th></tr>")
        for c in ledger.claimable_coupons:
            parts.append(
                f"<tr><td>{_esc(c.title)}</td><td>{_fen(c.amount_fen)}</td>"
                f"<td>{_fen(c.threshold_fen) if c.threshold_fen else '无门槛'}</td></tr>"
            )
        parts.append("</table>")
        parts.append("<div class='note'>💡 运行 <code>mcd-asset-butler claim</code> 可一键领取全部麦麦省券。</div>")
        parts.append("</section>")

    # ---------- 降级警告 ----------
    if warnings:
        parts.append("<section><h2>⚠️ 数据采集提示</h2>")
        for w in warnings:
            parts.append(f"<div class='note'>{_esc(w)}</div>")
        parts.append("</section>")

    parts.append(
        "<div class='footer'>由 <b>mcd-asset-butler</b> 生成 · 基于麦当劳中国官方 MCP Server<br>"
        "本报告仅供参考，不构成任何专业建议；餐品、价格与库存以麦当劳官方渠道实时结果为准<br>"
        "1024 程序员节 · 麦当劳程序员创意开发大赛参赛作品</div>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)
