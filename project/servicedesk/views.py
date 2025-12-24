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


from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from .models import Ticket, Message, Tag, VKGroup
import requests


def is_admin(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin)
def ticket_list(request):
    """Список обращений с фильтрами"""
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    assigned_filter = request.GET.get('assigned', '')
    search_query = request.GET.get('q', '')

    tickets = Ticket.objects.all().prefetch_related('tags')

    # Применяем фильтры
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    if priority_filter:
        tickets = tickets.filter(priority=priority_filter)
    if assigned_filter == 'me':
        tickets = tickets.filter(admin=request.user)
    elif assigned_filter == 'unassigned':
        tickets = tickets.filter(admin__isnull=True)

    # Поиск
    if search_query:
        tickets = tickets.filter(
            Q(ticket_id__icontains=search_query) |
            Q(user_name__icontains=search_query) |
            Q(subject__icontains=search_query) |
            Q(messages__text__icontains=search_query)
        ).distinct()

    # Пагинация
    paginator = Paginator(tickets.order_by('-updated_at'), 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_choices': Ticket.STATUS_CHOICES,
        'priority_choices': Ticket.PRIORITY_CHOICES,
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'assigned': assigned_filter,
            'q': search_query,
        },
        'unread_counts': get_unread_counts(),
    }
    return render(request, 'support/ticket_list.html', context)


@login_required
@user_passes_test(is_admin)
def ticket_detail(request, ticket_id):
    """Детальная страница обращения"""
    ticket = get_object_or_404(Ticket.objects.prefetch_related('tags', 'messages'), ticket_id=ticket_id)

    if request.method == 'POST':
        # Отправка ответа
        if 'response' in request.POST:
            response_text = request.POST.get('response', '').strip()

            if response_text:
                # Отправляем ответ через API ВКонтакте
                success = send_vk_message(
                    user_id=ticket.user_id,
                    text=response_text,
                    access_token=ticket.vk_group.access_token
                )

                if success:
                    # Сохраняем сообщение от администратора
                    Message.objects.create(
                        ticket=ticket,
                        text=response_text,
                        is_admin=True,
                        admin_author=request.user,
                        is_read=True
                    )

                    # Обновляем статус обращения
                    ticket.status = 'answered'
                    ticket.admin = request.user
                    ticket.updated_at = timezone.now()
                    ticket.save()

                    messages.success(request, 'Ответ успешно отправлен')
                else:
                    messages.error(request, 'Ошибка при отправке ответа')

        # Обновление статуса
        elif 'status' in request.POST:
            new_status = request.POST.get('status')
            if new_status and new_status != ticket.status:
                ticket.status = new_status
                if new_status == 'closed':
                    ticket.closed_at = timezone.now()
                ticket.save()
                messages.success(request, 'Статус обновлен')

        # Назначение на себя
        elif 'assign_to_me' in request.POST:
            ticket.admin = request.user
            ticket.save()
            messages.success(request, 'Обращение назначено на вас')

        # Обновление тегов
        elif 'tags' in request.POST:
            tag_ids = request.POST.getlist('tags')
            ticket.tags.set(tag_ids)
            messages.success(request, 'Теги обновлены')

        # Обновление приоритета
        elif 'priority' in request.POST:
            new_priority = request.POST.get('priority')
            if new_priority:
                ticket.priority = new_priority
                ticket.save()
                messages.success(request, 'Приоритет обновлен')

    # Помечаем сообщения пользователя как прочитанные
    ticket.messages.filter(is_admin=False, is_read=False).update(is_read=True)

    context = {
        'ticket': ticket,
        'messages': ticket.messages.all(),
        'all_tags': Tag.objects.all(),
    }
    return render(request, 'support/ticket_detail.html', context)


@login_required
@user_passes_test(is_admin)
def bulk_action(request):
    """Массовые действия с обращениями"""
    if request.method == 'POST':
        ticket_ids = request.POST.getlist('ticket_ids')
        action = request.POST.get('action')

        if ticket_ids and action:
            tickets = Ticket.objects.filter(ticket_id__in=ticket_ids)

            if action == 'assign_to_me':
                tickets.update(admin=request.user)
                messages.success(request, f'Назначено {len(tickets)} обращений')
            elif action == 'change_status':
                new_status = request.POST.get('new_status')
                if new_status:
                    tickets.update(status=new_status)
                    if new_status == 'closed':
                        tickets.update(closed_at=timezone.now())
                    messages.success(request, f'Обновлен статус {len(tickets)} обращений')
            elif action == 'add_tag':
                tag_id = request.POST.get('tag_id')
                if tag_id:
                    tag = get_object_or_404(Tag, id=tag_id)
                    for ticket in tickets:
                        ticket.tags.add(tag)
                    messages.success(request, f'Добавлен тег к {len(tickets)} обращениям')

    return redirect('ticket_list')


def get_unread_counts():
    """Получение количества непрочитанных сообщений по статусам"""
    return {
        'open': Ticket.objects.filter(status='open').count(),
        'answered': Ticket.objects.filter(status='answered').count(),
        'waiting': Ticket.objects.filter(status='waiting').count(),
        'total_unread': Message.objects.filter(is_admin=False, is_read=False).count(),
    }


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