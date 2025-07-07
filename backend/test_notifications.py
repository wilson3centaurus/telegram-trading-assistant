import os
from notifier import Notifier
import asyncio

async def test():
    await Notifier.send_notification("Test notification")

asyncio.run(test())