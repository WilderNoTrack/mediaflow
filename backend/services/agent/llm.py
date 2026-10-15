"""
Agent 的 LLM 调用层

统一 core.py / manager.py / tools.py 的 DeepSeek 调用，提供：
- 可重试错误（429 / 5xx / 超时 / 连接失败）的指数退避重试
- 不可重试错误（4xx，如鉴权失败、参数错）快速失败，不浪费时间
- token 用量累计，供运行追踪统计成本

此前每处都是裸 requests.post 且零重试：16 步的 Agent 流程里
任何一步撞上一次限流或抖动就整轮作废，自动运营场景尤其致命。
"""

import os
import time
import logging
import threading

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_ENDPOINT = os.getenv("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL    = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

MAX_RETRIES     = int(os.getenv("LLM_MAX_RETRIES", "3"))
BACKOFF_BASE    = float(os.getenv("LLM_BACKOFF_BASE", "1.5"))  # 秒
REQUEST_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

# 这些状态码重试有意义；其余 4xx 属于请求本身有问题，重试只是浪费
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """LLM 调用最终失败（已耗尽重试或遇到不可重试错误）。"""


class TokenCounter:
    """线程安全的 token 累计器，一次 Agent run 一个实例。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def add(self, usage: dict) -> None:
        if not usage:
            return
        with self._lock:
            self.prompt_tokens     += usage.get("prompt_tokens", 0) or 0
            self.completion_tokens += usage.get("completion_tokens", 0) or 0
            self.calls             += 1

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_dict(self) -> dict:
        return {
            "calls":             self.calls,
            "prompt_tokens":     self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens":      self.total,
        }


def chat_completion(
    messages: list,
    tools: list = None,
    temperature: float = 0.7,
    json_mode: bool = False,
    counter: "TokenCounter" = None,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:
    """
    调用 DeepSeek chat/completions，返回 message dict。
    失败时抛 LLMError（已带重试）。
    """
    if not DEEPSEEK_API_KEY:
        raise LLMError("DEEPSEEK_API_KEY 未配置")

    payload: dict = {
        "model":       DEEPSEEK_MODEL,
        "messages":    messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                f"{DEEPSEEK_ENDPOINT}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            if resp.status_code in RETRYABLE_STATUS:
                last_err = f"HTTP {resp.status_code}"
                raise _Retryable(last_err)
            resp.raise_for_status()

            data = resp.json()
            if counter is not None:
                counter.add(data.get("usage") or {})
            return data["choices"][0]["message"]

        except _Retryable as e:
            last_err = str(e)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = f"{type(e).__name__}: {e}"
        except requests.HTTPError as e:
            # 不可重试的 4xx：立刻失败
            raise LLMError(f"LLM 调用失败（不可重试）: {e}") from e
        except (KeyError, ValueError) as e:
            raise LLMError(f"LLM 返回体解析失败: {e}") from e

        if attempt < MAX_RETRIES - 1:
            delay = BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                f"[LLM] 第 {attempt + 1}/{MAX_RETRIES} 次失败({last_err})，{delay:.1f}s 后重试"
            )
            time.sleep(delay)

    raise LLMError(f"LLM 调用失败，已重试 {MAX_RETRIES} 次: {last_err}")


def chat_text(
    messages: list, temperature: float = 0.7,
    json_mode: bool = False, counter: "TokenCounter" = None,
) -> str:
    """只要文本内容的便捷封装。"""
    msg = chat_completion(
        messages, temperature=temperature, json_mode=json_mode, counter=counter
    )
    return msg.get("content") or ""


class _Retryable(Exception):
    """内部信号：本次失败可重试。"""
