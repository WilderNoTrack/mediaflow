"""LLM 客户端。

业务代码只依赖 `LLM` 协议，不直接碰 SDK：
- 生产用 DeepSeekLLM（OpenAI 兼容接口，SDK 自带超时与指数退避重试）；配了 openai-next 就用 ChainLLM：
  先走 openai-next 调 DeepSeek，出错自动换 DeepSeek 官方
- 测试用脚本化的假 LLM（见 tests/fakes.py），整条流水线可以离线测
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from mediaflow.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    def __init__(self) -> None:
        super().__init__("还没有填模型 Key（openai-next 或 DeepSeek）：回到首页，在「开始之前」里点「填 Key」")


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


NEXT_HEADERS = {"User-Agent": "curl/8.5.0"}  # openai-next 的防火墙会拦 OpenAI SDK 默认的 UA


class DeepSeekLLM:
    """OpenAI 兼容接口的 DeepSeek：默认直连官方；给了 base_url/headers 就走中转（openai-next）。"""

    def __init__(self, settings: Settings | None = None, *, api_key: str | None = None, model: str | None = None,
                 extra: dict[str, Any] | None = None, base_url: str | None = None, headers: dict[str, str] | None = None,
                 label: str = "DeepSeek", max_retries: int | None = None) -> None:
        from openai import AsyncOpenAI

        s = settings or get_settings()
        key = api_key or llm_key()
        if not key:
            raise LLMNotConfigured()
        self.model = model or s.deepseek_model
        self.extra = extra or {}
        self.label = label
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=base_url or s.deepseek_base_url,
            timeout=s.llm_timeout,
            max_retries=s.llm_max_retries if max_retries is None else max_retries,
            default_headers=headers,
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
        if self.extra:
            kwargs["extra_body"] = self.extra
        try:
            r = await self.client.chat.completions.create(**kwargs)
        except APIError as e:
            raise LLMError(f"{self.label} 调用失败：{e}") from e
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
        if self.extra:
            kwargs["extra_body"] = self.extra
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
            raise LLMError(f"{self.label} 调用失败：{e}") from e
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
    """DeepSeek 官方的 Key：界面里填的优先，没填用环境变量 DEEPSEEK_API_KEY。"""
    from mediaflow import credentials

    return credentials.get("deepseek_api_key")


def next_llm_key() -> str:
    """openai-next 的 Key（和配图共用一个）。"""
    from mediaflow import credentials

    return credentials.get("image_next_api_key")


def next_llm_model() -> str:
    from mediaflow import credentials

    return credentials.get("llm_next_model") or get_settings().llm_next_model


def llm_channel_pref() -> str:
    from mediaflow import credentials

    v = credentials.get("llm_channel")
    return v if v in ("next", "deepseek") else "auto"


NEXT_PAUSE_SECONDS = 15 * 60       # openai-next 出错后这么久内先走官方
NEXT_QUOTA_PAUSE_SECONDS = 6 * 3600  # 额度用完的话停久一点
_next_paused_until = 0.0
_QUOTA = ("quota", "额度", "余额", "insufficient", "balance", "credit", "用尽", "欠费", "充值", "recharge", "402")


def next_paused() -> bool:
    return time.time() < _next_paused_until


def _pause_next(err: Exception) -> None:
    global _next_paused_until
    msg = str(err).lower()
    _next_paused_until = time.time() + (NEXT_QUOTA_PAUSE_SECONDS if any(w in msg for w in _QUOTA) else NEXT_PAUSE_SECONDS)


def reset_next_pause() -> None:
    global _next_paused_until
    _next_paused_until = 0.0


def llm_channels() -> list[str]:
    """文字模型按顺序走哪几条：默认 openai-next 优先（配了的话），DeepSeek 官方备用。"""
    pref = llm_channel_pref()
    have = {"next": bool(next_llm_key()), "deepseek": bool(llm_key())}
    order = ["next", "deepseek"] if pref != "deepseek" else ["deepseek", "next"]
    if pref in ("next", "deepseek") and have[pref]:
        order = [pref]  # 指定了只用一条
    return [c for c in order if have[c]]


def make_channel(channel: str, *, model: str | None = None, api_key: str | None = None,
                 extra: dict[str, Any] | None = None) -> DeepSeekLLM:
    s = get_settings()
    if channel == "next":
        return DeepSeekLLM(api_key=api_key or next_llm_key(), model=model or next_llm_model(), extra=extra,
                           base_url=s.llm_next_base_url, headers=NEXT_HEADERS, label="openai-next", max_retries=1)
    return DeepSeekLLM(api_key=api_key or llm_key(), model=model, extra=extra)


class ChainLLM:
    """按顺序试几条通道：openai-next 出错（额度、鉴权、超时、5xx…）自动换 DeepSeek 官方，并在一段时间内先走官方。
    流式只在还没吐出回复/工具调用时换（不然用户会看到重复的字）。"""

    def __init__(self, makers: list[tuple[str, Callable[[], DeepSeekLLM]]]) -> None:
        self.makers = makers
        self._built: dict[str, DeepSeekLLM] = {}

    def _order(self) -> list[tuple[str, Callable[[], DeepSeekLLM]]]:
        if len(self.makers) > 1 and next_paused():
            return [m for m in self.makers if m[0] != "next"] + [m for m in self.makers if m[0] == "next"]
        return self.makers

    def _get(self, name: str, make: Callable[[], DeepSeekLLM]) -> DeepSeekLLM:
        if name not in self._built:
            self._built[name] = make()
        return self._built[name]

    @property
    def model(self) -> str:
        name, make = self._order()[0]
        return self._get(name, make).model

    async def complete(self, messages: list[dict[str, Any]], **kw: Any) -> LLMResponse:
        last: LLMError | None = None
        for i, (name, make) in enumerate(self._order()):
            try:
                return await self._get(name, make).complete(messages, **kw)
            except LLMError as e:
                last = e
                if name == "next":
                    _pause_next(e)
                if i + 1 < len(self.makers):
                    logger.warning("%s 调用失败，换下一条：%s", name, e)
        raise last or LLMNotConfigured()

    async def stream(self, messages: list[dict[str, Any]], **kw: Any) -> AsyncIterator[tuple[str, Any]]:
        order = self._order()
        for i, (name, make) in enumerate(order):
            started = False
            try:
                async for ev in self._get(name, make).stream(messages, **kw):
                    if ev[0] in ("delta", "calling"):
                        started = True
                    yield ev
                return
            except LLMError as e:
                if name == "next":
                    _pause_next(e)
                if started or i + 1 >= len(order):
                    raise
                logger.warning("%s 调用失败，换下一条：%s", name, e)


def llm_configured() -> bool:
    return _llm_override is not None or bool(llm_key()) or bool(next_llm_key())


def get_llm() -> LLM:
    if _llm_override is not None:
        return _llm_override
    chans = llm_channels()
    if not chans:
        raise LLMNotConfigured()
    if chans == ["deepseek"]:
        return DeepSeekLLM()
    return ChainLLM([(c, (lambda c=c: make_channel(c))) for c in chans])


def set_llm(llm: LLM | None) -> None:
    """测试用：注入假 LLM。"""
    global _llm_override
    _llm_override = llm


# ── 看图模型（多模态）：学配图模板、出图自检 ───────────────────────────────

_vision_override: LLM | None = None


def vision_model() -> str:
    return (get_settings().deepseek_vision_model or "").strip()


def vision_available() -> bool:
    """能不能看图：测试里注入了就能；否则要有 openai-next 的 Key（同一个 DeepSeek 模型就能看图），
    或者 DeepSeek Key + 配了看图模型（注入了假文本 LLM 的测试环境不算）。"""
    if _vision_override is not None:
        return True
    return _llm_override is None and bool(_vision_makers())


def _vision_makers(effort: str | None = None) -> list[tuple[str, Callable[[], DeepSeekLLM]]]:
    extra = {"reasoning_effort": effort} if effort else None
    out: list[tuple[str, Callable[[], DeepSeekLLM]]] = []
    for c in llm_channels():
        if c == "next":
            out.append(("next", lambda: make_channel("next", extra=extra)))
        elif vision_model():
            out.append(("deepseek", lambda: make_channel("deepseek", model=vision_model(), extra=extra)))
    return out


def get_vision_llm(effort: str | None = None) -> LLM | None:
    """看图用的 LLM；用不了返回 None（调用方跳过看图那一步）。effort=low 时少想一会儿，自检这种简单活用。"""
    if _vision_override is not None:
        return _vision_override
    if not vision_available():
        return None
    makers = _vision_makers(effort)
    return makers[0][1]() if len(makers) == 1 else ChainLLM(makers)


def set_vision_llm(llm: LLM | None) -> None:
    """测试用：注入假的看图 LLM。"""
    global _vision_override
    _vision_override = llm


def image_part(uri: str) -> dict[str, Any]:
    """OpenAI 格式的图片消息片段（data URI）。"""
    return {"type": "image_url", "image_url": {"url": uri}}
