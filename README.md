# Telegram заявки -> Google Sheets

Telegram-бот, который собирает заявку по шагам и записывает ее в Google Sheets.

## Что умеет

- `/start` начинает новую заявку.
- Бот спрашивает имя, телефон и текст заявки.
- Данные сохраняются в Google Sheets.
- Пользователь получает подтверждение.
- На Render работает как Web Service через Telegram webhook.

## Локальный запуск

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
.\.venv\Scripts\python.exe bot.py
```

## Перезапуск на Windows

Если бот уже запущен в фоне, используй:

```powershell
.\restart-bot.ps1
```

Логи:

```text
bot.log
bot.err
```

## Переменные окружения

Для локального запуска:

```text
TELEGRAM_BOT_TOKEN=токен_из_BotFather
GOOGLE_APPLICATION_CREDENTIALS=service-account.json
GOOGLE_SPREADSHEET_ID=id_таблицы
GOOGLE_WORKSHEET_NAME=Заявки
```

Для Render вместо файла `service-account.json` используется переменная:

```text
GOOGLE_SERVICE_ACCOUNT_JSON={...полный JSON service account...}
```

Также Render должен получить публичный адрес сервиса:

```text
WEBHOOK_URL=https://your-render-service.onrender.com
```

## Деплой на Render

1. Создай новый **Web Service** на Render из этого GitHub-репозитория.
2. Runtime: `Python`.
3. Build Command:

```text
pip install -r requirements.txt
```

4. Start Command:

```text
uvicorn app:api --host 0.0.0.0 --port $PORT
```

5. Добавь Environment Variables:

```text
TELEGRAM_BOT_TOKEN
GOOGLE_SERVICE_ACCOUNT_JSON
WEBHOOK_URL
GOOGLE_SPREADSHEET_ID
GOOGLE_WORKSHEET_NAME
```

`render.yaml` уже содержит шаблон сервиса и обычные переменные.

## Google Sheets

Если лист пустой, бот сам добавит заголовки:

```text
Дата, Telegram ID, Username, Имя, Телефон, Заявка
```

Service account должен иметь доступ `Editor` к таблице.

## Команды бота

- `/start` - создать заявку
- `/cancel` - отменить заполнение
