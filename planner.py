from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from work_mode import WorkMode


QUESTIONS = [
    "What programming language or framework would you prefer?",
    "Are there any specific requirements or constraints I should know about?",
    "Shall I start immediately, or do you need to prepare anything first?",
]


@dataclass
class _Session:
    description: str
    answers: list[dict] = field(default_factory=list)
    step: int = 0


class Planner:
    def __init__(self, work_mode: WorkMode) -> None:
        self._work_mode = work_mode
        self._sessions: dict[str, _Session] = {}

    def is_planning(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def start(self, session_id: str, description: str) -> str:
        self._sessions[session_id] = _Session(description=description)
        return f"Certainly, sir. {QUESTIONS[0]}"

    async def answer(self, session_id: str, user_answer: str) -> str:
        session = self._sessions.get(session_id)
        if not session:
            return "No active planning session."

        question = QUESTIONS[session.step] if session.step < len(QUESTIONS) else ""
        session.answers.append({"q": question, "a": user_answer})
        session.step += 1

        done = (
            session.step >= len(QUESTIONS)
            or user_answer.lower().strip() in {"no", "none", "nothing", "start", "go", "yes"}
        )

        if done:
            context_lines = "\n".join(
                f"Q: {a['q']}\nA: {a['a']}" for a in session.answers
            )
            prompt = (
                f"Task: {session.description}\n\nContext:\n{context_lines}\n\n"
                "Please implement this task."
            )
            result = await self._work_mode.start_task(prompt)
            del self._sessions[session_id]
            return result

        return QUESTIONS[session.step]
