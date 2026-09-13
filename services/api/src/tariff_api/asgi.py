"""ASGI entrypoint: ``uvicorn tariff_api.asgi:app``."""

from .main import create_app

app = create_app()
