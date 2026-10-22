"""麦当劳 MCP Server 客户端（MCP Streamable HTTP 协议，纯标准库实现）。

协议要点（参考 MCP 规范 Streamable HTTP 传输）：
- 所有消息为 JSON-RPC 2.0，通过 HTTP POST 发送到 https://mcp.mcd.cn
- 请求头：Content-Type: application/json
           Accept: application/json, text/event-stream
           Authorization: Bearer <MCP_TOKEN>
           Mcp-Session-Id: <initialize 响应返回的会话 ID>
- initialize 响应的 mcp-session-id 头需在后续请求中回带
- 服务端可能返回 application/json 单体响应，也可能返回 text/event-stream 流
- notifications/initialized 为通知（无 id），服务端返回 202 无响应体

本客户端对工具返回结构做「容错解析」：麦当劳各工具返回的 JSON 结构
可能随版本演进，解析器不假设固定层级，而是在嵌套结构中定位关键字段。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_MCP_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "mcd-asset-butler", "version": "1.0.0"}


class MCPError(Exception):
    """MCP 调用失败（网络、协议或业务错误）。"""


class MCPClient:
    """麦当劳 MCP Server 最小可用客户端。"""

    def __init__(
        self,
        token: Optional[str] = None,
        url: str = DEFAULT_MCP_URL,
        timeout: float = 30.0,
    ) -> None:
        self.url = url
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "")
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._req_id = 0
        self._initialized = False
        self.server_info: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # 传输层
    # ------------------------------------------------------------------ #
    def _post(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送单条 JSON-RPC 消息，返回解析后的响应对象（通知返回 None）。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": f"{CLIENT_INFO['name']}/{CLIENT_INFO['version']}",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                raw = resp.read().decode("utf-8", errors="replace")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise MCPError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise MCPError(f"网络错误: {e.reason}") from e

        if not raw.strip():
            return None  # 202 Accepted（通知）
        if "text/event-stream" in ctype:
            return self._parse_sse(raw)
        return json.loads(raw)

    @staticmethod
    def _parse_sse(raw: str) -> Optional[Dict[str, Any]]:
        """从 SSE 流中取出最后一条 message 事件的 JSON 数据。"""
        data_lines: List[str] = []
        last: Optional[Dict[str, Any]] = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line.strip() == "" and data_lines:
                chunk = "\n".join(data_lines)
                data_lines = []
                try:
                    last = json.loads(chunk)
                except json.JSONDecodeError:
                    pass
        if data_lines:  # 流未以空行结尾
            try:
                last = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                pass
        return last

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """发送请求（带 id）并校验 JSON-RPC 响应。"""
        self._req_id += 1
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        resp = self._post(payload)
        if resp is None:
            return None
        if "error" in resp:
            err = resp["error"]
            raise MCPError(f"{method} 失败: {err.get('code')} {err.get('message')}")
        return resp.get("result")

    def _notify(self, method: str) -> None:
        """发送通知（无 id，无响应体）。"""
        self._post({"jsonrpc": "2.0", "method": method})

    # ------------------------------------------------------------------ #
    # MCP 生命周期
    # ------------------------------------------------------------------ #
    def initialize(self) -> Dict[str, Any]:
        if not self.token:
            raise MCPError(
                "未配置 MCP Token。请到 https://open.mcd.cn/mcp 手机号登录后申请，"
                "并通过 --token 参数或环境变量 MCD_MCP_TOKEN 提供。"
            )
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._initialized = True
        self.server_info = result or {}
        try:
            self._notify("notifications/initialized")
        except MCPError:
            pass  # 部分实现不返回 202，忽略
        return self.server_info

    def list_tools(self) -> List[Dict[str, Any]]:
        if not self._initialized:
            self.initialize()
        result = self._rpc("tools/list") or {}
        return result.get("tools", [])

    # ------------------------------------------------------------------ #
    # 工具调用
    # ------------------------------------------------------------------ #
    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """调用工具并把 result.content 中的 text 段尽量解析为 JSON 返回。"""
        if not self._initialized:
            self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result is None:
            return None
        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
            raise MCPError(f"工具 {name} 返回错误: {' '.join(texts)[:300]}")
        return extract_payload(result.get("content", []))

    # ------------------------------------------------------------------ #
    # 本 Skill 用到的高层封装（容错：字段缺失时返回 None 交由上层降级）
    # ------------------------------------------------------------------ #
    def query_points_account(self) -> Optional[Dict[str, Any]]:
        """我的积分：可用/累计/冻结/即将过期。"""
        return self.call_tool("query-my-account", {})

    def query_my_coupons(self) -> Optional[Dict[str, Any]]:
        """我的优惠券列表。"""
        return self.call_tool("query-my-coupons", {})

    def query_my_prizes(self) -> Optional[Dict[str, Any]]:
        """抽奖中奖记录。"""
        return self.call_tool("query-my-prizes", {"pageNum": 1, "pageSize": 50})

    def query_lottery_info(self) -> Optional[Dict[str, Any]]:
        """积分抽奖活动信息（奖品列表/消耗规则）。"""
        return self.call_tool("query-lottery-info", {})

    def query_mall_products(self) -> Optional[Dict[str, Any]]:
        """积分商城可兑换商品。"""
        return self.call_tool("mall-points-products", {"pageNum": 1, "pageSize": 100})

    def query_available_coupons(self) -> Optional[Dict[str, Any]]:
        """麦麦省可领取优惠券。"""
        return self.call_tool("available-coupons", {})

    def auto_bind_coupons(self) -> Optional[Dict[str, Any]]:
        """麦麦省一键领券。"""
        return self.call_tool("auto-bind-coupons", {})

    def query_campaign_calendar(self) -> Optional[Dict[str, Any]]:
        """当月营销活动日历。"""
        return self.call_tool("campaign-calendar", {})

    def query_now_time(self) -> Optional[Dict[str, Any]]:
        """MCP 服务端当前时间。"""
        return self.call_tool("now-time-info", {})


def extract_payload(content: List[Dict[str, Any]]) -> Any:
    """把 MCP content 数组还原为业务数据。

    约定：text 段优先；若 text 是合法 JSON 则解析，否则原样返回字符串。
    多段 text 用换行拼接。
    """
    texts: List[str] = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text", ""))
        elif isinstance(item, str):
            texts.append(item)
    joined = "\n".join(t for t in texts if t)
    if not joined:
        return None
    try:
        return json.loads(joined)
    except (json.JSONDecodeError, ValueError):
        return joined
