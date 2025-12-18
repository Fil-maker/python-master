import json
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import requests

from project import settings

logger = logging.getLogger(__name__)


def handle_message_new(data):
    """
    Обработка нового сообщения
    """
    message_data = data.get('object', {})
    message = message_data.get('message', {})

    user_id = message.get('from_id')
    text = message.get('text')
    message_id = message.get('id')
    peer_id = message.get('peer_id')

    # Логика обработки сообщения
    logger.info(f"New message from {user_id}: {text}")

    # Пример ответа
    if text.lower() == 'привет':
        send_message(user_id, "Привет! Как дела?")


def send_message(user_id, text, keyboard=None):
    """
    Отправка сообщения через VK API
    """
    url = "https://api.vk.com/method/messages.send"
    params = {
        'user_id': user_id,
        'message': text,
        'random_id': 0,
        'access_token': settings.VK_CALLBACK_API['ACCESS_TOKEN'],
        'v': '5.199'  # версия API
    }

    if keyboard:
        params['keyboard'] = json.dumps(keyboard)

    try:
        response = requests.post(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error sending message: {e}")
        return None
