from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HermesAgentConfig:
    name: str
    system_prompt: str
    base_url: str | None = None
    rate_per_second: float = 1.0


STEPSTONE_PROMPT = """\
You are a job extraction agent for StepStone.de.
Given the raw HTML of a StepStone job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring company
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date (ISO 8601 if available, else human-readable)
- application_url: the direct link to apply (absolute URL)
- source: "stepstone"

Return a JSON array. If no jobs are found, return an empty array.
"""

XING_PROMPT = """\
You are a job extraction agent for Xing.com (Xing Jobs).
Given the raw HTML of a Xing job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring company
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date
- application_url: the direct link to apply (absolute URL)
- source: "xing"

Return a JSON array. If no jobs are found, return an empty array.
"""

MONSTERDE_PROMPT = """\
You are a job extraction agent for Monster.de.
Given the raw HTML of a MonsterDE job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring company
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date
- application_url: the direct link to apply (absolute URL)
- source: "monsterde"

Return a JSON array. If no jobs are found, return an empty array.
"""

INDEEDDE_PROMPT = """\
You are a job extraction agent for Indeed Deutschland (de.indeed.com).
Given the raw HTML of an IndeedDE job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring company
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date
- application_url: the direct link to apply (absolute URL)
- source: "indeedde"

Return a JSON array. If no jobs are found, return an empty array.
"""

LINKEDIN_PROMPT = """\
You are a job extraction agent for LinkedIn Jobs.
Given the raw HTML of a LinkedIn job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring company
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date
- application_url: the direct link to apply (absolute URL)
- source: "linkedin"

Return a JSON array. If no jobs are found, return an empty array.
"""

KIMETA_PROMPT = """\
You are a job extraction agent for Kimeta.de.
Given the raw HTML of a Kimeta job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring company
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date
- application_url: the direct link to apply (absolute URL)
- source: "kimeta"

Return a JSON array. If no jobs are found, return an empty array.
"""

INTERAMT_PROMPT = """\
You are a job extraction agent for Interamt.de (German public sector jobs).
Given the raw HTML of an Interamt job listing page, extract all job postings.
For each job posting, return a JSON object with:
- title: the job title
- company_name: the hiring authority
- location: the work location (city, possibly remote)
- description: a plain-text summary of the job description
- posted_date: the posting date
- application_url: the direct link to apply (absolute URL)
- source: "interamt"

Return a JSON array. If no jobs are found, return an empty array.
"""


HERMES_AGENTS: dict[str, HermesAgentConfig] = {
    "stepstone": HermesAgentConfig(
        name="stepstone",
        system_prompt=STEPSTONE_PROMPT,
        base_url="https://www.stepstone.de",
        rate_per_second=0.5,
    ),
    "xing": HermesAgentConfig(
        name="xing",
        system_prompt=XING_PROMPT,
        base_url="https://www.xing.com/jobs",
        rate_per_second=0.5,
    ),
    "monsterde": HermesAgentConfig(
        name="monsterde",
        system_prompt=MONSTERDE_PROMPT,
        base_url="https://www.monster.de",
        rate_per_second=0.5,
    ),
    "indeedde": HermesAgentConfig(
        name="indeedde",
        system_prompt=INDEEDDE_PROMPT,
        base_url="https://de.indeed.com",
        rate_per_second=0.5,
    ),
    "linkedin": HermesAgentConfig(
        name="linkedin",
        system_prompt=LINKEDIN_PROMPT,
        base_url="https://www.linkedin.com/jobs",
        rate_per_second=0.3,
    ),
    "kimeta": HermesAgentConfig(
        name="kimeta",
        system_prompt=KIMETA_PROMPT,
        base_url="https://www.kimeta.de",
        rate_per_second=1.0,
    ),
    "interamt": HermesAgentConfig(
        name="interamt",
        system_prompt=INTERAMT_PROMPT,
        base_url="https://www.interamt.de",
        rate_per_second=1.0,
    ),
}
