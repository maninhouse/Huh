# -*- coding: utf-8 -*-
import errno
import os
import sys
import logging
import tempfile
from flask import Flask, request, abort
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    AudioMessageContent,
    UserSource
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage
)
from io import BytesIO
from pydub import AudioSegment
from openai import OpenAI

app = Flask(__name__)

openai_api_key = os.getenv('OPENAI_API_KEY')

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None or channel_access_token is None:
    print('Specify LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN as environment variables.')
    sys.exit(1)

handler = WebhookHandler(channel_secret)

static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

configuration = Configuration(
    access_token=channel_access_token
)

# function for create tmp dir for download content
def make_static_tmp_dir():
    try:
        os.makedirs(static_tmp_path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(static_tmp_path):
            pass
        else:
            raise

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except ApiException as e:
        app.logger.warn("Got exception from LINE Messaging API: %s\n" % e.body)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=AudioMessageContent)
def handle_content_message(event):
    if isinstance(event.message, AudioMessageContent):
        ext = 'm4a'
    else:
        return

    user_id = event.source.user_id

    result_content = ''
    try:
        with ApiClient(configuration) as api_client:
            line_bot_blob_api = MessagingApiBlob(api_client)
            message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)

            # 讀取 M4A 檔案
            audio = AudioSegment.from_file(BytesIO(message_content), format="m4a")

            client = OpenAI(api_key=openai_api_key)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as temp:
                audio.export(temp.name, format="wav")
                temp.seek(0)
                audio_file = open(temp.name, "rb")
                transcript = client.audio.transcriptions.create(
                  model="whisper-1",
                  file=audio_file,
                  response_format="text",
                )
                result_content = f'{transcript}'

    except Exception as e:
        result_content += f'出現了一些錯誤，請稍後再試\n【{e}】'


    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text=result_content.strip('\n').strip(' '))
                ]
            )
        )