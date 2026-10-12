"""The AI capability layer.

Every capability is a plain async function with a typed signature and a strict
Pydantic output model. Controllers call these; nothing else touches the AI client.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from alpago.ai.client import ask, ask_json, load_prompt


SYSTEM_PROMPTS = {
    "default": (
        "You are the HR intelligence assistant for Alpago, a UAE-based real-estate "
        "and contracting group. Be concise, factual, and never invent data. If a "
        "field cannot be inferred, say so explicitly."
    ),
}


# ───────────────────────── JD generation ──────────────────────────────────────

class JobDescription(BaseModel):
    title: str
    summary: str
    responsibilities: list[str]
    requirements: list[str]
    nice_to_have: list[str] = Field(default_factory=list)
    offer_highlights: list[str] = Field(default_factory=list)


async def draft_jd(*, role_title: str, department: str, seniority: str, notes: str = "") -> JobDescription:
    prompt = load_prompt("draft_jd.v1").format(
        role_title=role_title, department=department, seniority=seniority, notes=notes
    )
    data = await ask_json(prompt=prompt, system=SYSTEM_PROMPTS["default"], max_tokens=2000)
    return JobDescription.model_validate(data)


# ───────────────────────── CV screening ───────────────────────────────────────

class CvScreening(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: str  # "strong fit" / "reasonable fit" / "weak fit" / "not fit"
    strengths: list[str]
    gaps: list[str]
    summary: str


async def screen_cv(*, cv_text: str, jd_text: str) -> CvScreening:
    prompt = load_prompt("screen_cv.v1").format(cv=cv_text, jd=jd_text)
    data = await ask_json(prompt=prompt, system=SYSTEM_PROMPTS["default"], max_tokens=1200)
    return CvScreening.model_validate(data)


# ───────────────────────── Interview questions ────────────────────────────────

class InterviewQuestion(BaseModel):
    question: str
    kind: str  # "technical" | "behavioural" | "situational" | "role_fit"
    rationale: str


async def draft_interview_questions(
    *, jd_text: str, cv_text: str, count: int = 8
) -> list[InterviewQuestion]:
    prompt = load_prompt("interview_questions.v1").format(jd=jd_text, cv=cv_text, count=count)
    data = await ask_json(prompt=prompt, system=SYSTEM_PROMPTS["default"], max_tokens=2000)
    return [InterviewQuestion.model_validate(q) for q in data.get("questions", [])]


# ───────────────────────── Offer letter ───────────────────────────────────────

async def draft_offer_letter(
    *, candidate_name: str, role_title: str, salary: str,
    start_date: str, allowances: dict | None = None,
) -> str:
    prompt = load_prompt("offer_letter.v1").format(
        candidate_name=candidate_name,
        role_title=role_title,
        salary=salary,
        start_date=start_date,
        allowances=", ".join(f"{k}: {v}" for k, v in (allowances or {}).items()) or "standard",
    )
    return await ask(prompt=prompt, system=SYSTEM_PROMPTS["default"], max_tokens=1500, temperature=0.3)


# ───────────────────────── Evaluation summary ─────────────────────────────────

class EvaluationSummary(BaseModel):
    headline: str
    strengths: list[str]
    development_areas: list[str]
    recommendation: str


async def summarise_evaluation(evaluations: list[dict]) -> EvaluationSummary:
    prompt = load_prompt("evaluation_summary.v1").format(evaluations=evaluations)
    data = await ask_json(
        prompt=prompt,
        system=SYSTEM_PROMPTS["default"],
        max_tokens=1000,
        model=None,  # use standard model
    )
    return EvaluationSummary.model_validate(data)
