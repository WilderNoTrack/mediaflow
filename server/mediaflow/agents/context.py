"""账号上下文：每次运行前由代码从数据库组装，LLM 只读不写。

旧版的坑：账号 ID、定位、长期规则都要 LLM 抄进工具参数，漏抄就失效、抄错就写错账号。
新版一律由这里注入，工具签名里不再出现 account_id。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from mediaflow.domain.models import Account, Draft, Note, Rule, Topic, TopicStatus

NOTES_IN_CONTEXT = 5
NOTE_CHARS = 400


@dataclass(frozen=True)
class AccountContext:
    account_id: str
    user_id: str
    name: str
    theme: str
    audience: str
    content_style: str
    image_style: str
    topic_type: str
    keywords: tuple[str, ...]
    rules: tuple[str, ...]
    recent_titles: tuple[str, ...] = field(default=())
    used_topics: tuple[str, ...] = field(default=())
    notes: tuple[str, ...] = field(default=())  # 运营笔记（调研结论），已截断
    playbook: str = ""  # 对标账号的打法摘要（复刻模式）

    def profile_text(self) -> str:
        lines = [
            f"账号名称：{self.name}",
            f"账号主题：{self.theme or '未设定'}",
            f"目标受众：{self.audience or '未设定'}",
            f"文案风格：{self.content_style or '真实、口语化、有干货'}",
            f"配图风格：{self.image_style or '真实感手机摄影'}",
            f"选题方向：{self.topic_type or '围绕主题自由发挥'}",
        ]
        if self.keywords:
            lines.append("关键词：" + "、".join(self.keywords))
        if self.playbook:
            lines.append("【对标账号打法（照这个思路做，内容换成本账号主题，不照抄原文）】")
            lines.append(self.playbook)
        if self.notes:
            lines.append("运营笔记（之前调研的结论，供参考，不必逐条照搬）：")
            lines.extend(f"- {n}" for n in self.notes)
        return "\n".join(lines)

    def rules_text(self) -> str:
        if not self.rules:
            return "（无）"
        return "\n".join(f"{i + 1}. {r}" for i, r in enumerate(self.rules))


def load_context(session: Session, account_id: str) -> AccountContext:
    acc = session.get(Account, account_id)
    if acc is None:
        raise LookupError(f"账号不存在：{account_id}")
    rules = session.exec(
        select(Rule.text)
        .where(Rule.account_id == account_id, Rule.active == True)  # noqa: E712
        .order_by(col(Rule.created_at))
    ).all()
    titles = session.exec(
        select(Draft.title)
        .where(Draft.account_id == account_id)
        .order_by(col(Draft.created_at).desc())
        .limit(30)
    ).all()
    used = session.exec(
        select(Topic.title)
        .where(Topic.account_id == account_id, Topic.status == TopicStatus.used)
        .order_by(col(Topic.created_at).desc())
        .limit(100)
    ).all()
    notes = session.exec(
        select(Note).where(Note.account_id == account_id).order_by(col(Note.created_at).desc()).limit(NOTES_IN_CONTEXT)
    ).all()
    from mediaflow.services.benchmark import plan_text, ready

    benches = ready(session, account_id)
    return AccountContext(
        account_id=acc.id,
        user_id=acc.user_id,
        name=acc.name,
        theme=acc.theme,
        audience=acc.audience,
        content_style=acc.content_style,
        image_style=acc.image_style,
        topic_type=acc.topic_type,
        keywords=tuple(acc.keywords or ()),
        rules=tuple(rules),
        recent_titles=tuple(titles),
        used_topics=tuple(used),
        playbook=plan_text(acc, benches),
        notes=tuple(f"{n.title}：{' '.join(n.content.split())[:NOTE_CHARS]}" for n in notes),
    )
