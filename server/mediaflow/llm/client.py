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
from typing import Any, Protocol

from mediaflow.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    def __init__(self) -> None:
        super().__init__("还没有配置 DEEPSEEK_API_KEY，请在 server/.env 里填写后重启")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


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
    def __init__(self, settings: Settings | None = None) -> None:
        from openai import AsyncOpenAI

        s = settings or get_settings()
        if not s.deepseek_api_key:
            raise LLMNotConfigured()
        self.model = s.deepseek_model
        self.client = AsyncOpenAI(
            api_key=s.deepseek_api_key,
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
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = r.usage.model_dump() if r.usage else {}
        return LLMResponse(content=msg.content or "", tool_calls=calls, usage=usage)


_llm_override: LLM | None = None


def get_llm() -> LLM:
    if _llm_override is not None:
        return _llm_override
    return DeepSeekLLM()


def set_llm(llm: LLM | None) -> None:
    """测试用：注入假 LLM。"""
    global _llm_override
    _llm_override = llm
