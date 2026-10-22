#!/usr/bin/env python3
"""一键发布到 GitHub 并提交大赛报名 Issue。

前置条件：
    1. 本地仓库已 git commit（本脚本读取 git ls-files 的文件清单）
    2. 环境变量 GITHUB_TOKEN 已设置（GitHub Personal Access Token，
       需要 repo 与 public_repo 权限；仅从环境变量读取，不落盘）

用法：
    GITHUB_TOKEN=ghp_xxxx python tools/publish_github.py
    GITHUB_TOKEN=ghp_xxxx python tools/publish_github.py --dry-run   # 只打印计划

动作：
    1. 创建公开仓库 mark-zhaofei/mcd-asset-butler
    2. 通过 Contents API 上传全部受版本管理的文件
    3. 添加 topics（可发现性）
    4. 启用 GitHub Pages（examples/report.html 变成在线演示链接）
    5. Star 自己的仓库（Star > 0 才能进入排行榜）
    6. 在 M-China-Official/mcd-developer-innovation-challenge 提交报名 Issue
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER = "mark-zhaofei"
REPO = "mcd-asset-butler"
ISSUE_REPO = "M-China-Official/mcd-developer-innovation-challenge"
API = "https://api.github.com"

REPO_META = {
    "name": REPO,
    "description": "🍔 麦当劳积分 & 优惠券资产管家：资产体检 / 保值策略（积分处置EV·临期券最优用法）/ 一键执行 / 可视化报告 — 1024 程序员节参赛作品",
    "homepage": "",
    "private": False,
    "has_issues": True,
    "has_wiki": False,
    "auto_init": False,
}

TOPICS = ["mcp", "mcdonalds", "1024", "programmers-day", "skill", "ai-agent", "python", "coupon", "points"]

ISSUE_TITLE = "【参赛申请】麦麦资产管家 mcd-asset-butler — 麦当劳积分&优惠券资产管理 Skill"
ISSUE_BODY = (
    "【参赛申请】\n"
    "项目名称：麦麦资产管家 · mcd-asset-butler\n"
    "项目地址：https://github.com/mark-zhaofei/mcd-asset-butler\n"
    "项目简介：基于麦当劳官方 MCP 的积分&优惠券资产管理 Skill：资产体检（折算金额/7天过期风险）、"
    "保值策略（积分处置 EV 对比：抽奖 vs 商城兑换 vs 直接抵扣；临期券最优用法）、"
    "一键执行（自动领券/抽奖/兑换引导）与单文件 HTML 可视化报告；纯 Python 标准库实现 MCP 客户端，零运行时依赖"
)


# 代理（沙箱出口）偶发 502/503/504，这些可重试；401/404/422 等不应重试
_RETRYABLE = {502, 503, 504, 429}


def api(method: str, path: str, token: str, payload: dict | None = None, _attempt: int = 0):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        if e.code in _RETRYABLE and _attempt < 6:
            import time as _t
            _t.sleep(2 ** _attempt + 1)
            return api(method, path, token, payload, _attempt + 1)
        detail = e.read().decode("utf-8", errors="replace")[:400]
        return e.code, detail
    except urllib.error.URLError as e:
        if _attempt < 6:
            import time as _t
            _t.sleep(2 ** _attempt + 1)
            return api(method, path, token, payload, _attempt + 1)
        return 0, f"URLError: {e}"


def list_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def upload_file(token: str, rel_path: str) -> tuple[int, str]:
    content = (ROOT / rel_path).read_bytes()
    b64 = base64.b64encode(content).decode("ascii")
    status, resp = api(
        "PUT",
        f"/repos/{OWNER}/{REPO}/contents/{urllib.parse.quote(rel_path)}",
        token,
        {
            "message": f"add {rel_path}",
            "content": b64,
        },
    )
    return status, resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 API")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("❌ 请先设置环境变量 GITHUB_TOKEN（GitHub PAT，需要 repo 权限）")
        return 1

    # 校验身份
    if not args.dry_run:
        status, me = api("GET", "/user", token)
        if status != 200:
            print(f"❌ Token 校验失败（HTTP {status}）：{me}")
            return 1
        login = me.get("login", "")
        if login != OWNER:
            print(f"⚠️ Token 所属账号是 {login}，将与计划Owner {OWNER} 不一致，仍继续……")
        else:
            print(f"✅ Token 校验通过：{login}")

    files = list_files()
    print(f"📦 待发布文件 {len(files)} 个（来自 git ls-files）")

    if args.dry_run:
        for f in files:
            print(f"  - {f}")
        print("\n计划动作：")
        print("  1. 创建公开仓库", f"{OWNER}/{REPO}")
        print("  2. 上传上述文件（Contents API）")
        print("  3. 添加 topics:", ", ".join(TOPICS))
        print("  4. 启用 GitHub Pages")
        print("  5. Star 自己的仓库")
        print("  6. 提交报名 Issue 到", ISSUE_REPO)
        return 0

    # 1. 创建仓库
    status, resp = api("POST", "/user/repos", token, REPO_META)
    if status == 201:
        print(f"✅ 仓库已创建：https://github.com/{OWNER}/{REPO}")
    elif status == 422 and "already exists" in str(resp):
        print(f"ℹ️ 仓库已存在，继续上传文件")
    else:
        print(f"❌ 创建仓库失败（HTTP {status}）：{resp}")
        return 1

    # 2. 上传文件
    ok, skip, fail = 0, 0, 0
    for f in files:
        status, detail = upload_file(token, f)
        if status in (200, 201):
            ok += 1
            print(f"  ✅ {f}")
        elif status == 422:
            skip += 1
            print(f"  ⏭️ {f}（已存在，跳过）")
        else:
            fail += 1
            print(f"  ❌ {f}（HTTP {status}）{detail}")
    print(f"📦 上传完成：成功 {ok}，跳过 {skip}，失败 {fail}")
    if fail:
        print("❌ 存在失败文件，终止后续步骤，请修复后重跑")
        return 1

    # 3. topics
    status, _ = api("PUT", f"/repos/{OWNER}/{REPO}/topics", token, {"names": TOPICS})
    print("✅ topics 已添加" if status == 200 else f"⚠️ topics 设置返回 HTTP {status}")

    # 4. GitHub Pages（把 examples/report.html 变成在线演示）
    status, resp = api(
        "POST",
        f"/repos/{OWNER}/{REPO}/pages",
        token,
        {"source": {"branch": "main", "path": "/"}},
    )
    if status == 201:
        print(f"✅ GitHub Pages 已启用：https://{OWNER}.github.io/{REPO}/examples/report.html")
    else:
        print(f"⚠️ Pages 启用返回 HTTP {status}（可稍后在仓库 Settings → Pages 手动开启）")

    # 5. self-star
    status, _ = api("PUT", f"/user/starred/{OWNER}/{REPO}", token)
    print("⭐ 已 Star 自己的仓库" if status == 204 else f"⚠️ Star 返回 HTTP {status}")

    # 6. 报名 Issue
    status, resp = api(
        "POST",
        f"/repos/{ISSUE_REPO}/issues",
        token,
        {"title": ISSUE_TITLE, "body": ISSUE_BODY},
    )
    if status == 201:
        print(f"✅ 报名 Issue 已提交：{resp.get('html_url', '')}")
        print("   官方机器人会在 Issue 下回复报名校验结果，请留意")
    else:
        print(f"❌ 报名 Issue 提交失败（HTTP {status}）：{resp}")
        return 1

    print("\n🎉 发布完成！后续建议：")
    print("  1. 等 1-2 分钟访问 Pages 链接确认在线报告")
    print("  2. 把仓库链接分享到开发者社区（腾讯云开发者社区/掘金/V2EX）攒 Star")
    print("  3. 关注报名 Issue 的官方校验回复")
    return 0


if __name__ == "__main__":
    sys.exit(main())
