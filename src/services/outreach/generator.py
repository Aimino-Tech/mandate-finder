from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from src.config import settings


@dataclass
class GenerationResult:
    subject: str
    body_text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


@dataclass
class PersonalizationContext:
    recipient_first_name: str = ""
    recipient_last_name: str = ""
    recipient_title: str = ""
    recipient_email: str = ""
    company_name: str = ""
    company_domain: str = ""
    company_industry: str = ""
    company_description: str = ""
    company_employees: int = 0
    motivation_reason: str = ""
    market_signals: list[str] = field(default_factory=list)
    custom_fields: dict[str, str] = field(default_factory=dict)


SYSTEM_PROMPT_TEMPLATE = """You are an expert HR agency business development assistant. Your task is to write a personalized outreach message to a decision-maker at a target company.

## Guidelines
- Keep the tone {tone} and professional
- Personalize based on the recipient's role, company, and industry
- Reference relevant market signals or company context where available
- Include a clear value proposition for the recipient
- End with a low-friction call to action
- Maximum {max_length} words
- Never make up specific facts about the company that you are not provided
- Do not use generic flattery — be specific and relevant

## Output Format
Return a JSON object with exactly these fields:
```json
{{
    "subject": "The email subject line (max 10 words)",
    "body_text": "The full message body in plain text"
}}
```"""


def _build_content_prompt(context: PersonalizationContext, template_subject: str, template_body: str) -> str:
    sections = []

    sections.append("## Recipient")
    sections.append(f"- Name: {context.recipient_first_name} {context.recipient_last_name}")
    sections.append(f"- Title: {context.recipient_title}")
    sections.append(f"- Email: {context.recipient_email}")

    sections.append("\n## Company")
    sections.append(f"- Name: {context.company_name}")
    if context.company_domain:
        sections.append(f"- Domain: {context.company_domain}")
    if context.company_industry:
        sections.append(f"- Industry: {context.company_industry}")
    if context.company_employees:
        sections.append(f"- Employees: ~{context.company_employees}")
    if context.company_description:
        sections.append(f"- Description: {context.company_description}")

    if context.motivation_reason:
        sections.append(f"\n## Reason for Reaching Out\n{context.motivation_reason}")

    if context.market_signals:
        sections.append("\n## Relevant Market Signals")
        for signal in context.market_signals:
            sections.append(f"- {signal}")

    sections.append(f"\n## Template to Follow\nSubject: {template_subject}\n\nBody:\n{template_body}")

    if context.custom_fields:
        sections.append("\n## Additional Context")
        for k, v in context.custom_fields.items():
            sections.append(f"- {k}: {v}")

    return "\n".join(sections)


async def _call_openai(system_prompt: str, content_prompt: str) -> GenerationResult:
    import httpx

    if not settings.agi_api_key:
        return _fallback_generation(content_prompt)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.agi_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.agi_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content_prompt},
                    ],
                    "temperature": settings.agi_temperature,
                    "max_tokens": settings.agi_max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed_ms = int((time.monotonic() - start) * 1000)
            choice = data["choices"][0]
            raw = json.loads(choice["message"]["content"])
            usage = data.get("usage", {})
            return GenerationResult(
                subject=raw.get("subject", ""),
                body_text=raw.get("body_text", ""),
                model=data.get("model", settings.agi_model),
                provider="openai",
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=elapsed_ms,
            )
    except Exception:
        return _fallback_generation(content_prompt)


def _fallback_generation(content_prompt: str) -> GenerationResult:
    lines = content_prompt.split("\n")
    company = ""
    recipient_name = ""
    for line in lines:
        if line.startswith("- Name: ") and "Company" not in line and not recipient_name:
            parts = line.replace("- Name: ", "", 1).strip().split(" ", 1)
            recipient_name = parts[0] if parts else ""
        if line.startswith("- Name: ") and not company:
            name_val = line.replace("- Name: ", "", 1).strip()
            if name_val and name_val != recipient_name:
                company = name_val
    title = ""
    for line in lines:
        if line.startswith("- Title: "):
            title = line.replace("- Title: ", "", 1).strip()
            break

    subject = f"Connecting with {company}" if company else "Introduction"
    body = f"Dear {recipient_name},\n\n"
    if company:
        body += f"I've been following {company}'s recent developments and I believe our HR agency services could be valuable to your team. "
    if title:
        body += f"As {title}, you understand the challenges of finding top talent in today's market. "
    body += "\n\nI'd love to schedule a brief call to discuss how we can support your hiring needs.\n\nBest regards,\nYour HR Agency Partner"

    return GenerationResult(
        subject=subject,
        body_text=body,
        model=settings.agi_model,
        provider="fallback",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=0,
    )


async def _call_anthropic(system_prompt: str, content_prompt: str) -> GenerationResult:
    import httpx

    if not settings.agi_api_key:
        return _fallback_generation(content_prompt)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.agi_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.agi_model,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": content_prompt}],
                    "temperature": settings.agi_temperature,
                    "max_tokens": settings.agi_max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed_ms = int((time.monotonic() - start) * 1000)
            content = data["content"][0]["text"]
            raw = json.loads(content)
            usage = data.get("usage", {})
            return GenerationResult(
                subject=raw.get("subject", ""),
                body_text=raw.get("body_text", ""),
                model=data.get("model", settings.agi_model),
                provider="anthropic",
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                latency_ms=elapsed_ms,
            )
    except Exception:
        return _fallback_generation(content_prompt)


async def generate_message(
    template_subject: str,
    template_body: str,
    context: PersonalizationContext,
    tone: str | None = None,
) -> GenerationResult:
    max_length = settings.agi_max_tokens // 2
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        tone=tone or settings.outreach_default_tone,
        max_length=max_length,
    )
    content_prompt = _build_content_prompt(context, template_subject, template_body)

    if settings.agi_provider == "openai":
        return await _call_openai(system_prompt, content_prompt)
    if settings.agi_provider == "anthropic":
        return await _call_anthropic(system_prompt, content_prompt)

    return _fallback_generation(content_prompt)
