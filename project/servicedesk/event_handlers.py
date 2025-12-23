import json
import logging
from datetime import datetime

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import requests

from project import settings
from .models import Message, VKGroup, Ticket

logger = logging.getLogger(__name__)


def handle_message_new(data):
    """
    Обработка нового сообщения
    """
    message_data = data['object']['message']
    group_id = data['group_id']

    group = VKGroup.objects.get(group_id=group_id)
    user_id = message_data['from_id']

    # Получаем информацию о пользователе
    user_info = get_vk_user_info(user_id, group.access_token)

    # Проверяем, есть ли активное обращение у пользователя
    # Ищем открытые или отвеченные обращения (не закрытые)
    active_ticket = Ticket.objects.filter(
        user_id=user_id,
        vk_group=group,
        status__in=['open', 'answered', 'waiting']
    ).order_by('-created_at').first()

    # Определяем тему обращения из первого сообщения
    if not active_ticket:
        subject = extract_subject(message_data.get('text', ''))
        # Создаем новое обращение
        active_ticket = Ticket.objects.create(
            user_id=user_id,
            user_name=user_info.get('name', f'Пользователь {user_id}'),
            user_photo=user_info.get('photo', ''),
            subject=subject,
            vk_group=group,
            status='open'
        )

    # Создаем сообщение
    Message.objects.create(
        ticket=active_ticket,
        message_id=message_data['id'],
        text=message_data.get('text', ''),
        attachments=message_data.get('attachments', []),
        is_admin=False,
        is_read=False
    )

    # Обновляем статус обращения
    if active_ticket.status == 'closed':
        active_ticket.status = 'open'
        active_ticket.closed_at = None
        active_ticket.save()
    elif active_ticket.status == 'answered':
        active_ticket.status = 'waiting'
        active_ticket.save()


def extract_subject(text):
    """Извлекает тему из текста сообщения"""
    if not text:
        return "Без темы"

    # Пытаемся найти тему в первых N символах
    first_line = text.split('\n')[0].strip()
    if len(first_line) > 100:
        return first_line[:97] + "..."
    return first_line if first_line else "Без темы"


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
