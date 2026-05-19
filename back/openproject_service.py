import base64
from typing import List, Dict, Optional
import requests

from config import (
    OPENPROJECT_API_URL as OPENPROJECT_URL,
    OPENPROJECT_TOKEN,
    OPENPROJECT_TIMEOUT as TIMEOUT,
)


def _get_headers() -> Dict[str, str]:
    """Build Basic Auth headers for the OpenProject API."""
    credentials = base64.b64encode(f"apikey:{OPENPROJECT_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }


def get_projects() -> List[Dict]:
    """
    Fetch all available projects from OpenProject.
    Returns a list of dicts with id, name, identifier and description.
    """
    url = f"{OPENPROJECT_URL}/api/v3/projects"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        projects = []
        for item in data.get("_embedded", {}).get("elements", []):
            desc_raw = item.get("description", {}).get("raw", "")
            projects.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "identifier": item["identifier"],
                    "description": desc_raw,
                    "active": item.get("active", True),
                }
            )
        return projects
    except Exception as e:
        raise RuntimeError(f"Erro ao buscar projetos do OpenProject: {e}")


def search_work_packages(project_id: int, query: str, limit: int = 5) -> List[Dict]:
    """
    Search for work packages (tickets) in a project that match the query.
    Uses OpenProject's filters to search by subject.
    """
    import json
    url = f"{OPENPROJECT_URL}/api/v3/projects/{project_id}/work_packages"

    # OpenProject uses encoded JSON filters
    filters = json.dumps([{"subjectOrId": {"operator": "**", "values": [query]}}])
    params = {
        "pageSize": limit,
        "filters": filters,
        "sortBy": json.dumps([["updatedAt", "desc"]]),
    }
    try:
        resp = requests.get(url, headers=_get_headers(), params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        packages = []
        for item in data.get("_embedded", {}).get("elements", []):
            status = item.get("_links", {}).get("status", {}).get("title", "")
            type_ = item.get("_links", {}).get("type", {}).get("title", "")
            packages.append(
                {
                    "id": item["id"],
                    "subject": item.get("subject", ""),
                    "description": item.get("description", {}).get("raw", ""),
                    "status": status,
                    "type": type_,
                    "url": f"{OPENPROJECT_URL}/work_packages/{item['id']}",
                }
            )
        return packages
    except Exception as e:
        raise RuntimeError(f"Erro ao buscar tickets no OpenProject: {e}")


def create_work_package(
    project_id: int,
    subject: str,
    description: str,
    type_id: Optional[int] = None,
) -> Dict:
    """
    Create a new work package (ticket/task) in OpenProject.
    Returns the created work package data.
    """
    url = f"{OPENPROJECT_URL}/api/v3/projects/{project_id}/work_packages"

    # Get the first available type for the project if not specified
    if type_id is None:
        type_id = _get_default_type_id(project_id)

    payload = {
        "subject": subject,
        "description": {"format": "markdown", "raw": description},
        "_links": {
            "type": {"href": f"/api/v3/types/{type_id}"},
        },
    }
    try:
        resp = requests.post(url, headers=_get_headers(), json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        item = resp.json()
        return {
            "id": item["id"],
            "subject": item.get("subject", ""),
            "url": f"{OPENPROJECT_URL}/work_packages/{item['id']}",
            "status": item.get("_links", {}).get("status", {}).get("title", ""),
        }
    except Exception as e:
        raise RuntimeError(f"Erro ao criar ticket no OpenProject: {e}")


def _get_default_type_id(project_id: int) -> int:
    """Returns the first available type ID for the project, defaulting to 1 (Task)."""
    url = f"{OPENPROJECT_URL}/api/v3/projects/{project_id}/types"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        types = resp.json().get("_embedded", {}).get("elements", [])
        if types:
            return types[0]["id"]
    except Exception:
        pass
    return 1  
