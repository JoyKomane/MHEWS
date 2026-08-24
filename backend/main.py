# backend/main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from databases import Database
from pydantic import BaseModel, Field
from typing import List, Optional

# 1. Read the database URL from the environment (injected by Docker from the 'fix' file)
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://postgres:postgres@db:5432/mhews")

# Initialize the database connection
database = Database(DATABASE_URL)

# 2. Pydantic Model for Coordinate Validation
class LocationCheck(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude must be between -90 and 90")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude must be between -180 and 180")

# 3. Lifespan context manager for clean DB startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.connect()
    print("✅ Database connected.")
    yield
    # Shutdown
    await database.disconnect()
    print("✅ Database disconnected.")

# Initialize FastAPI
app = FastAPI(title="MHEWS API", lifespan=lifespan)

# Allow CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---

@app.get("/")
async def root():
    return {"message": "MHEWS API is running"}

@app.get("/alerts")
async def get_alerts():
    """Fetch all active alerts from the database."""
    try:
        query = "SELECT * FROM alerts WHERE expires > NOW() ORDER BY last_seen_at DESC LIMIT 100"
        rows = await database.fetch_all(query=query)
        # Convert rows to dictionaries
        return {"alerts": [dict(row) for row in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/alerts/check")
async def check_location(location: LocationCheck):
    """
    Check if a coordinate is inside any active alert polygon.
    The Pydantic model automatically rejects invalid lat/lon before this runs.
    """
    # Example logic: In a real app, you'd query PostGIS here.
    # For now, we just return success to prove validation works.
    return {
        "message": "Coordinates are valid.",
        "lat": location.lat,
        "lon": location.lon,
        "inside_hazard_zone": False 
    }