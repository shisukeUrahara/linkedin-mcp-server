# src/linkedin_mcp_server/tools/company.py
"""
LinkedIn company profile scraping tools with employee data extraction.

Provides MCP tools for extracting company information, employee lists, and company
insights from LinkedIn with configurable depth and comprehensive error handling.
"""

import logging
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from linkedin_mcp_server.error_handler import handle_tool_error
from linkedin_mcp_server.services.linkedin_data import fetch_company_profile

logger = logging.getLogger(__name__)


def register_company_tools(mcp: FastMCP) -> None:
    """
    Register all company-related tools with the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance
    """

    @mcp.tool()
    async def get_company_profile(
        company_name: str,
        get_employees: bool = False,
        session_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a specific company's LinkedIn profile.

        Args:
            company_name (str): LinkedIn company name (e.g., "docker", "anthropic", "microsoft")
            get_employees (bool): Whether to scrape the company's employees (slower)

        Returns:
            Dict[str, Any]: Structured data from the company's profile
        """
        try:
            logger.info("Scraping company: %s", company_name)
            if get_employees:
                logger.info("Fetching employees may take a while...")

            return fetch_company_profile(
                company_name,
                get_employees=get_employees,
                session_token=session_token,
            )
        except Exception as e:
            return handle_tool_error(e, "get_company_profile")
