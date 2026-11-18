"""WSGI entry point for Gunicorn and Flask CLI."""

from backend.app import create_app

app = create_app()
