import json
import logging
from datetime import datetime

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import requests

from project import settings
from .models import VKMessage, VKGroup

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
    group_id = data['group_id']

    group = VKGroup.objects.get(group_id=group_id)

    # Получаем информацию об отправителе
    user_info = get_vk_user_info(message_data['from_id'], group.access_token)

    # Сохраняем сообщение
    VKMessage.objects.create(
        message_id=message_data['id'],
        from_id=message_data['from_id'],
        from_name=user_info.get('name', f'Пользователь {message_data["from_id"]}'),
        text=message_data.get('text', ''),
        attachments=message_data.get('attachments', []),
        date=datetime.fromtimestamp(message_data['date']),
        vk_group=group
    )

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


def get_vk_user_info(user_id, access_token):
    """Получение информации о пользователе ВКонтакте"""
    url = 'https://api.vk.com/method/users.get'
    params = {
        'user_ids': user_id,
        'access_token': access_token,
        'v': '5.131',
        'fields': 'first_name,last_name,photo_100'
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()
        if 'response' in data and len(data['response']) > 0:
            user = data['response'][0]
            return {
                'name': f"{user['first_name']} {user['last_name']}",
                'photo': user.get('photo_100')
            }
    except Exception as e:
        print(f"Error getting user info: {e}")

    return {'name': f'Пользователь {user_id}'}