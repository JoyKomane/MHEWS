# ============================================================
#  BACKGROUND SCHEDULER — Automates the Feed Polling
# ============================================================
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from gis.ingestor import poll_all_feeds

# Initialize the scheduler
scheduler = AsyncIOScheduler()

async def run_scheduled_poll():
    """
    Wrapper to run the async ingestor safely in the background.
    Catches any errors so the scheduler never crashes the main app.
    """
    try:
        print("\n🔄 [SCHEDULER] Starting background feed poll...")
        await poll_all_feeds()
        print("✅ [SCHEDULER] Background poll complete.\n")
    except Exception as e:
        print(f" [SCHEDULER] Background poll failed: {e}")

# Add the job to run every 60 seconds
scheduler.add_job(
    run_scheduled_poll, 
    trigger='interval', 
    seconds=60, 
    id='mhews_feed_poll', 
    name='Poll WMO/GDACS/NASA Feeds',
    replace_existing=True
)

# Start the scheduler when the FastAPI app starts
@app.on_event("startup")
async def start_scheduler():
    print("🚀 [SCHEDULER] Starting background scheduler (60s interval)...")
    scheduler.start()
    
    # Optional: Run it immediately on startup so we don't wait 60s for the first data
    await run_scheduled_poll() 

@app.on_event("shutdown")
async def shutdown_scheduler():
    print("🛑 [SCHEDULER] Shutting down background scheduler...")
    scheduler.shutdown()