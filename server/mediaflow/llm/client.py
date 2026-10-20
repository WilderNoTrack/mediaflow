"""LLM 客户端。

业务代码只依赖 `LLM` 协议，不直接碰 SDK：
- 生产用 DeepSeekLLM（OpenAI 兼容接口，SDK 自带超时与指数退避重试）
- 测试用脚本化的假 LLM（见 tests/fakes.py），整条流水线可以离线测
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from collections.abc import AsyncIterator
from typing import Any, Protocol

from mediaflow.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    def __init__(self) -> None:
        super().__init__("还没有填 DeepSeek API Key：回到首页，在「开始之前」里点「填 Key」")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    error: str = ""  # 模型给的参数不是合法 JSON 时记下原因，交给模型自己改


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


class LLM(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...


def parse_json(text: str) -> Any:
    """容忍模型偶尔包一层 ```json``` 或前后带解释文字。"""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise LLMError(f"模型没有返回合法 JSON：{text[:200]}")


async def complete_json(
    llm: LLM, messages: list[dict[str, Any]], *, temperature: float = 0.7
) -> dict[str, Any]:
    """要求 JSON 输出；解析失败时把错误告诉模型再给一次机会。"""
    resp = await llm.complete(messages, temperature=temperature, json_mode=True)
    try:
        data = parse_json(resp.content)
    except LLMError:
        retry = messages + [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": "上面的输出不是合法 JSON。请只输出一个 JSON 对象，不要任何其他文字。"},
        ]
        resp = await llm.complete(retry, temperature=0.2, json_mode=True)
        data = parse_json(resp.content)
    if not isinstance(data, dict):
        raise LLMError("模型返回的 JSON 不是对象")
    return data


class DeepSeekLLM:
    def __init__(self, settings: Settings | None = None, *, api_key: str | None = None) -> None:
        from openai import AsyncOpenAI

        s = settings or get_settings()
        key = api_key or llm_key()
        if not key:
            raise LLMNotConfigured()
        self.model = s.deepseek_model
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=s.deepseek_base_url,
            timeout=s.llm_timeout,
            max_retries=s.llm_max_retries,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        from openai import APIError

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools
        try:
            r = await self.client.chat.completions.create(**kwargs)
        except APIError as e:
            raise LLMError(f"DeepSeek 调用失败：{e}") from e
        msg = r.choices[0].message
        calls = [_tool_call(tc.id, tc.function.name, tc.function.arguments) for tc in msg.tool_calls or []]
        usage = r.usage.model_dump() if r.usage else {}
        return LLMResponse(content=msg.content or "", tool_calls=calls, usage=usage)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[tuple[str, Any]]:
        """边生成边吐：("reasoning", 思考片段) / ("delta", 回复片段) / ("calling", 工具名) / 最后 ("done", LLMResponse)。"""
        from openai import APIError

        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature,
                                  "stream": True, "stream_options": {"include_usage": True}}
        if tools:
            kwargs["tools"] = tools
        content: list[str] = []
        slots: dict[int, dict[str, str]] = {}
        usage: dict[str, int] = {}
        try:
            r = await self.client.chat.completions.create(**kwargs)
            async for chunk in r:
                if chunk.usage:
                    usage = chunk.usage.model_dump()
                if not chunk.choices:
                    continue
                d = chunk.choices[0].delta
                if rc := getattr(d, "reasoning_content", None):
                    yield ("reasoning", rc)
                if d.content:
                    content.append(d.content)
                    yield ("delta", d.content)
                for tc in d.tool_calls or []:
                    slot = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        if not slot["name"]:
                            yield ("calling", tc.function.name)
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments
        except APIError as e:
            raise LLMError(f"DeepSeek 调用失败：{e}") from e
        calls = [_tool_call(v["id"] or f"call_{i}", v["name"], v["args"]) for i, v in sorted(slots.items())]
        yield ("done", LLMResponse(content="".join(content), tool_calls=calls, usage=usage))


def _tool_call(call_id: str, name: str, raw: str | None) -> ToolCall:
    err = ""
    try:
        args = json.loads(raw or "{}")
        if not isinstance(args, dict):
            args, err = {}, "参数必须是 JSON 对象"
    except json.JSONDecodeError as e:
        args, err = {}, f"参数不是合法 JSON（{e.msg}），原文：{(raw or '')[:200]}"
    return ToolCall(id=call_id, name=name, arguments=args, error=err)


async def stream_complete(
    llm: LLM, messages: list[dict[str, Any]], *, temperature: float = 0.7, tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """有 stream() 的 LLM 就流式；没有的（测试里的假 LLM）一次拿完，再按同样的事件吐出来。"""
    fn = getattr(llm, "stream", None)
    if fn is not None:
        async for ev in fn(messages, temperature=temperature, tools=tools):
            yield ev
        return
    r = await llm.complete(messages, temperature=temperature, tools=tools)
    if r.content:
        yield ("delta", r.content)
    for c in r.tool_calls:
        yield ("calling", c.name)
    yield ("done", r)


_llm_override: LLM | None = None


def llm_key() -> str:
    """界面里填的 Key 优先，没填用环境变量 DEEPSEEK_API_KEY。"""
    from mediaflow import credentials

    return credentials.get("deepseek_api_key")


def llm_configured() -> bool:
    return _llm_override is not None or bool(llm_key())


def get_llm() -> LLM:
    if _llm_override is not None:
        return _llm_override
    return DeepSeekLLM()


def set_llm(llm: LLM | None) -> None:
    """测试用：注入假 LLM。"""
    global _llm_override
    _llm_override = llm
