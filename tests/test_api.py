# tests/test_api.py
import pytest
import httpx

BASE_URL = "http://localhost:8000"

@pytest.mark.asyncio
async def test_get_alerts():
    """Test that the /alerts endpoint returns a 200 OK and a list of alerts."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

@pytest.mark.asyncio
async def test_check_location_valid():
    """Test that valid coordinates are accepted."""
    payload = {"lat": -29.0, "lon": 25.0} # Valid South Africa coords
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/alerts/check", json=payload)
        assert response.status_code == 200
        assert response.json()["message"] == "Coordinates are valid."

@pytest.mark.asyncio
async def test_check_location_invalid():
    """Test that impossible coordinates are rejected with a 422 error."""
    payload = {"lat": 999.0, "lon": 999.0}
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/alerts/check", json=payload)
        assert response.status_code == 422 # Unprocessable Entity
        assert "lat" in response.text or "lon" in response.text