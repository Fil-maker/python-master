import json
from datetime import datetime

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
import logging
from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets

from project.servicedesk.event_handlers import handle_message_new
from project.servicedesk.serializers import GroupSerializer, UserSerializer

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from .models import VKMessage
import requests


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


class GroupViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows groups to be viewed or edited.
    """

    queryset = Group.objects.all().order_by("name")
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]


logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def vk_callback(request):
    """
    Основной обработчик Callback API от VK
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        logger.info(f"Received VK callback data: {data}")

        # Проверка типа события
        event_type = data.get('type')

        # Обработка подтверждения сервера
        if event_type == 'confirmation':
            return HttpResponse(settings.VK_CALLBACK_API['CONFIRMATION_TOKEN'])

        # Проверка секретного ключа (если используется)
        if 'secret' in settings.VK_CALLBACK_API:
            if data.get('secret') != settings.VK_CALLBACK_API['SECRET_KEY']:
                return HttpResponse('Invalid secret', status=403)

        # Обработка разных типов событий
        handlers = {
            'message_new': handle_message_new,
        }

        handler = handlers.get(event_type)
        if handler:
            # Запускаем обработчик в фоне (можно использовать celery/dramatiq)
            handler.delay(data) if hasattr(handler, 'delay') else handler(data)

        # Всегда возвращаем 'ok' для VK
        return HttpResponse('ok')

    except json.JSONDecodeError:
        logger.error("Invalid JSON received")
        return HttpResponse('Invalid JSON', status=400)
    except Exception as e:
        logger.error(f"Error processing callback: {e}")
        return HttpResponse('error', status=500)


def is_admin(user):
    return user.is_staff


@login_required
@user_passes_test(is_admin)
def message_list(request):
    status_filter = request.GET.get('status', '')

    messages = VKMessage.objects.all()

    if status_filter:
        messages = messages.filter(status=status_filter)

    context = {
        'messages': messages,
        'status_choices': VKMessage.STATUS_CHOICES,
        'current_filter': status_filter
    }
    return render(request, 'support/message_list.html', context)


@login_required
@user_passes_test(is_admin)
def message_detail(request, message_id):
    message = get_object_or_404(VKMessage, id=message_id)

    if request.method == 'POST':
        response_text = request.POST.get('response', '').strip()

        if response_text:
            # Отправляем ответ через API ВКонтакте
            success = send_vk_message(
                user_id=message.from_id,
                text=response_text,
                access_token=message.vk_group.access_token
            )

            if success:
                message.response = response_text
                message.status = 'answered'
                message.admin = request.user
                message.response_date = datetime.now()
                message.save()
                messages.success(request, 'Ответ успешно отправлен')
            else:
                messages.error(request, 'Ошибка при отправке ответа')

        # Обновление статуса
        new_status = request.POST.get('status')
        if new_status and new_status != message.status:
            message.status = new_status
            message.save()
            messages.success(request, 'Статус обновлен')

    return render(request, 'support/message_detail.html', {'message': message})


def send_vk_message(user_id, text, access_token):
    """Отправка сообщения через API ВКонтакте"""
    url = 'https://api.vk.com/method/messages.send'

    params = {
        'user_id': user_id,
        'message': text,
        'access_token': access_token,
        'v': '5.131',
        'random_id': 0
    }

    try:
        response = requests.post(url, params=params)
        data = response.json()

        if 'error' in data:
            print(f"VK API Error: {data['error']}")
            return False

        return True
    except Exception as e:
        print(f"Error sending message: {e}")
        return False
