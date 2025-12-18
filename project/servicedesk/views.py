import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
import logging
from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets

from project.servicedesk.event_handlers import handle_message_new
from project.servicedesk.serializers import GroupSerializer, UserSerializer


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
