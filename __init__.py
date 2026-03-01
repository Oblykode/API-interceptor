"""
API Interceptor Pro - Professional HTTP Traffic Analysis

A powerful HTTP traffic interception tool inspired by Burp Suite.
See, modify, and analyze HTTP/HTTPS requests and responses in real-time
with a modern, dark-themed interface.
"""

from .main import main
from .config import TARGET_IPS, INTERCEPT_ALL, PROXY_HOST, PROXY_PORT, UI_BASE_URL

__version__ = "1.0.0"
__author__ = "API Interceptor Pro Team"
__description__ = "Professional HTTP Traffic Analysis Tool"

__all__ = [
    'main',
    'TARGET_IPS',
    'INTERCEPT_ALL', 
    'PROXY_HOST',
    'PROXY_PORT',
    'UI_BASE_URL'
]
