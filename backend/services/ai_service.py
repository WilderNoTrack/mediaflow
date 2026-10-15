import os
import requests
from typing import Optional, Dict, Any
import re

class AIService:
    """AI Service for generating content using DeepSeek API."""
    
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.endpoint = os.getenv("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/v1")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    def generate_content(self, topic: str, user_preferences: Optional[Dict] = None, prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate content using AI.
        
        Args:
            topic: The topic/subject for content generation
            user_preferences: User's content preferences (style, domain, etc.)
            prompt: Custom prompt template (optional)
        
        Returns:
            dict with keys: title, content, tags
        """
        # If no API key, raise error
        if not self.api_key:
            raise Exception("DeepSeek API Key 未配置，请检查 .env 文件中的 DEEPSEEK_API_KEY")
        
        # Build prompt
        requirements = user_preferences.get("requirements", []) if user_preferences else []
        requirements_str = ""
        if requirements:
            requirements_str = "\n额外要求：\n" + "\n".join(f"- {r}" for r in requirements)

        ai_prompt = prompt if prompt else f"""请根据以下主题生成小红书风格的种草文案：

主题：{topic}{requirements_str}

要求：
1. 标题简洁有力，不超过 20 字
2. 正文 300-800 字，分段落，有 emoji
3. 生成 5 个相关标签，带#
4. 内容要真实、有情感、接地气

请直接返回以下格式（不要其他内容）：
标题：xxx
正文：xxx
标签：xxx,xxx,xxx,xxx,xxx"""
        
        try:
            url = f"{self.endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": ai_prompt}
                ],
                "temperature": 0.8
            }
            
            print(f"[AI] 发送请求到 DeepSeek API...")
            print(f"[AI] Prompt: {ai_prompt[:200]}...")
            response = requests.post(url, headers=headers, json=data, timeout=60)
            print(f"[AI] 收到响应：{response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._parse_ai_response(content, topic)
            else:
                print(f"[AI] API 返回错误：{response.text}")
                raise Exception(f"DeepSeek API 调用失败：{response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"[AI] 生成失败：{e}")
            raise
    

    
    def generate_from_topic(
        self,
        theme: str,
        target_audience: str,
        content_style: str,
        requirements: list,
        topic_title: str,
        topic_angle: str = "",
        image_style: str = "",
    ) -> Dict[str, Any]:
        """
        根据账号定位 + 选题，生成完整图文（标题/正文/标签/图片描述）。
        供工作台手动生成和 Agent 自动运营共用。
        """
        if not self.api_key:
            raise Exception("DeepSeek API Key 未配置")

        requirements = requirements or []
        req_str = ""
        if requirements:
            req_str = "\n\n【账号硬性要求（必须遵守）】\n" + "\n".join(f"- {r}" for r in requirements)

        prompt = f"""你是专业的小红书内容创作者。

账号定位：{theme or '未设定'}
目标受众：{target_audience or '未设定'}
内容风格：{content_style or '轻松真实，接地气'}{req_str}

选题：{topic_title}
切入角度：{topic_angle or '自由发挥'}

根据以上信息，创作一篇完整的小红书图文帖子。

要求：
1. 标题：吸引人，不超过 20 字，贴合选题角度
2. 正文：300-600 字，分段，自然加入 emoji，写得像真人分享，不要广告感
3. 标签：5 个相关话题标签（不带 # 号）
4. 配图方案（image_prompts）：规划每张图的内容，描述要具体真实，能直接用于生成照片
   - 账号配图风格：{image_style or content_style or "未设定，根据账号主题和内容选择自然合适的呈现方式"}
   - ⚠️ 最高优先级：如果上面的「账号配图风格」中描述了图片的结构、数量、顺序或"要/不要哪类图"
     （例如"只拍最终效果不要过程图"、"全部生活随手拍"、"固定3张"），必须严格按账号要求执行，
     下面的默认规则全部让位，不得自行补充账号明确不要的图。
   - 仅当账号没有指定结构时，按以下默认规则：
     · 图片数量和正文内容一一对应：正文写了几个步骤/环节/要点，就配几张图，不能少配。
     · 分步教程类正文（出现 1️⃣2️⃣3️⃣ 或"第一步"等）：封面1张 + 每个步骤各1张 + 最终成果1张。
     · 教程/干货类不少于 4 张；纯展示/种草类至少 3 张；上限 9 张。
   - 每张描述要包含：拍什么 + 状态/细节/质感 + 大概角度，画面内容贴合本账号的主题和配图风格

返回严格的 JSON 格式（image_prompts 的数量按上面规则确定，下面只是格式示意，不代表只配3张）：
{{
  "title": "标题",
  "content": "正文",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "image_prompts": ["第1张图描述", "第2张图描述", "第3张图描述", "..."]
}}"""

        try:
            url = f"{self.endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.85,
                "response_format": {"type": "json_object"}
            }
            response = requests.post(url, headers=headers, json=data, timeout=90)
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._extract_json(content)
            raise Exception(f"API 调用失败：{response.status_code} - {response.text}")
        except Exception as e:
            print(f"[AI 选题生成] 失败：{e}")
            raise

    def generate_from_conversation(
        self,
        messages: list,
        requirements: list = None
    ) -> Dict[str, Any]:
        """
        根据对话上下文生成完整图文内容（标题 + 正文 + 标签 + 图片描述）。
        """
        if not self.api_key:
            raise Exception("DeepSeek API Key 未配置")

        requirements = requirements or []

        # 构建对话摘要
        chat_lines = []
        for m in messages[-15:]:
            role_label = "用户" if m["role"] == "user" else "小媒"
            chat_lines.append(f"{role_label}: {m['message']}")
        chat_context = "\n".join(chat_lines)

        req_str = ""
        if requirements:
            req_str = "\n\n【用户文案要求（必须遵守）】\n" + "\n".join(f"- {r}" for r in requirements)

        prompt = f"""你是专业的小红书内容创作者。根据以下对话内容，生成一篇完整的小红书图文帖子。

【对话记录】
{chat_context}{req_str}

【创作要求】
1. 从对话中提取核心主题和角度
2. 标题：吸引眼球，不超过 20 字，可用数字/疑问句/emoji
3. 正文：300-600 字，分段落，自然插入 emoji，像真人真实分享，接地气
4. 标签：5 个相关话题标签（不带 # 号）
5. 图片描述：为这篇帖子配 3 张图，描述每张图的内容（10-20 字，中文）

严格按照以下 JSON 格式返回，不要有其他任何内容：
{{
  "title": "标题",
  "content": "正文内容",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "image_prompts": ["第1张图描述", "第2张图描述", "第3张图描述"]
}}"""

        try:
            url = f"{self.endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.85,
                "response_format": {"type": "json_object"}
            }

            print(f"[Agent] 开始生成图文内容...")
            response = requests.post(url, headers=headers, json=data, timeout=90)
            print(f"[Agent] 收到响应：{response.status_code}")

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._extract_json(content)
            else:
                raise Exception(f"API 调用失败：{response.status_code} - {response.text}")
        except Exception as e:
            print(f"[Agent] 生成失败：{e}")
            raise

    def suggest_keywords(self, profile_desc: str) -> list:
        """根据账号定位生成搜索关键词建议。"""
        if not self.api_key:
            return []
        import requests as _req, json as _json
        prompt = (
            f"基于以下账号信息，生成 8 个具体的选题词：\n\n"
            f"{profile_desc}\n\n"
            "规则：\n"
            "- 如果有「选题类型」，就从该类型下生成具体实例（如类型='通勤穿搭场景'→生成具体场景、类型='家常菜品'→生成具体菜名、类型='考研知识点'→生成具体知识点）\n"
            "- 和已有选题词保持相同的粒度和风格，不重复\n"
            "- 这些词是 Agent 拿去平台搜索热点内容用的，要真实存在且有搜索量\n"
            '直接返回 JSON：{"keywords": ["词1","词2",...]}'
        )
        try:
            resp = _req.post(
                f"{self.endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.7, "response_format": {"type": "json_object"}},
                timeout=30,
            )
            if resp.status_code == 200:
                data = _json.loads(resp.json()["choices"][0]["message"]["content"])
                return data.get("keywords", [])
        except Exception as e:
            print(f"[AI] suggest_keywords 失败: {e}")
        return []

    def build_image_prompt(
        self,
        chinese_description: str,
        topic_title: str = "",
        content_style: str = "",
        image_style: str = "",
        platform: str = "小红书",
        meta: dict = None,
    ) -> str:
        """
        将中文图片描述生成专业、真实感强的 gpt-image-2 提示词。
        返回中文 prompt（gpt-image-2 支持中文且效果好）。

        meta: 可选出参 dict。扩写失败退回原描述时，写入
              meta["fallback"]=True 和 meta["reason"]，供调用方向用户说明。
        """
        if not self.api_key:
            if meta is not None:
                meta["fallback"] = True
                meta["reason"] = "AI Key 未配置，未扩写"
            return chinese_description

        is_cartoon = "卡通" in (content_style or "") or "插画" in (content_style or "") or "卡通" in (image_style or "")

        # 视觉风格完全来自用户设定，不预设
        if content_style and image_style:
            visual_style = f"{content_style}；{image_style}"
        elif image_style:
            visual_style = image_style
        else:
            visual_style = content_style or ""

        system = f"""你是 gpt-image-2 提示词生成专家。

用户的图片视觉风格要求：
「{visual_style or "用户未指定，按图片内容自然发挥"}」

你的任务：根据用户的视觉风格要求，把简短的图片描述扩展成详细的 gpt-image-2 提示词。

核心原则：
- 完全忠实于用户说的视觉风格，不要擅自升级或改变
- 如果用户要"随手拍、手机感、生活感、粗糙感" → 提示词要体现：手机随拍感，自然光线，真实生活场景，不过度打光
- 如果用户要"卡通插画" → 扁平插画风格，可爱卡通，无写实感，线条清晰，马卡龙色系
- 如果用户要"专业摄影、精致大片" → 专业摄影布光，浅景深，商业级质感，精心构图
- 如果用户要"小清新自然光" → 柔和自然光，明亮清爽，简洁背景，清新色调
- 没有指定风格时，根据内容选择最自然合适的方式

输出格式：全部用中文输出，直接给出提示词，100-200字，详细描述画面构图、光线、色调、质感、氛围，不要解释不要引号。"""

        user_msg = (
            f"内容主题：{topic_title or ''}\n"
            f"图片描述：{chinese_description}\n\n"
            "请生成详细的 gpt-image-2 中文提示词："
        )

        try:
            resp = requests.post(
                f"{self.endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.6,
                    "max_tokens": 400,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                body = resp.json()
                choice0 = (body.get("choices") or [{}])[0]
                result = (choice0.get("message", {}).get("content") or "").strip()
                # LLM 偶尔对某些描述返回空 completion，此时退回原始描述，绝不返回空
                if result:
                    print(f"[ImagePrompt] {chinese_description[:30]}... → {result[:80]}...")
                    return result
                # 诊断：打印 finish_reason / usage，定位空响应到底是限流、审核还是截断
                print(
                    f"[ImagePrompt] 扩写返回空，退回原描述 | "
                    f"finish_reason={choice0.get('finish_reason')} "
                    f"usage={body.get('usage')} "
                    f"desc={chinese_description[:40]}"
                )
                if meta is not None:
                    meta["fallback"] = True
                    meta["reason"] = "AI 返回空内容"
            else:
                print(f"[ImagePrompt] HTTP {resp.status_code}: {resp.text[:200]}，退回原描述")
                if meta is not None:
                    meta["fallback"] = True
                    meta["reason"] = f"AI 服务返回 HTTP {resp.status_code}"
        except Exception as e:
            print(f"[AI] build_image_prompt 失败: {e}")
            if meta is not None:
                meta["fallback"] = True
                meta["reason"] = "AI 服务调用异常"
        return chinese_description

    def analyze_requirements(self, messages: list) -> Dict[str, Any]:
        """Analyze chat messages to extract user requirements."""
        if not self.api_key:
            raise Exception("DeepSeek API Key 未配置")
        
        # Build prompt with recent messages (limit to 10)
        chat_lines = []
        for m in messages[-10:]:
            chat_lines.append(f"{m['role']}: {m['message']}")
        chat_history = "\n".join(chat_lines)
        
        ai_prompt = f"""你是 MediaFlow 的需求分析助手。

【对话背景】
以下是用户与 AI 运营助手"小媒"的聊天记录。
小媒是一个亲切专业的内容运营顾问，通过自然聊天了解用户的文案创作需求。

【聊天记录】
{chat_history}

【任务】
从对话中提取两类信息：

【第一类：功能性配置】
- publish_frequency: 发布频率（如"每天"、"每周 3 次"）
- image_source: 图片来源（如"实拍"、"网图"、"AI 生成"）
- platform: 发布平台（默认"小红书"）

【第二类：文案生成要求】（重点！）
把用户提到的所有文案相关的要求、偏好、规则整理成一个列表。

**特别注意**：
1. 用户可能说"我想要 XX"（正面要求）
2. 用户也可能说"不要 XX"、"不喜欢 XX"、"别用 XX"（否定/禁用）
3. 否定表达也要记录！例如：
   - 用户说"不要用绝绝子" → 记录："不要用'绝绝子'等网络流行语"
   - 用户说"不喜欢连锁店" → 记录："不要连锁店，只要独立小店"
4. 用户的语气偏好也要记录（如"像朋友聊天"、"不要太正式"）

**要求列表格式**：
- 直接引用用户的原话（可以稍微整理通顺）
- 不要分类（不要分什么"主题"、"风格"、"类型"）
- 按重要性排序（用户反复说的、强调的放前面）
- 不确定的返回 null

返回 JSON 格式：
{{
  "publish_frequency": "每周 3 次",
  "image_source": "实拍",
  "platform": "小红书",
  "requirements": [
    "要求 1（用户原话或整理）",
    "要求 2（包括否定表达，如'不要用 XX'）",
    ...
  ]
}}"""
        
        try:
            url = f"{self.endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": ai_prompt}],
                "temperature": 1.0  # 数据抽取/分析场景
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                ai_content = result["choices"][0]["message"]["content"]
                requirements = self._extract_json(ai_content)
                requirements['platform'] = requirements.get('platform', '小红书')
                return requirements
            else:
                raise Exception(f"DeepSeek API 调用失败：{response.status_code}")
        except Exception as e:
            print(f"[AI 需求分析] 失败：{e}")
            raise
    
    def _extract_json(self, content: str) -> Dict[str, Any]:
        """Extract JSON from AI response."""
        import json
        
        # Try direct parse
        try:
            return json.loads(content)
        except:
            pass
        
        # Extract from markdown code block
        match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        
        # Extract first { to last }
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end])
            except:
                pass
        
        raise ValueError(f"无法提取 JSON: {content[:200]}")

    
    def _parse_ai_response(self, content: str, default_topic: str) -> Dict[str, Any]:
        """Parse AI response into structured format."""
        lines = content.split("\n")
        title = default_topic
        body_lines = []
        tags = [default_topic, "分享", "种草"]
        
        in_body = False
        for line in lines:
            if line.startswith("标题："):
                title = line.replace("标题：", "").strip()
                in_body = False
            elif line.startswith("正文："):
                body_text = line.replace("正文：", "").strip()
                if body_text:
                    body_lines.append(body_text)
                in_body = True
            elif line.startswith("标签："):
                tag_str = line.replace("标签：", "").strip()
                tags = [t.strip() for t in tag_str.split(",")]
                in_body = False
            elif in_body and line.strip():
                body_lines.append(line.strip())
        
        body = "\n".join(body_lines)
        
        if not body:
            body = content
        
        return {
            "title": title,
            "content": body,
            "tags": tags[:5]
        }
