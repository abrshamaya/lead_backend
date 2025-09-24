"""
ASGI config for AmayaLead project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import sys
import asyncio
from django.core.asgi import get_asgi_application

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

print("Using event loop policy:", asyncio.get_event_loop_policy())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AmayaLead.settings')

application = get_asgi_application()
