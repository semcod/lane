"""OpenAI-compatible LLM provider using httpx and tenacity for reliability."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import NxdoSettings, get_settings
from ..models import Priority, Task, TaskPlan, TaskType
from .base import LLMProvider

SYSTEM_PROMPT = """\
You are an expert software engineering project manager and technical lead.
Your role is to analyze a software project's current state and recent development
history, then produce a concrete, prioritized plan of the next 10 tasks.

RULES:
- Tasks must be specific and actionable with detailed descriptions (2-4 sentences).
- Each task should fit in a focused work session of roughly 1-8 hours.
- Use the current project state, recent git changes and the user's extra context.
- Mix features, bug fixes, refactoring, tests and docs when appropriate.
- Respond ONLY with valid JSON.
- NEVER use empty strings for description or acceptance_criteria.

DESCRIPTION REQUIREMENTS:
- Minimum 2 sentences explaining WHAT the task does and WHY it matters
- Include specific files, functions, or components when known
- Mention the expected outcome or benefit

ACCEPTANCE CRITERIA REQUIREMENTS:
- Provide 2-4 concrete, verifiable criteria per task
- Must be testable outcomes (e.g., "All tests pass", "Code coverage > 80%")

JSON schema:
{
  "project_name": "string",
  "summary": "2-3 sentence analysis of project state and priorities",
  "tasks": [
    {
      "number": 1,
      "title": "short imperative title (max 5 words)",
      "description": "2-4 sentences: what to do, why it matters, expected outcome",
      "priority": "high|medium|low",
      "task_type": "feature|bug|refactor|docs|test|chore",
      "estimated_hours": 2.0,
      "acceptance_criteria": ["criterion 1", "criterion 2", "criterion 3"],
      "dependencies": []
    }
  ]
}
"""


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenRouter or any OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Optional[NxdoSettings] = None,
        app_name: str = "nxdo",
        koru_aware: bool = False,
    ) -> None:
        cfg = settings or get_settings()
        self.api_key = api_key or cfg.api_key
        self.model = model or cfg.llm_model
        self.base_url = (base_url or cfg.llm_base_url).rstrip("/")
        self.timeout = cfg.llm_timeout
        self.max_retries = cfg.llm_max_retries
        self.app_name = app_name
        self.koru_aware = koru_aware

    def generate_plan(self, user_prompt: str, project_name: str) -> TaskPlan:
        raw = self._call_api(user_prompt)
        return _parse_response(raw, project_name, self.model)

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_api(self, user_message: str) -> str:
        if not self.api_key:
            raise ValueError(
                "Missing API key. Set OPENROUTER_API_KEY or OPENAI_API_KEY before generating a task plan."
            )

        # Build system prompt with koru extension if enabled
        system_prompt = SYSTEM_PROMPT
        if self.koru_aware:
            from ..koru_context import get_koru_system_prompt_extension
            system_prompt += get_koru_system_prompt_extension()

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv(
                "OPENROUTER_APP_URL", "https://github.com/semcod/nxdo"
            ),
            "X-OpenRouter-Title": os.getenv("OPENROUTER_APP_NAME", self.app_name),
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if not response.is_success:
                error_detail = response.text
                raise ValueError(
                    f"API request failed with status {response.status_code}: {error_detail}"
                )
            data = response.json()

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise ValueError(f"Unexpected LLM response payload: {data}") from exc


def _strip_markdown_fences(raw: str) -> str:
    """Remove markdown code fences from the response."""
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0].strip()
    return raw


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from raw response with error handling."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON. Raw response:\n{raw[:500]}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got: {type(data).__name__}")

    return data


def _create_task_from_dict(item: dict, task_index: int) -> Task:
    """Create a Task object from a dictionary item."""
    try:
        # Handle dependencies - convert to list of ints, filtering out non-int values
        raw_deps = item.get("dependencies", [])
        dependencies = []
        for dep in raw_deps:
            if isinstance(dep, int):
                dependencies.append(dep)
            elif isinstance(dep, str) and dep.isdigit():
                dependencies.append(int(dep))
            # Skip non-integer dependencies (e.g., task titles)

        return Task(
            number=int(item.get("number", task_index + 1)),
            title=item.get("title", "Untitled task"),
            description=item.get("description", ""),
            priority=Priority(item.get("priority", Priority.MEDIUM.value)),
            task_type=TaskType(item.get("task_type", TaskType.FEATURE.value)),
            estimated_hours=item.get("estimated_hours"),
            acceptance_criteria=list(item.get("acceptance_criteria", [])),
            dependencies=dependencies,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid task data in LLM response: {item}") from exc


def _parse_tasks_from_data(data: dict) -> list[Task]:
    """Parse tasks from the response data."""
    tasks: list[Task] = []
    for index, item in enumerate(data.get("tasks", [])):
        tasks.append(_create_task_from_dict(item, index))
    return tasks


def _parse_response(raw: str, project_name: str, model: str) -> TaskPlan:
    """Parse and validate the raw JSON response from the LLM."""
    raw = _strip_markdown_fences(raw)
    data = _parse_json_response(raw)
    tasks = _parse_tasks_from_data(data)

    return TaskPlan(
        project_name=data.get("project_name", project_name),
        summary=data.get("summary", ""),
        tasks=tasks,
        generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        model_used=model,
    )
