"""
图片生成服务 — 调用 gpt-image-2 API（国内节点）
POST /v1/api/generate → 获取任务 ID → 轮询直到完成 → 下载保存
"""
import os
import uuid
import time
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 国内节点
DEFAULT_ENDPOINT = "https://grsai.dakka.com.cn/v1/api/generate"


class ImageService:
    def __init__(self, api_key: str = ""):
        self.api_key  = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model    = os.getenv("IMAGE_MODEL", "gpt-image-2")
        self.endpoint = os.getenv("IMAGE_ENDPOINT", DEFAULT_ENDPOINT)
        self.size     = os.getenv("IMAGE_SIZE", "1024x1024")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def _all_keys(cls) -> list:
        keys = []
        primary = os.getenv("OPENAI_API_KEY", "")
        if primary:
            keys.append(primary)
        i = 2
        while True:
            k = os.getenv(f"OPENAI_API_KEY_{i}", "")
            if not k:
                break
            if k not in keys:
                keys.append(k)
            i += 1
        return keys

    @classmethod
    def for_index(cls, idx: int) -> "ImageService":
        keys = cls._all_keys()
        if not keys:
            return cls()
        return cls(api_key=keys[idx % len(keys)])

    def generate(self, prompt: str) -> str | None:
        """
        生成单张图片，返回本地 URL（如 /uploads/xxx.png）。
        失败返回 None。
        """
        if not self.available:
            logger.warning("[ImageService] OPENAI_API_KEY 未配置，跳过生图")
            return None

        logger.info(f"[ImageService] 生成图片: {prompt[:60]}...")

        try:
            resp = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "aspectRatio": self.size,   # 直接传像素值，如 "1024x1024"
                    "replyType": "json",
                },
                timeout=90,   # API 实测需 40s+，留足余量
            )

            if not resp.ok:
                logger.error(f"[ImageService] HTTP {resp.status_code}: {resp.text[:300]}")
                return None

            data = resp.json()
            task_id = data.get("id")

            if not task_id:
                logger.error(f"[ImageService] 无任务 ID，响应：{data}")
                return None

            # 如果立即完成
            if data.get("status") == "succeeded":
                return self._extract_and_save(data)

            # 异步轮询（最多等 120 秒）
            return self._poll(task_id)

        except Exception as e:
            logger.error(f"[ImageService] 生图异常: {e}")
            return None

    def _poll(self, task_id: str, timeout: int = 120, interval: int = 3) -> str | None:
        """轮询任务直到完成或超时。"""
        query_url = self.endpoint.replace("/generate", "/query")
        deadline = time.time() + timeout

        while time.time() < deadline:
            time.sleep(interval)
            try:
                resp = requests.post(
                    query_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"id": task_id},
                    timeout=15,
                )
                if not resp.ok:
                    continue
                data = resp.json()
                status = data.get("status")
                logger.info(f"[ImageService] 任务 {task_id[:8]} 状态: {status} ({data.get('progress', 0)}%)")

                if status == "succeeded":
                    return self._extract_and_save(data)
                if status in ("failed", "violation"):
                    logger.error(f"[ImageService] 任务失败: {data.get('error')}")
                    return None
            except Exception as e:
                logger.warning(f"[ImageService] 轮询出错: {e}")

        logger.error(f"[ImageService] 任务 {task_id[:8]} 超时（{timeout}s）")
        return None

    def _extract_and_save(self, data: dict) -> str | None:
        """从响应中提取图片 URL 并下载保存。"""
        results = data.get("results", [])
        if not results:
            logger.error(f"[ImageService] 无图片结果: {data}")
            return None

        r0 = results[0]
        # results[0] 可能是字符串 URL 或 {"url": "..."} 对象
        img_url = r0 if isinstance(r0, str) else (r0.get("url") or r0.get("imageUrl") or "")
        if not img_url:
            logger.error(f"[ImageService] 无法从 results[0] 取 URL: {r0}")
            return None

        return self._download_and_save(img_url)

    def _download_and_save(self, url: str) -> str | None:
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            filename = f"{uuid.uuid4()}.png"
            (UPLOAD_DIR / filename).write_bytes(r.content)
            logger.info(f"[ImageService] 已保存: /uploads/{filename}")
            return f"/uploads/{filename}"
        except Exception as e:
            logger.error(f"[ImageService] 下载失败: {e}")
            return None

    def generate_batch(self, prompts: list[str]) -> list[str]:
        results = []
        for prompt in prompts[:9]:
            url = self.generate(prompt)
            results.append(url or "")
        return results
