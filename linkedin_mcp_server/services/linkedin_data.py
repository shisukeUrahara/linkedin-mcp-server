"""Shared LinkedIn scraping helpers reused by tools and web features."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from linkedin_scraper import Company, Job, JobSearch, Person

from linkedin_mcp_server.error_handler import safe_get_driver

_PROFILE_REGEX = re.compile(r"linkedin\.com/in/([\w\-_%]+)")
_COMPANY_REGEX = re.compile(r"linkedin\.com/company/([\w\-_%]+)")
_JOB_REGEX = re.compile(r"linkedin\.com/jobs/view/(\d+)")


def _normalize_profile_identifier(identifier: str) -> str:
    match = _PROFILE_REGEX.search(identifier)
    if match:
        return match.group(1).strip("/")
    return identifier.strip().strip("/")


def _normalize_company_identifier(identifier: str) -> str:
    match = _COMPANY_REGEX.search(identifier)
    if match:
        return match.group(1).strip("/")
    return identifier.strip().strip("/")


def _normalize_job_identifier(identifier: str) -> str:
    match = _JOB_REGEX.search(identifier)
    if match:
        return match.group(1)
    return identifier.strip().strip("/")


def fetch_person_profile(
    identifier: str, *, session_token: Optional[str] = None
) -> Dict[str, Any]:
    """Return structured LinkedIn profile data for a username or URL."""

    linkedin_username = _normalize_profile_identifier(identifier)
    linkedin_url = f"https://www.linkedin.com/in/{linkedin_username}/"

    driver = safe_get_driver(session_token=session_token)
    person = Person(linkedin_url, driver=driver, close_on_complete=False)

    experiences: List[Dict[str, Any]] = [
        {
            "position_title": exp.position_title,
            "company": exp.institution_name,
            "from_date": exp.from_date,
            "to_date": exp.to_date,
            "duration": exp.duration,
            "location": exp.location,
            "description": exp.description,
        }
        for exp in person.experiences
    ]

    educations: List[Dict[str, Any]] = [
        {
            "institution": edu.institution_name,
            "degree": edu.degree,
            "from_date": edu.from_date,
            "to_date": edu.to_date,
            "description": edu.description,
        }
        for edu in person.educations
    ]

    interests: List[str] = [interest.title for interest in person.interests]

    accomplishments: List[Dict[str, str]] = [
        {"category": acc.category, "title": acc.title}
        for acc in person.accomplishments
    ]

    contacts: List[Dict[str, str]] = [
        {
            "name": contact.name,
            "occupation": contact.occupation,
            "url": contact.url,
        }
        for contact in person.contacts
    ]

    return {
        "name": person.name,
        "about": person.about,
        "experiences": experiences,
        "educations": educations,
        "interests": interests,
        "accomplishments": accomplishments,
        "contacts": contacts,
        "company": person.company,
        "job_title": person.job_title,
        "open_to_work": getattr(person, "open_to_work", False),
    }


def fetch_company_profile(
    identifier: str,
    *,
    get_employees: bool = False,
    session_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Return LinkedIn company data for a company slug or URL."""

    company_slug = _normalize_company_identifier(identifier)
    linkedin_url = f"https://www.linkedin.com/company/{company_slug}/"

    driver = safe_get_driver(session_token=session_token)
    company = Company(
        linkedin_url,
        driver=driver,
        get_employees=get_employees,
        close_on_complete=False,
    )

    showcase_pages: List[Dict[str, Any]] = [
        {
            "name": page.name,
            "linkedin_url": page.linkedin_url,
            "followers": page.followers,
        }
        for page in company.showcase_pages
    ]

    affiliated_companies: List[Dict[str, Any]] = [
        {
            "name": affiliated.name,
            "linkedin_url": affiliated.linkedin_url,
            "followers": affiliated.followers,
        }
        for affiliated in company.affiliated_companies
    ]

    result: Dict[str, Any] = {
        "name": company.name,
        "about_us": company.about_us,
        "website": company.website,
        "phone": company.phone,
        "headquarters": company.headquarters,
        "founded": company.founded,
        "industry": company.industry,
        "company_type": company.company_type,
        "company_size": company.company_size,
        "specialties": company.specialties,
        "showcase_pages": showcase_pages,
        "affiliated_companies": affiliated_companies,
        "headcount": company.headcount,
    }

    if get_employees and company.employees:
        result["employees"] = company.employees

    return result


def fetch_job_details(
    identifier: str, *, session_token: Optional[str] = None
) -> Dict[str, Any]:
    """Return LinkedIn job details for a job ID or URL."""

    job_id = _normalize_job_identifier(identifier)
    job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

    driver = safe_get_driver(session_token=session_token)
    job = Job(job_url, driver=driver, close_on_complete=False)
    return job.to_dict()


def search_jobs(
    search_term: str, *, session_token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search LinkedIn jobs and return a list of results."""

    driver = safe_get_driver(session_token=session_token)
    job_search = JobSearch(driver=driver, close_on_complete=False, scrape=False)
    jobs = job_search.search(search_term)
    return [job.to_dict() for job in jobs]


def fetch_recommended_jobs(
    *, session_token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return personalized recommended jobs for the authenticated account."""

    driver = safe_get_driver(session_token=session_token)
    job_search = JobSearch(
        driver=driver,
        close_on_complete=False,
        scrape=True,
        scrape_recommended_jobs=True,
    )

    if getattr(job_search, "recommended_jobs", None):
        return [job.to_dict() for job in job_search.recommended_jobs]
    return []
