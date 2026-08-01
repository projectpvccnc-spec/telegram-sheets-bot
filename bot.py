import asyncio
import html
import io
import json
import logging
import os
import re
from datetime import datetime, timezone

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build as gdrive_build
from googleapiclient.http import MediaIoBaseUpload
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
CONFIRM_CALLBACK = "confirm_form"
RESTART_CALLBACK = "restart_form"

STATUSES = ["Новая", "В работе", "Готово", "Отмена"]
LANGUAGES = {
    "ru": "Русский",
    "kk": "Қазақша",
    "en": "English",
}

# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

TRANSLATIONS: dict[str, dict] = {
    "ru": {
        "main_menu_text": "<b>Бот заявок</b>\n\nНажмите «Старт», чтобы запустить заявку.",
        "btn_start": "Старт",
        "btn_my_requests": "Мои заявки",
        "btn_contacts": "Контакты",
        "btn_help": "Помощь",
        "btn_cancel": "Отменить",
        "btn_next": "Далее",
        "btn_share_phone": "Отправить телефон",
        "btn_share_location": "Отправить локацию",
        "btn_skip": "Пропустить",
        "btn_submit": "Отправить заявку",
        "btn_restart": "Заполнить заново",
        "btn_whatsapp": "Написать в WhatsApp",
        "btn_payment": "Оплата",
        "btn_in_progress": "В работе",
        "btn_done": "Готово",
        "btn_cancelled_status": "Отмена",
        "choose_language": "<b>Выберите язык</b>\n\nВыберите язык для заявки.",
        "choose_category": "<b>Категория заявки</b>\nВыберите подходящий вариант.",
        "step_name": "<b>Шаг 1</b>\nКак вас зовут?",
        "step_phone": "<b>Шаг 2</b>\nОтправьте номер телефона кнопкой или напишите вручную.",
        "step_details": "<b>Шаг 3</b>\nКратко опишите заявку.",
        "step_media": (
            "<b>Фото или файл</b>\n"
            "Можно отправить фото товара, чек, PDF, договор или реквизиты. "
            "Если ничего нет, нажмите «Далее»."
        ),
        "step_location": "<b>Локация</b>\nЕсли нужна доставка, отправьте локацию или адрес.",
        "step_location_hint": "Можно отправить локацию кнопкой, написать адрес текстом или пропустить.",
        "step_contact_time": "<b>Когда удобно связаться?</b>",
        "step_contact_time_hint": "Выберите время связи.",
        "step_custom_time": "Напишите удобное время связи.",
        "name_too_short": "Напишите имя чуть подробнее.",
        "phone_invalid": "Похоже, номер введен не полностью. Напишите телефон еще раз.",
        "details_too_short": "Опишите заявку чуть подробнее.",
        "time_too_short": "Напишите время чуть подробнее.",
        "media_photo_added": "Фото добавлено. Можно отправить еще или нажать «Далее».",
        "media_doc_added": "Файл добавлен. Можно отправить еще или нажать «Далее».",
        "media_hint": "Отправьте фото/файл или нажмите «Далее».",
        "cancelled": "Заполнение отменено.",
        "main_menu_label": "Главное меню",
        "no_requests": "У вас пока нет заявок.",
        "my_requests_title": "<b>Ваши последние заявки</b>",
        "help_text": (
            "Нажмите «Старт», заполните форму и подтвердите отправку. "
            "После этого заявка появится в таблице."
        ),
        "duplicate_warning": (
            "Похожая заявка уже отправлялась несколько раз. "
            "Мы не будем дублировать ее в таблице."
        ),
        "save_error": "Заявку не удалось сохранить. Попробуйте позже.",
        "request_accepted": "<b>Заявка {} принята.</b>\nМенеджер ответит в течение 15 минут.",
        "blacklisted": "Доступ ограничен.",
        "summary_title": "<b>Проверьте заявку</b>\n\n",
        "summary_language": "<b>Язык:</b> {}",
        "summary_category": "<b>Категория:</b> {}",
        "summary_name": "<b>Имя:</b> {}",
        "summary_phone": "<b>Телефон:</b> {}",
        "summary_details": "<b>Заявка:</b> {}",
        "summary_photos": "<b>Фото:</b> {}",
        "summary_files": "<b>Файлы:</b> {}",
        "summary_location": "<b>Локация:</b> {}",
        "summary_location_none": "Не указана",
        "summary_contact_time": "<b>Время связи:</b> {}",
        "summary_footer": "\n\nЕсли все верно, нажмите кнопку отправки.",
        "contacts_default": (
            "Контакты пока не настроены. "
            "Можно оставить заявку, и менеджер свяжется с вами."
        ),
        "categories": ["Заказ", "Покупка", "Консультация", "Доставка", "Возврат"],
        "contact_times": ["Сейчас", "Сегодня", "Завтра", "Указать время"],
        "contact_time_custom": "Указать время",
    },
    "kk": {
        "main_menu_text": "<b>Өтінім боты</b>\n\nӨтінім беру үшін «Бастау» батырмасын басыңыз.",
        "btn_start": "Бастау",
        "btn_my_requests": "Менің өтінімдерім",
        "btn_contacts": "Байланыс",
        "btn_help": "Көмек",
        "btn_cancel": "Болдырмау",
        "btn_next": "Келесі",
        "btn_share_phone": "Телефон жіберу",
        "btn_share_location": "Орын жіберу",
        "btn_skip": "Өткізу",
        "btn_submit": "Өтінім жіберу",
        "btn_restart": "Қайта толтыру",
        "btn_whatsapp": "WhatsApp-қа жазу",
        "btn_payment": "Төлем",
        "btn_in_progress": "Жұмыста",
        "btn_done": "Дайын",
        "btn_cancelled_status": "Болдырылмады",
        "choose_language": "<b>Тілді таңдаңыз</b>\n\nӨтінім үшін тілді таңдаңыз.",
        "choose_category": "<b>Өтінім санаты</b>\nҚолайлы нұсқаны таңдаңыз.",
        "step_name": "<b>1-қадам</b>\nАтыңыз кім?",
        "step_phone": "<b>2-қадам</b>\nТелефон нөміріңізді батырма арқылы жіберіңіз немесе қолмен жазыңыз.",
        "step_details": "<b>3-қадам</b>\nӨтінімді қысқаша сипаттаңыз.",
        "step_media": (
            "<b>Фото немесе файл</b>\n"
            "Тауар фотосын, чекті, PDF, шарт немесе деректемелерді жіберуге болады. "
            "Ештеңе жоқ болса, «Келесі» батырмасын басыңыз."
        ),
        "step_location": "<b>Орналасу</b>\nЖеткізу қажет болса, орынды немесе мекенжайды жіберіңіз.",
        "step_location_hint": "Батырма арқылы орынды жіберуге, мекенжайды мәтінмен жазуға немесе өткізуге болады.",
        "step_contact_time": "<b>Байланысу үшін ыңғайлы уақыт?</b>",
        "step_contact_time_hint": "Байланысу уақытын таңдаңыз.",
        "step_custom_time": "Ыңғайлы байланысу уақытын жазыңыз.",
        "name_too_short": "Атыңызды толығырақ жазыңыз.",
        "phone_invalid": "Нөмір толық емес сияқты. Телефонды қайта енгізіңіз.",
        "details_too_short": "Өтінімді толығырақ сипаттаңыз.",
        "time_too_short": "Уақытты толығырақ жазыңыз.",
        "media_photo_added": "Фото қосылды. Тағы жіберуге немесе «Келесі» батырмасын басуға болады.",
        "media_doc_added": "Файл қосылды. Тағы жіберуге немесе «Келесі» батырмасын басуға болады.",
        "media_hint": "Фото/файл жіберіңіз немесе «Келесі» батырмасын басыңыз.",
        "cancelled": "Толтыру тоқтатылды.",
        "main_menu_label": "Басты мәзір",
        "no_requests": "Сізде әлі өтінім жоқ.",
        "my_requests_title": "<b>Соңғы өтінімдеріңіз</b>",
        "help_text": (
            "«Бастау» батырмасын басып, пішінді толтырып, жіберуді растаңыз. "
            "Осыдан кейін өтінім кестеде пайда болады."
        ),
        "duplicate_warning": (
            "Ұқсас өтінім бірнеше рет жіберілді. "
            "Біз оны кестеде қайталамаймыз."
        ),
        "save_error": "Өтінімді сақтау мүмкін болмады. Кейінірек қайталаңыз.",
        "request_accepted": "<b>Өтінім {} қабылданды.</b>\nМенеджер 15 минут ішінде жауап береді.",
        "blacklisted": "Қатынас шектелген.",
        "summary_title": "<b>Өтінімді тексеріңіз</b>\n\n",
        "summary_language": "<b>Тіл:</b> {}",
        "summary_category": "<b>Санат:</b> {}",
        "summary_name": "<b>Аты:</b> {}",
        "summary_phone": "<b>Телефон:</b> {}",
        "summary_details": "<b>Өтінім:</b> {}",
        "summary_photos": "<b>Фото:</b> {}",
        "summary_files": "<b>Файлдар:</b> {}",
        "summary_location": "<b>Орналасу:</b> {}",
        "summary_location_none": "Көрсетілмеген",
        "summary_contact_time": "<b>Байланысу уақыты:</b> {}",
        "summary_footer": "\n\nБарлығы дұрыс болса, жіберу батырмасын басыңыз.",
        "contacts_default": (
            "Байланыс деректері әлі баптанбаған. "
            "Өтінім қалдырыңыз, менеджер сізбен байланысады."
        ),
        "categories": ["Тапсырыс", "Сатып алу", "Кеңес", "Жеткізу", "Қайтару"],
        "contact_times": ["Қазір", "Бүгін", "Ертең", "Уақытты көрсету"],
        "contact_time_custom": "Уақытты көрсету",
    },
    "en": {
        "main_menu_text": "<b>Request Bot</b>\n\nPress «Start» to create a request.",
        "btn_start": "Start",
        "btn_my_requests": "My Requests",
        "btn_contacts": "Contacts",
        "btn_help": "Help",
        "btn_cancel": "Cancel",
        "btn_next": "Next",
        "btn_share_phone": "Share Phone",
        "btn_share_location": "Share Location",
        "btn_skip": "Skip",
        "btn_submit": "Submit Request",
        "btn_restart": "Fill Again",
        "btn_whatsapp": "Write on WhatsApp",
        "btn_payment": "Payment",
        "btn_in_progress": "In Progress",
        "btn_done": "Done",
        "btn_cancelled_status": "Cancelled",
        "choose_language": "<b>Choose Language</b>\n\nSelect the language for your request.",
        "choose_category": "<b>Request Category</b>\nChoose the appropriate option.",
        "step_name": "<b>Step 1</b>\nWhat is your name?",
        "step_phone": "<b>Step 2</b>\nShare your phone number using the button or type it manually.",
        "step_details": "<b>Step 3</b>\nBriefly describe your request.",
        "step_media": (
            "<b>Photo or File</b>\n"
            "You can send a product photo, receipt, PDF, contract or bank details. "
            "If you have none, press «Next»."
        ),
        "step_location": "<b>Location</b>\nIf delivery is needed, share your location or address.",
        "step_location_hint": "You can share location via button, type an address or skip.",
        "step_contact_time": "<b>When is convenient to contact you?</b>",
        "step_contact_time_hint": "Choose a contact time.",
        "step_custom_time": "Please write a convenient time to contact you.",
        "name_too_short": "Please write your name in a bit more detail.",
        "phone_invalid": "The number seems incomplete. Please enter the phone again.",
        "details_too_short": "Please describe the request in a bit more detail.",
        "time_too_short": "Please write the time in a bit more detail.",
        "media_photo_added": "Photo added. You can send more or press «Next».",
        "media_doc_added": "File added. You can send more or press «Next».",
        "media_hint": "Send a photo/file or press «Next».",
        "cancelled": "Request cancelled.",
        "main_menu_label": "Main Menu",
        "no_requests": "You have no requests yet.",
        "my_requests_title": "<b>Your recent requests</b>",
        "help_text": (
            "Press «Start», fill out the form and confirm submission. "
            "After that, the request will appear in the spreadsheet."
        ),
        "duplicate_warning": (
            "A similar request has already been submitted several times. "
            "We will not duplicate it in the table."
        ),
        "save_error": "Failed to save the request. Please try again later.",
        "request_accepted": "<b>Request {} accepted.</b>\nA manager will respond within 15 minutes.",
        "blacklisted": "Access restricted.",
        "summary_title": "<b>Review your request</b>\n\n",
        "summary_language": "<b>Language:</b> {}",
        "summary_category": "<b>Category:</b> {}",
        "summary_name": "<b>Name:</b> {}",
        "summary_phone": "<b>Phone:</b> {}",
        "summary_details": "<b>Request:</b> {}",
        "summary_photos": "<b>Photos:</b> {}",
        "summary_files": "<b>Files:</b> {}",
        "summary_location": "<b>Location:</b> {}",
        "summary_location_none": "Not specified",
        "summary_contact_time": "<b>Contact time:</b> {}",
        "summary_footer": "\n\nIf everything is correct, press the submit button.",
        "contacts_default": (
            "Contacts are not configured yet. "
            "You can leave a request and a manager will contact you."
        ),
        "categories": ["Order", "Purchase", "Consultation", "Delivery", "Return"],
        "contact_times": ["Now", "Today", "Tomorrow", "Specify time"],
        "contact_time_custom": "Specify time",
    },
}

# Canonical (Russian) lists — always stored in the sheet
_CATEGORIES_RU = TRANSLATIONS["ru"]["categories"]
_CONTACT_TIMES_RU = TRANSLATIONS["ru"]["contact_times"]
# Index of the "custom time" option (last element)
_CUSTOM_TIME_INDEX = len(_CONTACT_TIMES_RU) - 1


def t(lang: str, key: str, *args: object) -> str:
    """Return translated string for the given language and key."""
    tr = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
    value = tr.get(key, TRANSLATIONS["ru"].get(key, key))
    if args:
        return value.format(*args)
    return value


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


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t(lang, "btn_start"), callback_data=START_CALLBACK)],
        [
            InlineKeyboardButton(t(lang, "btn_my_requests"), callback_data="my_requests"),
            InlineKeyboardButton(t(lang, "btn_contacts"), callback_data="contacts"),
        ],
        [InlineKeyboardButton(t(lang, "btn_help"), callback_data="help")],
    ]
    return InlineKeyboardMarkup(rows)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"lang|{code}")] for code, label in LANGUAGES.items()]
        + [[InlineKeyboardButton(t("ru", "btn_cancel"), callback_data=CANCEL_CALLBACK)]]
    )


def category_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    categories = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])["categories"]
    rows = [[InlineKeyboardButton(name, callback_data=f"category|{i}")] for i, name in enumerate(categories)]
    rows.append([InlineKeyboardButton(t(lang, "btn_cancel"), callback_data=CANCEL_CALLBACK)])
    return InlineKeyboardMarkup(rows)


def phone_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t(lang, "btn_share_phone"), request_contact=True)], [t(lang, "btn_cancel")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def media_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "btn_next"), callback_data=SKIP_MEDIA_CALLBACK)],
            [InlineKeyboardButton(t(lang, "btn_cancel"), callback_data=CANCEL_CALLBACK)],
        ]
    )


def location_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(lang, "btn_share_location"), request_location=True)],
            [t(lang, "btn_skip"), t(lang, "btn_cancel")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def contact_time_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    times = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])["contact_times"]
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(value, callback_data=f"time|{i}")] for i, value in enumerate(times)]
        + [[InlineKeyboardButton(t(lang, "btn_cancel"), callback_data=CANCEL_CALLBACK)]]
    )


def confirm_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "btn_submit"), callback_data=CONFIRM_CALLBACK)],
            [InlineKeyboardButton(t(lang, "btn_restart"), callback_data=RESTART_CALLBACK)],
            [InlineKeyboardButton(t(lang, "btn_cancel"), callback_data=CANCEL_CALLBACK)],
        ]
    )


def after_submit_keyboard(request_number: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t(lang, "btn_start"), callback_data=START_CALLBACK)]]
    whatsapp_url = os.getenv("WHATSAPP_URL")
    payment_url = os.getenv("PAYMENT_URL")
    if whatsapp_url:
        rows.append([InlineKeyboardButton(t(lang, "btn_whatsapp"), url=whatsapp_url)])
    if payment_url:
        rows.append([InlineKeyboardButton(t(lang, "btn_payment"), url=payment_url)])
    rows.append([InlineKeyboardButton(t(lang, "btn_my_requests"), callback_data="my_requests")])
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


def _load_service_account_info() -> dict:
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        return json.loads(service_account_json)
    credentials_path = require_env("GOOGLE_APPLICATION_CREDENTIALS")
    with open(credentials_path) as fh:
        return json.load(fh)


def get_gspread_client():
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        return gspread.service_account_from_dict(_load_service_account_info())
    return gspread.service_account(filename=require_env("GOOGLE_APPLICATION_CREDENTIALS"))


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
        worksheet.update("A1:Q1", [HEADERS])

    return worksheet


async def upload_file_to_drive(bot: Bot, file_id: str, filename: str, mime_type: str) -> str | None:
    """Download a file from Telegram and upload it to Google Drive.

    Returns a public shareable URL on success, or None if the upload fails.
    If GOOGLE_DRIVE_FOLDER_ID is set, the file is placed in that folder.
    """
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    try:
        info = _load_service_account_info()
        creds = SACredentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = gdrive_build("drive", "v3", credentials=creds, cache_discovery=False)

        tg_file = await bot.get_file(file_id)
        buffer = io.BytesIO()
        await tg_file.download_to_memory(buffer)
        buffer.seek(0)

        file_metadata: dict = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaIoBaseUpload(buffer, mimetype=mime_type, resumable=False)
        created = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        ).execute()

        drive_file_id = created["id"]
        service.permissions().create(
            fileId=drive_file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return f"https://drive.google.com/file/d/{drive_file_id}/view"
    except Exception:
        logging.exception("Failed to upload file to Google Drive (file_id=%s)", file_id)
        return None


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


def request_summary(data: dict, lang: str = "ru") -> str:
    location = data.get("location") or t(lang, "summary_location_none")
    return (
        t(lang, "summary_title")
        + t(lang, "summary_language", html.escape(data.get("language_label", ""))) + "\n"
        + t(lang, "summary_category", html.escape(data.get("category_display", data.get("category", "")))) + "\n"
        + t(lang, "summary_name", html.escape(data.get("name", ""))) + "\n"
        + t(lang, "summary_phone", html.escape(data.get("phone", ""))) + "\n"
        + t(lang, "summary_details", html.escape(data.get("details", ""))) + "\n"
        + t(lang, "summary_photos", len(data.get("photos", []))) + "\n"
        + t(lang, "summary_files", len(data.get("documents", []))) + "\n"
        + t(lang, "summary_location", html.escape(location)) + "\n"
        + t(lang, "summary_contact_time", html.escape(data.get("contact_time_display", data.get("contact_time", ""))))
        + t(lang, "summary_footer")
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
        data.get("category", ""),          # canonical Russian name
        data.get("name", ""),
        data.get("phone", ""),
        data.get("details", ""),
        "\n".join(data.get("photos", [])),
        "\n".join(data.get("documents", [])),
        data.get("location", ""),
        data.get("contact_time", ""),      # canonical Russian name
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


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru") if context and context.user_data else "ru"
    message = t(lang, "main_menu_text")

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(message, reply_markup=main_menu_keyboard(lang), parse_mode="HTML")
    else:
        await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        await update.message.reply_text(t(lang, "main_menu_label"), reply_markup=main_menu_keyboard(lang))
    return ConversationHandler.END


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if is_blacklisted(update.effective_user.id):
        await update.callback_query.answer(t("ru", "blacklisted"), show_alert=True)
        return ConversationHandler.END

    context.user_data.clear()
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        t("ru", "choose_language"),
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
        t(code, "choose_category"),
        reply_markup=category_keyboard(code),
        parse_mode="HTML",
    )
    return CATEGORY


async def set_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("|", 1)[1])
    lang = context.user_data.get("language", "ru")
    context.user_data["category"] = _CATEGORIES_RU[index]
    context.user_data["category_display"] = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])["categories"][index]
    await query.edit_message_text(t(lang, "step_name"), parse_mode="HTML")
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    name = update.message.text.strip()
    if name.lower() == t(lang, "btn_cancel").lower():
        return await cancel(update, context)
    if len(name) < 2:
        await update.message.reply_text(t(lang, "name_too_short"))
        return NAME

    context.user_data["name"] = name
    await update.message.reply_text(
        t(lang, "step_phone"),
        reply_markup=phone_keyboard(lang),
        parse_mode="HTML",
    )
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    if update.message.text and update.message.text.lower() == t(lang, "btn_cancel").lower():
        return await cancel(update, context)

    if update.message.contact and update.message.contact.phone_number:
        phone = normalize_phone(update.message.contact.phone_number)
    else:
        phone = normalize_phone(update.message.text or "")

    if not is_valid_phone(phone):
        await update.message.reply_text(t(lang, "phone_invalid"))
        return PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text(
        t(lang, "step_details"),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
    return DETAILS


async def collect_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    details = update.message.text.strip()
    if len(details) < 3:
        await update.message.reply_text(t(lang, "details_too_short"))
        return DETAILS

    context.user_data["details"] = details
    context.user_data["photos"] = []
    context.user_data["documents"] = []
    await update.message.reply_text(
        t(lang, "step_media"),
        reply_markup=media_keyboard(lang),
        parse_mode="HTML",
    )
    return MEDIA


async def collect_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")

    if update.message.photo:
        photo = update.message.photo[-1]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        url = await upload_file_to_drive(context.bot, photo.file_id, f"photo_{ts}.jpg", "image/jpeg")
        entry = url if url else photo.file_id
        context.user_data.setdefault("photos", []).append(entry)
        await update.message.reply_text(t(lang, "media_photo_added"), reply_markup=media_keyboard(lang))
        return MEDIA

    if update.message.document:
        doc = update.message.document
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = doc.file_name or f"document_{ts}"
        mime = doc.mime_type or "application/octet-stream"
        url = await upload_file_to_drive(context.bot, doc.file_id, filename, mime)
        label_name = doc.file_name or "document"
        entry = f"{label_name} | {url}" if url else f"{label_name} | {doc.file_id}"
        context.user_data.setdefault("documents", []).append(entry)
        await update.message.reply_text(t(lang, "media_doc_added"), reply_markup=media_keyboard(lang))
        return MEDIA

    await update.message.reply_text(t(lang, "media_hint"), reply_markup=media_keyboard(lang))
    return MEDIA


async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t(lang, "step_location"), parse_mode="HTML")
    await query.message.reply_text(t(lang, "step_location_hint"), reply_markup=location_keyboard(lang))
    return LOCATION


async def collect_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    text = (update.message.text or "").strip()
    if text.lower() == t(lang, "btn_cancel").lower():
        return await cancel(update, context)
    if text.lower() == t(lang, "btn_skip").lower():
        context.user_data["location"] = ""
    elif update.message.location:
        loc = update.message.location
        context.user_data["location"] = f"{loc.latitude},{loc.longitude}"
    else:
        context.user_data["location"] = text

    await update.message.reply_text(
        t(lang, "step_contact_time"),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
    await update.message.reply_text(t(lang, "step_contact_time_hint"), reply_markup=contact_time_keyboard(lang))
    return CONTACT_TIME


async def set_contact_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("|", 1)[1])
    lang = context.user_data.get("language", "ru")

    if index == _CUSTOM_TIME_INDEX:
        await query.edit_message_text(t(lang, "step_custom_time"))
        return CUSTOM_TIME

    context.user_data["contact_time"] = _CONTACT_TIMES_RU[index]
    context.user_data["contact_time_display"] = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])["contact_times"][index]
    await query.edit_message_text(request_summary(context.user_data, lang), reply_markup=confirm_keyboard(lang), parse_mode="HTML")
    return CONFIRM


async def collect_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    value = update.message.text.strip()
    if len(value) < 2:
        await update.message.reply_text(t(lang, "time_too_short"))
        return CUSTOM_TIME
    context.user_data["contact_time"] = value
    context.user_data["contact_time_display"] = value
    await update.message.reply_text(request_summary(context.user_data, lang), reply_markup=confirm_keyboard(lang), parse_mode="HTML")
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
    lang = context.user_data.get("language", "ru")

    try:
        duplicate_total = duplicate_count(update.effective_user.id, context.user_data)
        if duplicate_total >= 2:
            await query.edit_message_text(
                t(lang, "duplicate_warning"),
                reply_markup=main_menu_keyboard(lang),
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
            t(lang, "save_error"),
            reply_markup=main_menu_keyboard(lang),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        t(lang, "request_accepted", html.escape(request_number)),
        reply_markup=after_submit_keyboard(request_number, lang),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru") if context and context.user_data else "ru"
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            t(lang, "cancelled"),
            reply_markup=main_menu_keyboard(lang),
        )
    else:
        await update.message.reply_text(t(lang, "cancelled"), reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(t(lang, "main_menu_label"), reply_markup=main_menu_keyboard(lang))
    return ConversationHandler.END


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    query = update.callback_query
    await query.answer()
    text = os.getenv("CONTACTS_TEXT") or t(lang, "contacts_default")
    await query.edit_message_text(text, reply_markup=main_menu_keyboard(lang))
    return ConversationHandler.END


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t(lang, "help_text"), reply_markup=main_menu_keyboard(lang))
    return ConversationHandler.END


async def show_my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("language", "ru")
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    rows = [row + [""] * (len(HEADERS) - len(row)) for row in get_all_rows() if len(row) > 3 and row[3] == user_id]
    if not rows:
        await query.edit_message_text(t(lang, "no_requests"), reply_markup=main_menu_keyboard(lang))
        return ConversationHandler.END

    latest = rows[-5:]
    lines = [t(lang, "my_requests_title")]
    for row in latest:
        lines.append(f"{html.escape(row[0])} | {html.escape(row[2])} | {html.escape(row[6])}")
    await query.edit_message_text("\n".join(lines), reply_markup=main_menu_keyboard(lang), parse_mode="HTML")
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
    return await send_main_menu(update, context)


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
