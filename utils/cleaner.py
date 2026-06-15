# utils/cleaner.py
async def safe_delete(message):
    try:
        await message.delete()
    except Exception:
        pass
