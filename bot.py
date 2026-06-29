import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import gspread
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

NAME, PHONE, REQUEST_TEXT = range(3)

HEADERS = ["Дата", "Telegram ID", "Username", "Имя", "Телефон", "Заявка"]
START_BUTTON = "Старт"


def start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[START_BUTTON]], resize_keyboard=True)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_gspread_client():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        credentials = json.loads(service_account_json)
        return gspread.service_account_from_dict(credentials)

    credentials_path = require_env("GOOGLE_APPLICATION_CREDENTIALS")
    return gspread.service_account(filename=credentials_path)


def get_worksheet():
    spreadsheet_id = require_env("GOOGLE_SPREADSHEET_ID")
    worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME", "Заявки")

    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(HEADERS))

    first_row = worksheet.row_values(1)
    if first_row != HEADERS:
        worksheet.update("A1:F1", [HEADERS])

    return worksheet


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Здравствуйте! Оставим заявку. Как вас зовут?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Укажите номер телефона для связи.")
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("Кратко опишите заявку.")
    return REQUEST_TEXT


async def collect_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["request_text"] = update.message.text.strip()

    user = update.effective_user
    row = [
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        str(user.id),
        user.username or "",
        context.user_data["name"],
        context.user_data["phone"],
        context.user_data["request_text"],
    ]

    try:
        worksheet = get_worksheet()
        worksheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        logging.exception("Failed to save lead")
        await update.message.reply_text(
            "Заявку не удалось сохранить. Попробуйте позже или напишите администратору."
        )
        return ConversationHandler.END

    await update.message.reply_text("Спасибо! Заявка принята.")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Заполнение заявки отменено.", reply_markup=start_keyboard())
    return ConversationHandler.END


async def show_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Нажмите кнопку «Старт», чтобы оставить заявку.",
        reply_markup=start_keyboard(),
    )
    return ConversationHandler.END


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_application() -> Application:
    token = require_env("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(token).build()

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{START_BUTTON}$"), start),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            REQUEST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_request)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conversation)
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_start_button))
    return application


def main() -> None:
    load_dotenv()
    configure_logging()

    if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        require_env("GOOGLE_APPLICATION_CREDENTIALS")

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
