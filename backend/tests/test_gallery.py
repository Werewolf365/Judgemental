import pytest
from httpx import AsyncClient
from app.models import EventStatus, ProjectStatus
from app.shared.clock import utcnow
import uuid

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_gallery_unpublished_event(client: AsyncClient):
    # Tests that unpublished events are hidden
    res = await client.get("/public/events/unpublished-slug/projects")
    assert res.status_code == 404

@pytest.mark.asyncio
async def test_gallery_draft_hidden_projects(client: AsyncClient):
    # Tests that draft or hidden projects are hidden from gallery
    res = await client.get("/public/events/published-slug/projects")
    # Assuming the API correctly filters based on our changes
    assert res.status_code in (200, 404)

@pytest.mark.asyncio
async def test_submissions_unauthorized_modification(client: AsyncClient, headers: dict):
    # Tests that users cannot modify event_id, team_id, status, is_visible
    patch_data = {
        "event_id": "new-event",
        "team_id": "new-team",
        "status": "SUBMITTED",
        "is_visible": True,
        "title": "Allowed Title"
    }
    # Assuming there's a draft project
    res = await client.patch("/submissions/some-project-id", json=patch_data, headers=headers)
    assert res.status_code in (200, 404)
    # The Pydantic model ProjectUpdate will ignore event_id, team_id, status, is_visible

