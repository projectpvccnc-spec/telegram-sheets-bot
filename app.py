import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from telegram import Update

from bot import build_application, configure_logging, require_env

load_dotenv()
configure_logging()

telegram_app = build_application()
api = FastAPI()


def get_webhook_url() -> str | None:
    base_url = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/telegram"


@api.on_event("startup")
async def startup() -> None:
    require_env("TELEGRAM_BOT_TOKEN")
    if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        require_env("GOOGLE_APPLICATION_CREDENTIALS")

    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = get_webhook_url()
    if webhook_url:
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logging.info("Telegram webhook configured.")
    else:
        logging.warning("WEBHOOK_URL is not set; Telegram webhook was not configured.")


@api.on_event("shutdown")
async def shutdown() -> None:
    await telegram_app.stop()
    await telegram_app.shutdown()


@api.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api.post("/telegram")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
