
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(tags=["GES Dashboard"])


@router.get("/solar/dashboard", include_in_schema=False)
def get_solar_dashboard() -> FileResponse:
    """
    Serve the local, read-only GES dashboard.
    """
    dashboard_file = (
        Path(__file__).resolve().parent
        / "static"
        / "solar_dashboard.html"
    )

    return FileResponse(
        dashboard_file,
        media_type="text/html",
    )
