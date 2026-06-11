from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import OutreachTemplate

VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def extract_variables(text: str) -> list[str]:
    return sorted(set(VARIABLE_PATTERN.findall(text)))


def render_template(template_text: str, variables: dict[str, str]) -> str:
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))
    return VARIABLE_PATTERN.sub(_replace, template_text)


class OutreachTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        name: str,
        subject_template: str,
        body_template: str,
        channel: str = "email",
        tone: str = "professional",
        description: str | None = None,
        variables_schema: list[str] | None = None,
    ) -> OutreachTemplate:
        extracted = extract_variables(f"{subject_template}\n{body_template}")
        template = OutreachTemplate(
            name=name,
            description=description,
            channel=channel,
            subject_template=subject_template,
            body_template=body_template,
            variables_schema=variables_schema or extracted,
            tone=tone,
        )
        self.session.add(template)
        await self.session.commit()
        await self.session.refresh(template)
        return template

    async def get(self, template_id: str) -> OutreachTemplate | None:
        result = await self.session.execute(
            select(OutreachTemplate).where(OutreachTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, channel: str | None = None, only_active: bool = True, offset: int = 0, limit: int = 50
    ) -> list[OutreachTemplate]:
        query = select(OutreachTemplate)
        if only_active:
            query = query.where(OutreachTemplate.is_active.is_(True))
        if channel:
            query = query.where(OutreachTemplate.channel == channel)
        query = query.order_by(OutreachTemplate.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        template_id: str,
        **kwargs: Any,
    ) -> OutreachTemplate | None:
        template = await self.get(template_id)
        if template is None:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(template, key):
                setattr(template, key, value)
        if "subject_template" in kwargs or "body_template" in kwargs:
            combined = f"{template.subject_template}\n{template.body_template}"
            template.variables_schema = extract_variables(combined)
        await self.session.commit()
        await self.session.refresh(template)
        return template

    async def delete(self, template_id: str) -> bool:
        template = await self.get(template_id)
        if template is None:
            return False
        template.is_active = False
        await self.session.commit()
        return True

    async def preview(
        self, template_id: str, variables: dict[str, str]
    ) -> dict[str, str] | None:
        template = await self.get(template_id)
        if template is None:
            return None
        if template.variables_schema:
            missing = [v for v in template.variables_schema if v not in variables]
            if missing:
                return None
        return {
            "subject": render_template(template.subject_template, variables),
            "body_text": render_template(template.body_template, variables),
        }
