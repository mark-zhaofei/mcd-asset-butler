# workbuddy.md — WorkBuddy 开发上下文

> 本文件记录 `mcd-asset-butler`（麦麦资产管家）在 **腾讯 WorkBuddy** 中的完整开发过程，
> 用于核验本项目真实使用腾讯 WorkBuddy 智能体开发（WorkBuddy 专项奖励）。
> 全部内容为真实开发记录，未做夸张处理。

## 1. 项目信息

| 项 | 内容 |
|---|---|
| 项目名称 | 麦麦资产管家 · mcd-asset-butler |
| 参赛活动 | 1024 程序员节 · 麦当劳程序员创意开发大赛 |
| 开发环境 | WorkBuddy（Windows，Git Bash） |
| 开发日期 | 2026-10-22 |
| 开发方式 | 全程由 WorkBuddy 智能体协助完成：需求解读 → 选题分析 → 编码 → 测试 → 演示素材 → 参赛文件 |

## 2. 开发起点（用户原始指令）

用户赵飞向 WorkBuddy 发出参赛请求，并附上活动页面链接：

> 「你帮我也弄一个作品参赛吧 https://www.workbuddy.link/p/8QYARuAmZ9RgQty3FSzNUs?source=2」

WorkBuddy 随后完成了活动解读（WorkBuddy × 麦当劳「1024 造物挑战」程序员节应用创作大赛）：
基于麦当劳 MCP 开发 Skill、GitHub 开源、按 Star 排名、需包含 5 个标准文件、10-25 23:59 截止。

## 3. 开发轮次记录

### 第 1 轮：活动规则与能力摸底

- **WorkBuddy 动作**：抓取活动规则原文（activityGuidelines.md）、官方 README、
  麦当劳 MCP Server 工具清单（35 个 Tool）、当前排行榜 RANKING.md（当日 13:00 快照）。
- **关键结论**：
  - 硬性要求：仓库须含 `README.md` / `CONTEST_DECLARATION.md`（官方原文不可改）/
    `MCP_INTEGRATION.md` / `mcp-config.example.json` / `workbuddy.md`；
    报名截止 2026-10-25 23:59；按 GitHub Star 排名；报名 Issue 须按标准格式、
    标题与正文间不加换行。
  - 竞争格局：省钱/优惠券赛道前三名 893★/810★/808★ 已红海；
    营养、派对、抽奖、MBTI 均有多个项目；**「积分资产」维度接近空白**
    （mc-points-steward 仅 36★），且无项目把「券 + 积分 + 奖品」作为统一资产账本。

### 第 2 轮：选题决策

- **用户确认**：「可以，就做积分资产管理」方向（在 WorkBuddy 给出三个候选方向
  「积分资产管家 / 生日派对管家 / 企业团餐」并分析红海规避后采纳）。
- **产品定义**：
  - 体检：券/积分/奖品统一折算（100 积分 = ¥1）、7 天过期风险
  - 策略：积分处置 EV 对比（抽奖 vs 商城兑换 vs 直接抵扣）、临期券最优用法
  - 执行：一键领麦麦省券、抽奖、兑换引导
  - 呈现：终端表格 + 单文件 HTML 可视化报告

### 第 3 轮：核心开发（WorkBuddy 主导编码）

WorkBuddy 在本地工作区创建项目并完成全部源码（纯 Python 标准库、零运行时依赖）：

| 模块 | 内容 |
|---|---|
| `mcp_client.py` | 手写 MCP Streamable HTTP 客户端：initialize / notifications /
tools/list / tools/call、`Mcp-Session-Id` 会话管理、JSON 与 SSE 双响应解析 |
| `models.py` | 资产模型 + 容错解析器：不假设固定字段层级，在嵌套 JSON 中定位关键字段 |
| `engine.py` | 分析引擎：资产折算、过期风险、积分处置 EV、兑换性价比排序、
临期券「券后实付最低」搜索 + 适用餐品匹配 + 用券门槛约束 |
| `report.py` | 单文件 HTML 报告生成器（内联 CSS/SVG、零外部资源） |
| `demo_data.py` | 离线演示数据（与官方 Tool 说明结构对齐） |
| `service.py` | 采集编排：单工具失败自动降级，部分失败仍可出报告 |
| `cli.py` | 8 个子命令：checkup / strategy / claim / exchange / lottery / report /
dashboard / tools |

**开发中实测发现并修复的问题**（均由 WorkBuddy 通过 demo 运行自测发现）：
1. 金额单位误判（整数被当成「元」）→ 统一为国内支付 API 惯例「整数=分」；
2. 抽奖活动 `costPoints` 在嵌套节点中导致 EV 计算缺失 → 改为嵌套查找；
3. 临期券搭配语义错误（冰淇淋券搭配菠萝派）→ 新增「券面适用餐品匹配」；
4. 终端表格中文错位（`len()` 不计全角宽度）→ 改用东亚字符显示宽度对齐。

### 第 4 轮：测试与演示素材

- **单测**：编写并运行 16 个单元测试（`unittest`），全部通过；
  含两个由 WorkBuddy 自测发现的失败用例（百分号概率解析、时间戳断言）并修复。
- **演示 GIF**：WorkBuddy 编写 `tools/gen_demo_gif.py`（Pillow 双字体混排：
  Consolas + 微软雅黑，打字机效果 + 块光标），生成 139 帧 / 86KB 终端演示动画。
- **报告截图**：使用本机 Chrome headless 对 HTML 报告截图（`--headless=new --screenshot`）。
- **HTML 报告样例**：demo 模式生成 `examples/report.html` 并入库。

### 第 5 轮：参赛文件与发布准备

- 按官方要求撰写 `README.md`（含演示 GIF、报告截图、算法说明、快速开始）、
  `MCP_INTEGRATION.md`（12 个 Tool 清单 + mermaid 调用流程图 + 业务价值）、
  `mcp-config.example.json`（仅 `${MCD_MCP_TOKEN}` 环境变量占位符）；
  `CONTEST_DECLARATION.md` 使用官方模板原文、一字未改。
- 规划发布：创建公开仓库 → 推送 → star → 在 `M-China-Official/mcd-developer-innovation-challenge`
  按标准 Issue 格式提交报名。

## 4. 本项目使用到的 WorkBuddy 能力

| 能力 | 用途 |
|---|---|
| 网页检索 / 网页抓取 | 活动规则、MCP 工具清单、排行榜竞争格局分析 |
| 本地文件读写与目录管理 | 项目骨架与全部源码 |
| 命令行执行 | 运行 demo、单元测试、GIF 生成、Chrome 截图 |
| 任务管理 | 5 项任务清单跟踪（骨架 → 引擎 → 演示素材 → 参赛文件 → 发布） |
| 联网环境诊断 | 排查 git 代理与 GitHub 连通性问题 |

## 5. 真实性说明

- 本文档所述开发过程、轮次、发现的问题均为 2026-10-22 当天在 WorkBuddy 中的真实记录；
- 项目中真实调用了麦当劳 MCP Server（联调需用户自行申请的 Token，
  开发期以 `--demo` 离线模式保证全流程可复现）；
- 未使用任何方式夸大或伪造开发过程。
