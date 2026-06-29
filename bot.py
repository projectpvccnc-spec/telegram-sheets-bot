import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime, timezone

import gspread
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

NAME, PHONE, REQUEST_TEXT, CONFIRM = range(4)

HEADERS = ["Дата", "Telegram ID", "Username", "Имя", "Телефон", "Заявка"]
START_CALLBACK = "start_form"
CONFIRM_CALLBACK = "confirm_form"
RESTART_CALLBACK = "restart_form"
CANCEL_CALLBACK = "cancel_form"


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Оставить заявку", callback_data=START_CALLBACK)]]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Отправить заявку", callback_data=CONFIRM_CALLBACK)],
            [InlineKeyboardButton("Заполнить заново", callback_data=RESTART_CALLBACK)],
            [InlineKeyboardButton("Отменить", callback_data=CANCEL_CALLBACK)],
        ]
    )


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


def normalize_phone(text: str) -> str:
    return re.sub(r"[^\d+]", "", text.strip())


def is_valid_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    return 7 <= len(digits) <= 15


def summary_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"<b>Имя:</b> {html.escape(context.user_data['name'])}\n"
        f"<b>Телефон:</b> {html.escape(context.user_data['phone'])}\n"
        f"<b>Заявка:</b> {html.escape(context.user_data['request_text'])}\n\n"
        "Если все верно, нажмите кнопку отправки."
    )


async def send_main_menu(update: Update, text: str | None = None) -> int:
    message = text or (
        "<b>Заявка в один чат</b>\n\n"
        "Нажмите кнопку ниже, заполните 3 коротких шага, "
        "и заявка попадет в таблицу."
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            message,
            reply_markup=start_keyboard(),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=start_keyboard(),
            parse_mode="HTML",
        )

    return ConversationHandler.END


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()

    text = "<b>Шаг 1 из 3</b>\nКак вас зовут?"
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )

    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Напишите имя чуть подробнее.")
        return NAME

    context.user_data["name"] = name
    await update.message.reply_text(
        "<b>Шаг 2 из 3</b>\nУкажите номер телефона для связи.",
        parse_mode="HTML",
    )
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = normalize_phone(update.message.text)
    if not is_valid_phone(phone):
        await update.message.reply_text(
            "Похоже, номер введен не полностью. Напишите телефон еще раз."
        )
        return PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text(
        "<b>Шаг 3 из 3</b>\nКратко опишите заявку.",
        parse_mode="HTML",
    )
    return REQUEST_TEXT


async def collect_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    request_text = update.message.text.strip()
    if len(request_text) < 3:
        await update.message.reply_text("Опишите заявку чуть подробнее.")
        return REQUEST_TEXT

    context.user_data["request_text"] = request_text
    await update.message.reply_text(
        summary_text(context),
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    return CONFIRM


def build_row(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    user = update.effective_user
    return [
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        str(user.id),
        user.username or "",
        context.user_data["name"],
        context.user_data["phone"],
        context.user_data["request_text"],
    ]


async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        worksheet = get_worksheet()
        worksheet.append_row(build_row(update, context), value_input_option="USER_ENTERED")
    except Exception:
        logging.exception("Failed to save lead")
        await query.edit_message_text(
            "Заявку не удалось сохранить. Попробуйте позже.",
            reply_markup=start_keyboard(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        "<b>Заявка принята.</b>\nМы свяжемся с вами в ближайшее время.",
        reply_markup=start_keyboard(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()

    if update.callback_query:
        await send_main_menu(update, "<b>Заполнение отменено.</b>\nМожно начать заново.")
    else:
        await update.message.reply_text(
            "<b>Заполнение отменено.</b>\nМожно начать заново.",
            reply_markup=start_keyboard(),
            parse_mode="HTML",
        )

    return ConversationHandler.END


async def show_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_main_menu(update)


async def configure_bot_commands(bot: Bot) -> None:
    await bot.delete_my_commands()


async def post_init(application: Application) -> None:
    await configure_bot_commands(application.bot)


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_application() -> Application:
    token = require_env("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(token).post_init(post_init).build()

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", send_main_menu),
            CallbackQueryHandler(ask_name, pattern=f"^{START_CALLBACK}$"),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            REQUEST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_request)],
            CONFIRM: [
                CallbackQueryHandler(confirm_request, pattern=f"^{CONFIRM_CALLBACK}$"),
                CallbackQueryHandler(ask_name, pattern=f"^{RESTART_CALLBACK}$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern=f"^{CANCEL_CALLBACK}$"),
        ],
        allow_reentry=True,
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
