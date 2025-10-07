"""Lightweight heuristic agent that maps chat requests to LinkedIn tools."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from linkedin_mcp_server.error_handler import convert_exception_to_response
from linkedin_mcp_server.services.linkedin_data import (
    fetch_company_profile,
    fetch_job_details,
    fetch_person_profile,
    fetch_recommended_jobs,
    search_jobs,
)

_PROFILE_URL = re.compile(r"linkedin\.com/(?:in|pub)/([\w\-_%]+)", re.IGNORECASE)
_COMPANY_URL = re.compile(r"linkedin\.com/company/([\w\-_%]+)", re.IGNORECASE)
_JOB_URL = re.compile(r"linkedin\.com/jobs/view/(\d+)", re.IGNORECASE)


class SimpleLinkedInAgent:
    """A minimal rule-based layer that calls LinkedIn scraping helpers."""

    def __init__(self) -> None:
        self._history: Dict[str, List[Dict[str, str]]] = {}

    def _record(self, session_token: str, role: str, content: str) -> None:
        history = self._history.setdefault(session_token, [])
        history.append({"role": role, "content": content})
        # Keep the last 20 turns per session to avoid unbounded growth
        if len(history) > 40:
            del history[:-40]

    def get_history(self, session_token: str) -> List[Dict[str, str]]:
        """Expose the tracked chat history for debugging or UI display."""

        return list(self._history.get(session_token, []))

    async def handle_message(self, session_token: str, message: str) -> Dict[str, Any]:
        """Respond to a chat message by choosing an appropriate LinkedIn action."""

        self._record(session_token, "user", message)
        lowered = message.lower()

        try:
            if "recommended" in lowered and "job" in lowered:
                jobs = await asyncio.to_thread(
                    fetch_recommended_jobs, session_token=session_token
                )
                reply = self._format_job_response(jobs, "Here are your recommended jobs:")
                return self._success(session_token, reply, {"jobs": jobs})

            if "search" in lowered and "job" in lowered:
                query = self._extract_job_search_query(message)
                if not query:
                    return self._success(
                        session_token,
                        "Tell me what kind of role you want me to search for, like 'search jobs for product manager in Berlin'.",
                    )
                jobs = await asyncio.to_thread(
                    search_jobs, query, session_token=session_token
                )
                reply = self._format_job_response(
                    jobs, f"I found {len(jobs)} job matches for '{query}':"
                )
                return self._success(session_token, reply, {"jobs": jobs, "query": query})

            profile_match = _PROFILE_URL.search(message)
            if profile_match or "profile" in lowered:
                identifier = profile_match.group(1) if profile_match else message
                profile = await asyncio.to_thread(
                    fetch_person_profile,
                    identifier,
                    session_token=session_token,
                )
                reply = self._summarize_profile(profile)
                return self._success(session_token, reply, {"profile": profile})

            company_match = _COMPANY_URL.search(message)
            if company_match or "company" in lowered:
                identifier = company_match.group(1) if company_match else message
                company = await asyncio.to_thread(
                    fetch_company_profile,
                    identifier,
                    session_token=session_token,
                )
                reply = self._summarize_company(company)
                return self._success(session_token, reply, {"company": company})

            job_match = _JOB_URL.search(message)
            if job_match or ("job" in lowered and any(char.isdigit() for char in message)):
                identifier = job_match.group(1) if job_match else message
                job_details = await asyncio.to_thread(
                    fetch_job_details, identifier, session_token=session_token
                )
                reply = self._summarize_job(job_details)
                return self._success(session_token, reply, {"job": job_details})

            return self._success(
                session_token,
                "I can review LinkedIn profiles, company pages, specific job posts, search for roles, or fetch your recommended jobs. Try sharing a LinkedIn link or ask for 'recommended jobs'.",
            )
        except Exception as exc:  # noqa: BLE001
            error_payload = convert_exception_to_response(exc, "chat_agent")
            return {
                "status": "error",
                "message": error_payload.get("message", str(exc)),
                "details": error_payload,
            }

    def _success(
        self,
        session_token: str,
        reply: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._record(session_token, "assistant", reply)
        payload: Dict[str, Any] = {
            "status": "success",
            "reply": reply,
        }
        if extra:
            payload.update(extra)
        payload["history"] = self.get_history(session_token)
        return payload

    @staticmethod
    def _extract_job_search_query(message: str) -> Optional[str]:
        lowered = message.lower()
        if " for " in lowered:
            return message.split(" for ", 1)[1].strip()
        if " about " in lowered:
            return message.split(" about ", 1)[1].strip()
        return None

    @staticmethod
    def _format_job_response(jobs: List[Dict[str, Any]], header: str) -> str:
        if not jobs:
            return "I couldn't find any jobs that match right now. Try adjusting the query."

        preview = jobs[:3]
        bullet_lines = [
            f"• {job.get('title', 'Untitled role')} — {job.get('company', '')} ({job.get('location', 'Location unknown')})"
            for job in preview
        ]
        suffix = "\n".join(bullet_lines)
        more = "\n…" if len(jobs) > len(preview) else ""
        return f"{header}\n{suffix}{more}"

    @staticmethod
    def _summarize_profile(profile: Dict[str, Any]) -> str:
        name = profile.get("name") or "This person"
        job_title = profile.get("job_title") or ""
        company = profile.get("company") or ""
        opener = f"{name}"
        if job_title:
            opener += f" is a {job_title}"
        if company:
            connector = " at " if job_title else " works at "
            opener += f"{connector}{company}"
        experiences = profile.get("experiences", [])
        if experiences:
            latest = experiences[0]
            opener += (
                f". Their recent role is {latest.get('position_title')} at "
                f"{latest.get('company')}"
            )
        return opener

    @staticmethod
    def _summarize_company(company: Dict[str, Any]) -> str:
        name = company.get("name") or "The company"
        industry = company.get("industry")
        headcount = company.get("headcount")
        summary = f"{name}"
        if industry:
            summary += f" operates in the {industry.lower()} sector"
        if headcount:
            summary += f" with around {headcount} employees"
        specialties = company.get("specialties") or []
        if specialties:
            summary += ". Key specialties include " + ", ".join(specialties[:3])
        return summary

    @staticmethod
    def _summarize_job(job: Dict[str, Any]) -> str:
        title = job.get("title") or "This job"
        company = job.get("company") or ""
        location = job.get("location") or ""
        summary = title
        if company:
            summary += f" at {company}"
        if location:
            summary += f" in {location}"
        applicants = job.get("num_applicants")
        if applicants:
            summary += f". Approximately {applicants} people have applied so far"
        return summary


agent = SimpleLinkedInAgent()
