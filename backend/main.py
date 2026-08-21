# backend/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from databases import Database
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import sys
import os

# Ensure we can import from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database setup
DATABASE_URL = "postgresql://postgres:postgres@db:5432/mhews"
database = Database(DATABASE_URL)

app = FastAPI(title="MHEWS API")

# Allow frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup():
    await database.connect()
    print("✅ Database connected.")
    
    # Start the automatic polling scheduler (runs every 10 minutes)
    from gis.ingestor import poll_all_feeds
    scheduler.add_job(poll_all_feeds, 'interval', minutes=10, id='wmo_poller', replace_existing=True)
    scheduler.start()
    print("⏰ Automatic polling scheduler started (runs every 10 minutes).")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    await database.disconnect()
    print("✅ Database disconnected.")

from backend.alerts import router as alerts_router
from backend.translate import router as translate_router
from fastapi.staticfiles import StaticFiles

# Register modular API routers
app.include_router(alerts_router)
app.include_router(translate_router)

# Serve the frontend UI files statically
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)