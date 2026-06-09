# ============================================================
#  MHEWS — backend/main.py
#  B4: The FastAPI application scaffold.
#
#  This is the entry point for your entire backend.
#  Right now it has no endpoints — we add those in B5, B6, B9.
#  The goal for B4 is simply:
#    1. App starts without errors
#    2. Database connection works
#    3. http://localhost:8000/docs loads (auto-generated API docs)
#
#  Run locally (outside Docker):
#    uvicorn backend.main:app --reload
# ============================================================

# --- Standard library imports ---
import os                    # For reading environment variables

# --- Third party imports ---
from fastapi import FastAPI  # The web framework
from fastapi.middleware.cors import CORSMiddleware  # Handles CORS headers
import databases             # Async database connection library
import sqlalchemy            # For defining table schemas in Python
from dotenv import load_dotenv  # Loads our .env file

# ============================================================
#  Load environment variables from .env file
# ============================================================
#  This reads the .env file and makes all variables available
#  via os.environ or os.getenv().
#  Must be called before anything that reads environment vars.
# ============================================================
load_dotenv()

# ============================================================
#  Read configuration from environment variables
# ============================================================
#  os.getenv(key, default) reads a variable from the environment.
#  If the variable is not set, it uses the default value.
#  This way the app works both locally and in Docker.
# ============================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgres://postgres:postgres@localhost:5432/mhews"  # local fallback
)

# ============================================================
#  Set up the async database connection
# ============================================================
#  databases.Database creates a connection pool.
#  A connection pool keeps several database connections open
#  so the app doesn't have to open a new connection for
#  every single request — much faster.
# ============================================================
database = databases.Database(DATABASE_URL)

# ============================================================
#  Define the SQLAlchemy metadata and table structure
# ============================================================
#  SQLAlchemy metadata keeps track of our table definitions.
#  We define the alerts table structure here in Python so
#  SQLAlchemy can build correct SQL queries for us.
#  This doesn't CREATE the table — init.sql does that.
#  This just tells SQLAlchemy what columns exist.
# ============================================================
metadata = sqlalchemy.MetaData()

alerts_table = sqlalchemy.Table(
    "alerts",
    metadata,
    sqlalchemy.Column("id",                   sqlalchemy.Text, primary_key=True),
    sqlalchemy.Column("event",                sqlalchemy.Text),
    sqlalchemy.Column("severity",             sqlalchemy.Text),
    sqlalchemy.Column("urgency",              sqlalchemy.Text),
    sqlalchemy.Column("description",          sqlalchemy.Text),
    sqlalchemy.Column("instruction",          sqlalchemy.Text),
    sqlalchemy.Column("onset",                sqlalchemy.DateTime(timezone=True)),
    sqlalchemy.Column("expires",              sqlalchemy.DateTime(timezone=True)),
    sqlalchemy.Column("source",               sqlalchemy.Text),
    sqlalchemy.Column("area_desc",            sqlalchemy.Text),
    sqlalchemy.Column("plain_text",           sqlalchemy.Text),
    sqlalchemy.Column("plain_text_language",  sqlalchemy.Text),
    sqlalchemy.Column("accuracy_percent",     sqlalchemy.Integer),
    sqlalchemy.Column("hazard_category",      sqlalchemy.Text),
    # Note: the polygon column is a special PostGIS geometry type.
    # SQLAlchemy doesn't know about it natively — we handle it
    # with raw SQL in the endpoint files (B5, B6).
    sqlalchemy.Column("created_at",           sqlalchemy.DateTime(timezone=True)),
)

# ============================================================
#  Create the FastAPI application
# ============================================================
#  FastAPI() creates the app object.
#  title, description, version appear in the auto-generated
#  docs page at http://localhost:8000/docs
# ============================================================
app = FastAPI(
    title="MHEWS API",
    description=(
        "Multi-Hazard Early Warning System — "
        "People-centred CAP alert API for South Africa. "
        "MSc thesis prototype."
    ),
    version="0.1.0",
)

# ============================================================
#  Configure CORS (Cross-Origin Resource Sharing)
# ============================================================
#  CORS is a browser security feature that blocks requests
#  from one domain to another unless the server explicitly
#  allows it.
#
#  Our frontend runs on http://localhost:3000 (or just opens
#  as a file) and our API runs on http://localhost:8000.
#  Without CORS middleware, the browser would block the
#  frontend from calling our API.
#
#  allow_origins: which URLs are allowed to call our API.
#  In development we allow everything ("*").
#  In production you would set this to your actual domain.
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Allow all origins in development
    allow_credentials=True,    # Allow cookies and auth headers
    allow_methods=["*"],       # Allow GET, POST, PUT, DELETE etc.
    allow_headers=["*"],       # Allow any request headers
)

# ============================================================
#  Startup and shutdown events
# ============================================================
#  @app.on_event("startup") runs when the server starts.
#  @app.on_event("shutdown") runs when the server stops.
#
#  We use these to open and close the database connection pool.
#  This is the correct way to manage DB connections in FastAPI.
# ============================================================

@app.on_event("startup")
async def startup():
    """
    Runs when the FastAPI server starts.
    Opens the database connection pool.
    """
    # Connect to PostGIS.
    # If this fails, the server will crash with a clear error
    # message — which is better than silently failing later.
    await database.connect()
    print("✅ MHEWS API started — database connected.")

@app.on_event("shutdown")
async def shutdown():
    """
    Runs when the FastAPI server stops (Ctrl+C or container stop).
    Closes the database connection pool cleanly.
    """
    await database.disconnect()
    print("🛑 MHEWS API stopped — database disconnected.")

# ============================================================
#  Health check endpoint
# ============================================================
#  GET /health — a simple endpoint that returns "ok".
#
#  Why do we need this?
#  1. Docker can use it to check if the app is running.
#  2. You can curl it to quickly confirm the server is up.
#  3. Monitoring tools use health checks to alert you if
#     the server goes down.
#
#  Test it: curl http://localhost:8000/health
# ============================================================

@app.get("/health", tags=["System"])
async def health_check():
    """
    Returns the health status of the API and database connection.
    """
    try:
        # Run a trivial query to confirm the DB is reachable.
        # If this fails, the database is down or misconfigured.
        await database.fetch_one("SELECT 1")
        return {
            "status": "ok",
            "api": "running",
            "database": "connected"
        }
    except Exception as e:
        # Return a 500-style response with the error detail.
        return {
            "status": "error",
            "api": "running",
            "database": str(e)
        }

# ============================================================
#  Root endpoint
# ============================================================
#  GET / — returns a welcome message with links to the docs.
#
#  Test it: curl http://localhost:8000/
#  Or just open http://localhost:8000 in your browser.
# ============================================================

@app.get("/", tags=["System"])
async def root():
    """
    Root endpoint — confirms the API is running and shows links.
    """
    return {
        "message": "MHEWS API is running",
        "docs":    "http://localhost:8000/docs",
        "health":  "http://localhost:8000/health",
        "version": "0.1.0"
    }

# ============================================================
#  Register routers
# ============================================================
#  Each router lives in its own file to keep things organised.
#  include_router() adds all the routes from that file to app.
#
#  B5 + B6 live in backend/alerts.py
#  After this, the following endpoints exist:
#    GET  /alerts        — all active alerts from PostGIS
#    POST /alerts/check  — point-in-polygon GPS check
# ============================================================
from backend.alerts import router as alerts_router
app.include_router(alerts_router)

# B9 — translation endpoint
from backend.translate import router as translate_router
app.include_router(translate_router)

# ============================================================
#  NOTE: More endpoints added in the next steps:
#  B7 — CAP XML parser in gis/cap_parser.py
#  B8 — accuracy metric in gis/accuracy.py
#  B9 — POST /alerts/translate (Claude API plain language)
#  B10 — background ingestor in gis/ingestor.py
# ============================================================
