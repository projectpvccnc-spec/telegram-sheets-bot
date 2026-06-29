import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime, timezone

import gspread
from dotenv import load_dotenv
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

LANGUAGE, CATEGORY, NAME, PHONE, DETAILS, MEDIA, LOCATION, CONTACT_TIME, CUSTOM_TIME, CONFIRM = range(10)

HEADERS = [
    "Номер",
    "Дата",
    "Статус",
    "Telegram ID",
    "Username",
    "Язык",
    "Категория",
    "Имя",
    "Телефон",
    "Заявка",
    "Фото",
    "Файлы",
    "Локация",
    "Время связи",
    "Менеджер",
    "Комментарий",
    "Дата обработки",
]

START_CALLBACK = "start_form"
CANCEL_CALLBACK = "cancel_form"
SKIP_MEDIA_CALLBACK = "skip_media"
SKIP_LOCATION_CALLBACK = "skip_location"
CONFIRM_CALLBACK = "confirm_form"
RESTART_CALLBACK = "restart_form"

CATEGORIES = ["Заказ", "Покупка", "Консультация", "Доставка", "Возврат"]
CONTACT_TIMES = ["Сейчас", "Сегодня", "Завтра", "Указать время"]
STATUSES = ["Новая", "В работе", "Готово", "Отмена"]
LANGUAGES = {
    "ru": "Русский",
    "kk": "Қазақша",
    "en": "English",
}


def csv_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def admin_ids() -> set[int]:
    ids = set()
    for item in csv_env("ADMIN_CHAT_IDS"):
        try:
            ids.add(int(item))
        except ValueError:
            logging.warning("Invalid ADMIN_CHAT_IDS item: %s", item)
    return ids


def blacklist_ids() -> set[int]:
    ids = set()
    for item in csv_env("BLACKLIST_IDS"):
        try:
            ids.add(int(item))
        except ValueError:
            logging.warning("Invalid BLACKLIST_IDS item: %s", item)
    return ids


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in admin_ids())


def is_blacklisted(user_id: int | None) -> bool:
    return bool(user_id and user_id in blacklist_ids())


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Старт", callback_data=START_CALLBACK)],
        [
            InlineKeyboardButton("Мои заявки", callback_data="my_requests"),
            InlineKeyboardButton("Контакты", callback_data="contacts"),
        ],
        [InlineKeyboardButton("Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(rows)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"lang|{code}")] for code, label in LANGUAGES.items()]
        + [[InlineKeyboardButton("Отменить", callback_data=CANCEL_CALLBACK)]]
    )


def category_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"category|{name}")] for name in CATEGORIES]
    rows.append([InlineKeyboardButton("Отменить", callback_data=CANCEL_CALLBACK)])
    return InlineKeyboardMarkup(rows)


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Отправить телефон", request_contact=True)], ["Отменить"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def media_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Далее", callback_data=SKIP_MEDIA_CALLBACK)],
            [InlineKeyboardButton("Отменить", callback_data=CANCEL_CALLBACK)],
        ]
    )


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Отправить локацию", request_location=True)], ["Пропустить", "Отменить"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def contact_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(value, callback_data=f"time|{value}")] for value in CONTACT_TIMES]
        + [[InlineKeyboardButton("Отменить", callback_data=CANCEL_CALLBACK)]]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Отправить заявку", callback_data=CONFIRM_CALLBACK)],
            [InlineKeyboardButton("Заполнить заново", callback_data=RESTART_CALLBACK)],
            [InlineKeyboardButton("Отменить", callback_data=CANCEL_CALLBACK)],
        ]
    )


def after_submit_keyboard(request_number: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Старт", callback_data=START_CALLBACK)]]
    whatsapp_url = os.getenv("WHATSAPP_URL")
    payment_url = os.getenv("PAYMENT_URL")
    if whatsapp_url:
        rows.append([InlineKeyboardButton("Написать в WhatsApp", url=whatsapp_url)])
    if payment_url:
        rows.append([InlineKeyboardButton("Оплата", url=payment_url)])
    rows.append([InlineKeyboardButton("Мои заявки", callback_data="my_requests")])
    return InlineKeyboardMarkup(rows)


def admin_status_keyboard(request_number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("В работе", callback_data=f"status|{request_number}|В работе"),
                InlineKeyboardButton("Готово", callback_data=f"status|{request_number}|Готово"),
            ],
            [InlineKeyboardButton("Отмена", callback_data=f"status|{request_number}|Отмена")],
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
        worksheet.update(f"A1:Q1", [HEADERS])

    return worksheet


def normalize_phone(text: str) -> str:
    return re.sub(r"[^\d+]", "", text.strip())


def is_valid_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    return 7 <= len(digits) <= 15


def next_request_number(worksheet) -> str:
    values = worksheet.col_values(1)
    numbers = []
    for value in values[1:]:
        match = re.search(r"\d+", value or "")
        if match:
            numbers.append(int(match.group(0)))
    next_number = (max(numbers) + 1) if numbers else 1001
    return f"#{next_number}"


def find_request_row(worksheet, request_number: str) -> tuple[int | None, list[str] | None]:
    for index, row in enumerate(worksheet.get_all_values(), start=1):
        if row and row[0] == request_number:
            return index, row
    return None, None


def get_all_rows() -> list[list[str]]:
    worksheet = get_worksheet()
    return worksheet.get_all_values()[1:]


def request_summary(data: dict) -> str:
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"<b>Язык:</b> {html.escape(data.get('language_label', ''))}\n"
        f"<b>Категория:</b> {html.escape(data.get('category', ''))}\n"
        f"<b>Имя:</b> {html.escape(data.get('name', ''))}\n"
        f"<b>Телефон:</b> {html.escape(data.get('phone', ''))}\n"
        f"<b>Заявка:</b> {html.escape(data.get('details', ''))}\n"
        f"<b>Фото:</b> {len(data.get('photos', []))}\n"
        f"<b>Файлы:</b> {len(data.get('documents', []))}\n"
        f"<b>Локация:</b> {html.escape(data.get('location', 'Не указана'))}\n"
        f"<b>Время связи:</b> {html.escape(data.get('contact_time', ''))}\n\n"
        "Если все верно, нажмите кнопку отправки."
    )


def build_row(request_number: str, update: Update, data: dict) -> list[str]:
    user = update.effective_user
    return [
        request_number,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Новая",
        str(user.id),
        user.username or "",
        data.get("language_label", ""),
        data.get("category", ""),
        data.get("name", ""),
        data.get("phone", ""),
        data.get("details", ""),
        "\n".join(data.get("photos", [])),
        "\n".join(data.get("documents", [])),
        data.get("location", ""),
        data.get("contact_time", ""),
        "",
        "",
        "",
    ]


def duplicate_count(user_id: int, data: dict) -> int:
    count = 0
    for row in get_all_rows():
        padded = row + [""] * (len(HEADERS) - len(row))
        same = (
            padded[3] == str(user_id)
            and padded[6] == data.get("category", "")
            and padded[8] == data.get("phone", "")
            and padded[9] == data.get("details", "")
        )
        if same:
            count += 1
    return count


async def send_main_menu(update: Update, text: str | None = None) -> int:
    message = text or (
        "<b>Бот заявок</b>\n\n"
        "Нажмите «Старт», чтобы запустить заявку."
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(message, reply_markup=main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(
            message,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
        await update.message.reply_text("Главное меню", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if is_blacklisted(update.effective_user.id):
        await update.callback_query.answer("Доступ ограничен.", show_alert=True)
        return ConversationHandler.END

    context.user_data.clear()
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "<b>Выберите язык</b>\n\nВыберите язык для заявки.",
        reply_markup=language_keyboard(),
        parse_mode="HTML",
    )
    return LANGUAGE


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    code = query.data.split("|", 1)[1]
    context.user_data["language"] = code
    context.user_data["language_label"] = LANGUAGES.get(code, "Русский")
    await query.edit_message_text(
        "<b>Категория заявки</b>\nВыберите подходящий вариант.",
        reply_markup=category_keyboard(),
        parse_mode="HTML",
    )
    return CATEGORY


async def set_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data.split("|", 1)[1]
    await query.edit_message_text(
        "<b>Шаг 1</b>\nКак вас зовут?",
        parse_mode="HTML",
    )
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if name.lower() == "отменить":
        return await cancel(update, context)
    if len(name) < 2:
        await update.message.reply_text("Напишите имя чуть подробнее.")
        return NAME

    context.user_data["name"] = name
    await update.message.reply_text(
        "<b>Шаг 2</b>\nОтправьте номер телефона кнопкой или напишите вручную.",
        reply_markup=phone_keyboard(),
        parse_mode="HTML",
    )
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text and update.message.text.lower() == "отменить":
        return await cancel(update, context)

    if update.message.contact and update.message.contact.phone_number:
        phone = normalize_phone(update.message.contact.phone_number)
    else:
        phone = normalize_phone(update.message.text or "")

    if not is_valid_phone(phone):
        await update.message.reply_text("Похоже, номер введен не полностью. Напишите телефон еще раз.")
        return PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text(
        "<b>Шаг 3</b>\nКратко опишите заявку.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
    return DETAILS


async def collect_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    details = update.message.text.strip()
    if len(details) < 3:
        await update.message.reply_text("Опишите заявку чуть подробнее.")
        return DETAILS

    context.user_data["details"] = details
    context.user_data["photos"] = []
    context.user_data["documents"] = []
    await update.message.reply_text(
        "<b>Фото или файл</b>\n"
        "Можно отправить фото товара, чек, PDF, договор или реквизиты. "
        "Если ничего нет, нажмите «Далее».",
        reply_markup=media_keyboard(),
        parse_mode="HTML",
    )
    return MEDIA


async def collect_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        context.user_data.setdefault("photos", []).append(update.message.photo[-1].file_id)
        await update.message.reply_text("Фото добавлено. Можно отправить еще или нажать «Далее».", reply_markup=media_keyboard())
        return MEDIA

    if update.message.document:
        doc = update.message.document
        label = f"{doc.file_name or 'document'} | {doc.file_id}"
        context.user_data.setdefault("documents", []).append(label)
        await update.message.reply_text("Файл добавлен. Можно отправить еще или нажать «Далее».", reply_markup=media_keyboard())
        return MEDIA

    await update.message.reply_text("Отправьте фото/файл или нажмите «Далее».", reply_markup=media_keyboard())
    return MEDIA


async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("<b>Локация</b>\nЕсли нужна доставка, отправьте локацию или адрес.", parse_mode="HTML")
    await query.message.reply_text(
        "Можно отправить локацию кнопкой, написать адрес текстом или пропустить.",
        reply_markup=location_keyboard(),
    )
    return LOCATION


async def collect_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text.lower() == "отменить":
        return await cancel(update, context)
    if text.lower() == "пропустить":
        context.user_data["location"] = ""
    elif update.message.location:
        loc = update.message.location
        context.user_data["location"] = f"{loc.latitude},{loc.longitude}"
    else:
        context.user_data["location"] = text

    await update.message.reply_text(
        "<b>Когда удобно связаться?</b>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
    await update.message.reply_text("Выберите время связи.", reply_markup=contact_time_keyboard())
    return CONTACT_TIME


async def set_contact_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split("|", 1)[1]
    if value == "Указать время":
        await query.edit_message_text("Напишите удобное время связи.")
        return CUSTOM_TIME

    context.user_data["contact_time"] = value
    await query.edit_message_text(request_summary(context.user_data), reply_markup=confirm_keyboard(), parse_mode="HTML")
    return CONFIRM


async def collect_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if len(value) < 2:
        await update.message.reply_text("Напишите время чуть подробнее.")
        return CUSTOM_TIME
    context.user_data["contact_time"] = value
    await update.message.reply_text(request_summary(context.user_data), reply_markup=confirm_keyboard(), parse_mode="HTML")
    return CONFIRM


async def notify_admins(bot: Bot, request_number: str, row: list[str]) -> None:
    admins = admin_ids()
    if not admins:
        return

    text = (
        f"<b>Новая заявка {html.escape(request_number)}</b>\n\n"
        f"<b>Категория:</b> {html.escape(row[6])}\n"
        f"<b>Имя:</b> {html.escape(row[7])}\n"
        f"<b>Телефон:</b> {html.escape(row[8])}\n"
        f"<b>Заявка:</b> {html.escape(row[9])}\n"
        f"<b>Время связи:</b> {html.escape(row[13])}"
    )
    for chat_id in admins:
        try:
            await bot.send_message(chat_id, text, reply_markup=admin_status_keyboard(request_number), parse_mode="HTML")
        except Exception:
            logging.exception("Failed to notify admin %s", chat_id)


async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        duplicate_total = duplicate_count(update.effective_user.id, context.user_data)
        if duplicate_total >= 2:
            await query.edit_message_text(
                "Похожая заявка уже отправлялась несколько раз. Мы не будем дублировать ее в таблице.",
                reply_markup=main_menu_keyboard(),
            )
            context.user_data.clear()
            return ConversationHandler.END

        worksheet = get_worksheet()
        request_number = next_request_number(worksheet)
        row = build_row(request_number, update, context.user_data)
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        await notify_admins(context.bot, request_number, row)
    except Exception:
        logging.exception("Failed to save lead")
        await query.edit_message_text(
            "Заявку не удалось сохранить. Попробуйте позже.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        f"<b>Заявка {html.escape(request_number)} принята.</b>\n"
        "Менеджер ответит в течение 15 минут.",
        reply_markup=after_submit_keyboard(request_number),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Заполнение отменено.", reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("Заполнение отменено.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Главное меню", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = os.getenv("CONTACTS_TEXT", "Контакты пока не настроены. Можно оставить заявку, и менеджер свяжется с вами.")
    await query.edit_message_text(text, reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Нажмите «Старт», заполните форму и подтвердите отправку. "
        "После этого заявка появится в таблице.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def show_my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    rows = [row + [""] * (len(HEADERS) - len(row)) for row in get_all_rows() if len(row) > 3 and row[3] == user_id]
    if not rows:
        await query.edit_message_text("У вас пока нет заявок.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    latest = rows[-5:]
    lines = ["<b>Ваши последние заявки</b>"]
    for row in latest:
        lines.append(f"{html.escape(row[0])} | {html.escape(row[2])} | {html.escape(row[6])}")
    await query.edit_message_text("\n".join(lines), reply_markup=main_menu_keyboard(), parse_mode="HTML")
    return ConversationHandler.END


async def admin_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("Недостаточно прав.", show_alert=True)
        return

    _, request_number, status = query.data.split("|", 2)
    worksheet = get_worksheet()
    row_index, _ = find_request_row(worksheet, request_number)
    if not row_index:
        await query.answer("Заявка не найдена.", show_alert=True)
        return

    manager = update.effective_user.full_name or str(update.effective_user.id)
    worksheet.update(f"C{row_index}:Q{row_index}", [[
        status,
        *worksheet.row_values(row_index)[3:14],
        manager,
        "",
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ]])
    await query.answer(f"Статус: {status}")
    await query.edit_message_reply_markup(reply_markup=admin_status_keyboard(request_number))


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Ваш Telegram ID: {update.effective_user.id}")


async def admin_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    rows = [row + [""] * (len(HEADERS) - len(row)) for row in get_all_rows()]
    if not rows:
        await update.message.reply_text("Заявок пока нет.")
        return
    row = rows[-1]
    await update.message.reply_text(
        f"{row[0]} | {row[2]}\n{row[6]}\n{row[7]} | {row[8]}\n{row[9]}"
    )


async def admin_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [row for row in get_all_rows() if len(row) > 1 and row[1].startswith(today)]
    await update.message.reply_text(f"Заявок сегодня: {len(rows)}")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    rows = [row + [""] * (len(HEADERS) - len(row)) for row in get_all_rows()]
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row[2]] = counts.get(row[2], 0) + 1
    text = "\n".join([f"{status}: {count}" for status, count in counts.items()])
    await update.message.reply_text(f"Всего заявок: {len(rows)}\n{text}")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    message = " ".join(context.args).strip()
    if not message:
        await update.message.reply_text("Использование: /broadcast текст рассылки")
        return
    user_ids = sorted({row[3] for row in get_all_rows() if len(row) > 3 and row[3].isdigit()})
    sent = 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(int(user_id), message)
            sent += 1
        except Exception:
            logging.exception("Broadcast failed for %s", user_id)
    await update.message.reply_text(f"Рассылка отправлена: {sent}")


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if is_blacklisted(update.effective_user.id):
        return ConversationHandler.END
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
            CallbackQueryHandler(choose_language, pattern=f"^{START_CALLBACK}$"),
        ],
        states={
            LANGUAGE: [CallbackQueryHandler(set_language, pattern=r"^lang\|")],
            CATEGORY: [CallbackQueryHandler(set_category, pattern=r"^category\|")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND, collect_phone)],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_details)],
            MEDIA: [
                MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, collect_media),
                CallbackQueryHandler(ask_location, pattern=f"^{SKIP_MEDIA_CALLBACK}$"),
            ],
            LOCATION: [MessageHandler((filters.TEXT | filters.LOCATION) & ~filters.COMMAND, collect_location)],
            CONTACT_TIME: [CallbackQueryHandler(set_contact_time, pattern=r"^time\|")],
            CUSTOM_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_custom_time)],
            CONFIRM: [
                CallbackQueryHandler(confirm_request, pattern=f"^{CONFIRM_CALLBACK}$"),
                CallbackQueryHandler(choose_language, pattern=f"^{RESTART_CALLBACK}$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern=f"^{CANCEL_CALLBACK}$"),
        ],
        allow_reentry=True,
    )

    application.add_handler(CallbackQueryHandler(admin_status_callback, pattern=r"^status\|"))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("last", admin_last))
    application.add_handler(CommandHandler("today", admin_today))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(conversation)
    application.add_handler(CallbackQueryHandler(show_my_requests, pattern="^my_requests$"))
    application.add_handler(CallbackQueryHandler(show_contacts, pattern="^contacts$"))
    application.add_handler(CallbackQueryHandler(show_help, pattern="^help$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
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
