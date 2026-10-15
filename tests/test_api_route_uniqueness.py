
from collections import Counter

from fastapi.routing import APIRoute

from app.main import app


def test_api_routes_are_not_registered_twice():
    """
    Ensure the same API path and HTTP method
    are not registered multiple times.
    """

    routes = []

    for route in app.routes:

        if not isinstance(route, APIRoute):
            continue

        for method in route.methods:
            routes.append(
                (method, route.path)
            )

    counts = Counter(routes)

    duplicates = {
        key: count
        for key, count in counts.items()
        if count > 1
    }

    assert not duplicates, (
        f"Duplicate API routes: {duplicates}"
    )
