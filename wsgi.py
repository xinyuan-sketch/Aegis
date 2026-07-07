"""Gunicorn 入口：gunicorn -c deploy/gunicorn.conf.py wsgi:app"""
from app import create_app

app = create_app()
