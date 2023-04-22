import requests
import csv
import os
from io import FileIO
from json import loads, dump
from flask import Flask, request
from telegram import Update, ParseMode, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from datetime import datetime
from threading import Thread

app = Flask('auth')

TELEGRAM_TOKEN = '5846418480:AAF0X1KlpmQz_Srj-oQfhgBWBCR71p3-jgY'
# ссылка, на которую будет перенаправлять бот для аунтефикации на гугл диске
# Чтобы изменить нужно добавить ссылку в консоли разработчика google
REDIRECT_URI = 'http://localhost:5000/'

# Консоль разработчика google
CLIENT_ID = '137149159399-mb30j804ik650qhpb2artqqbe1uuj9rq.apps.googleusercontent.com'
CLIENT_SECRET = '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'


@app.route('/')
def index():
    code = request.args.get('code')
    return f'''
        <!DOCTYPE html>
<html>
    <head>
        <title>Успешно!</title>
        <style>
            #container {"""{
                width: 0 auto;
                margin: 0 auto;
                text-align: center;
                }"""
    }
            #auth-code {"{font-weight: bold;}"}
        </style>
        <script>
            function clip_text(a_string) {"""{
                var input = document.createElement('input');
                input.id = "__copyText__";
                input.value = a_string;
                document.body.appendChild(input);
                input.select();
                document.execCommand("copy");
                var txt = input.value;
                input.remove();
                console.log("OK COPIED: '" + txt + "'");
            }"""
    }
        </script>
    </head>
    <body>
        <div id="container">
            <h2>Вы успешно авторизованы</h2>
            <p>Отправьте Ваш одноразоый код авторизации боту:</p>
            <span id="auth-code">/auth {code}</span>
            <button onClick="clip_text(document.getElementById('auth-code').innerHTML)">Скопировать</button>
        </div>
    </body>
</html>
'''


def load_users(file):
    with open(file) as f:
        f = f.read()
        if f:
            return loads(f)
    return {}


user_credentials = load_users('auth_users.txt')


# Функция для аутентификации пользователя в Google Диске
def authenticate(update: Update, context):
    user_id = update.message.from_user.id
    print(user_id, list(user_credentials.keys()))
    print(str(user_id) in list(user_credentials.keys()))
    if str(user_id) in list(user_credentials.keys()):
        # Пользователь уже аутентифицирован
        return build('drive', 'v3', credentials=Credentials.from_authorized_user_info(
            info=user_credentials[str(user_id)]))
    else:
        # Пользователь еще не аутентифицирован
        auth_url = f'''https://accounts.google.com/o/oauth2/auth?client_id={CLIENT_ID}&redirect_uri={
        REDIRECT_URI}&scope=https://www.googleapis.com/auth/drive.file&response_type=code&access_type=offline&prompt=consent'''

        update.message.reply_text(
            f'Пожалуйста, перейдите по [ссылкe]({auth_url}) для аутентификации и введите ваш код /auth \\[код\\]',
            parse_mode=ParseMode.MARKDOWN_V2)
        return


# Функция для обработки команды /start
def start(update: Update, context):
    update.message.reply_text('Привет! Я бот для работы с Google Диском. Введите /help для получения списка команд.')
    authenticate(update, context)


# Функция для обработки команды /help
def help(update: Update, context):
    update.message.reply_text(f'Список доступных команд:\n' +
                              '/auth - ввести код аунтефикации\n' +
                              '/list - показать список файлов на Google Диске\n' +
                              '/delete - удалить файл с Google Диска\n' +
                              '/mkdir - создать папку на Google Диске\n' +
                              '/move - переместить файл между папками\n' +
                              '/search - выполнить поиск файла на Google Диске\n' +
                              '/download - скачать файл с Google Диска\n' +
                              '/copy - создать копию файла на Google Диске\n\n' +
                              'Отправьте файл боту для загрузки на Google Диск')


# Функция для обработки сообщений с медиафайлами
def handle_media(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return
    message = update.message

    # Определение типа сообщения и соответствующих параметров
    if message.photo:
        now = datetime.now()
        file_name = f'Фото_{now.strftime("%Y-%m-%d_%H-%M-%S")}.jpg'
        file_path = f'images/{file_name}'
        file_id = message.photo[-1].file_id
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name
        file_path = f'videos/{file_name}'
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name
        file_path = f'audios/{file_name}'
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_path = f'documents/{file_name}'

    # Загрузка файла из сообщения
    file = context.bot.get_file(file_id)
    file.download(file_path)
    file_metadata = {'name': file_name}
    media = MediaFileUpload(file_path)
    file = service.files().create(body=file_metadata,
                                  media_body=media,
                                  fields='id').execute()

    update.message.reply_text(f'Файл {file_name} загружен на Google Диск. ID файла: <code>{file.get("id")}</code>',
                              parse_mode='HTML')

    update.message.reply_text(f'[Ссылка на файл](https://drive.google.com/file/d/{file.get("id")}/view?usp=share_link)',
                              parse_mode=ParseMode.MARKDOWN_V2)


# Функция для обработки команды /list
def list_files(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    results = service.files().list(
        pageSize=10, fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        update.message.reply_text('На вашем Google Диске нет файлов.')
    else:
        update.message.reply_text('Файлы:')
        for item in items:
            update.message.reply_text(f'{item["name"]}\n' +
                                      f'ID <code>{item["id"]}</code>',
                                      parse_mode='HTML')


# Функция для обработки команды /delete
def delete(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    if len(context.args) == 0:
        update.message.reply_text('Пожалуйста, укажите ID файла для удаления.')
        return

    file_id = context.args[0]
    try:
        service.files().delete(fileId=file_id).execute()
        update.message.reply_text(f'Файл с ID `{file_id}` удален с Google Диска\\.',
                                  parse_mode=ParseMode.MARKDOWN_V2)
    except HttpError as error:
        update.message.reply_text(f'Произошла ошибка: {error}')


# Функция для обработки команды /mkdir
def mkdir(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    if len(context.args) == 0:
        update.message.reply_text('Пожалуйста, укажите имя папки для создания.')
        return

    folder_name = ' '.join(context.args)
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata,
                                  fields='id').execute()
    update.message.reply_text(f'Папка "{folder_name}" создана на Google Диске. ID <code>{file.get("id")}</code>',
                              parse_mode='HTML')


# Функция для обработки команды /move
def move(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    if len(context.args) < 2:
        update.message.reply_text('Правильное использование команды /move [ID файла] [ID папки].')
        return

    file_id = context.args[0]
    folder_id = context.args[1]

    # Получаем текущую папку файла
    file = service.files().get(fileId=file_id,
                               fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))
    # Перемещаем файл в новую папку
    file = service.files().update(fileId=file_id,
                                  addParents=folder_id,
                                  removeParents=previous_parents,
                                  fields='id, parents').execute()
    update.message.reply_text(f'Файл с ID `{file_id}` перемещен в папку с ID `{folder_id}`',
                              parse_mode=ParseMode.MARKDOWN_V2)


# Функция для обработки команды /search
def search(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    if len(context.args) == 0:
        update.message.reply_text('Пожалуйста, укажите имя файла для поиска.')
        return

    query = ' '.join(context.args)
    results = service.files().list(q=f"name contains '{query}'",
                                   spaces='drive',
                                   fields='nextPageToken, files(id, name)').execute()
    items = results.get('files', [])

    if not items:
        update.message.reply_text(f'Файлы с именем "{query}" не найдены на вашем Google Диске.')
    else:
        update.message.reply_text(f'Найденные файлы:')
        for item in items:
            update.message.reply_text(f'{item["name"]}\n' +
                                      f'ID <code>{item["id"]}</code>',
                                      parse_mode='HTML')


# Функция для обработки команды /download
def download(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    if len(context.args) == 0:
        update.message.reply_text('Правильное использование команды /download [ID файла].')
        return

    file_id = context.args[0]
    file = service.files().get(fileId=file_id).execute()
    file_name = file['name']
    request = service.files().get_media(fileId=file_id)
    fh = FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f'Download {int(status.progress() * 100)}%')

    update.message.reply_document(open(file_name, 'rb'),
                                  filename=file_name)


# Функция для обработки команды /copy
def copy(update: Update, context):
    service = authenticate(update, context)
    if service is None:
        return

    if len(context.args) == 0:
        update.message.reply_text('Правильное использование команды /copy [ID файла]')
        return

    file_id = context.args[0]
    file = service.files().get(fileId=file_id).execute()
    file_name = file['name']
    copied_file = {'name': f'Копия {file_name}'}
    file = service.files().copy(fileId=file_id,
                                body=copied_file).execute()

    update.message.reply_text(
        f'Создана копия файла "{file_name}" на Google Диске.\n' +
        f'ID копии: <code>{file.get("id")}</code>',
        parse_mode='HTML')


# Функция для обработки команды /auth
def auth(update: Update, context):
    global user_credentials

    if len(context.args) == 0:
        update.message.reply_text('Пожалуйста, укажите код аутентификации /auth [код]')
        return

    user_id = update.message.from_user.id
    auth_code = context.args[0]

    data = {
        'code': auth_code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    response = requests.post('https://accounts.google.com/o/oauth2/token', data=data)
    response_data = response.json()
    print(data, response_data)

    refresh_token = response_data['refresh_token']
    inf = {
        'code': auth_code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
        'redirect_uris': [REDIRECT_URI],
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'refresh_token': refresh_token
    }

    user_credentials[str(user_id)] = inf
    with open('auth_users.txt', 'w') as f:
        dump(user_credentials, f)

    update.message.reply_text('Вы успешно авторизовались в Google Диске.')


def main():
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('help', help))
    dispatcher.add_handler(CommandHandler('list', list_files))
    dispatcher.add_handler(CommandHandler('delete', delete))
    dispatcher.add_handler(CommandHandler('mkdir', mkdir))
    dispatcher.add_handler(CommandHandler('move', move))
    dispatcher.add_handler(CommandHandler('search', search))
    dispatcher.add_handler(CommandHandler('download', download))
    dispatcher.add_handler(CommandHandler('copy', copy))
    dispatcher.add_handler(CommandHandler('auth', auth))

    updater.dispatcher.add_handler(
        MessageHandler(
            Filters.photo |
            Filters.video |
            Filters.audio |
            Filters.document,
            handle_media)
    )

    commands = [
        BotCommand("start", "запустить бота"),
        BotCommand("help", "получить список доступных команд"),
        BotCommand("list", "показать список файлов на Google Диске"),
        BotCommand("delete", "удалить файл с Google Диска"),
        BotCommand("mkdir", "создать папку на Google Диске"),
        BotCommand("move", "переместить файл между папками"),
        BotCommand("search", "выполнить поиск файла на Google Диске"),
        BotCommand("download", "скачать файл с Google Диска"),
        BotCommand("copy", "создать копию файла на Google Диске"),
        BotCommand("auth", "ввести код аутентификации")
    ]

    updater.bot.set_my_commands(commands)

    updater.start_polling()


if __name__ == '__main__':
    PYG = Thread(target=main)
    PYG.start()
    app.run()