import json
from datetime import datetime, timedelta
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.cache import cache
from .models import Ticket, Message, Tag, VKGroup


class SupportAppTests(TestCase):
    """Базовые настройки для всех тестов"""

    def setUp(self):
        """Настройка тестовых данных"""
        # Очищаем кэш перед каждым тестом
        cache.clear()

        # Создаем тестовых пользователей
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )

        self.regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='testpass123'
        )

        # Создаем тестовую группу ВК
        self.vk_group = VKGroup.objects.create(
            group_id=123456789,
            name='Test Group',
            access_token='test_access_token',
            secret_key='test_secret_key'
        )

        # Создаем теги
        self.tag_urgent = Tag.objects.create(name='Срочно', color='#ff0000')
        self.tag_bug = Tag.objects.create(name='Баг', color='#00ff00')
        self.tag_feature = Tag.objects.create(name='Функционал', color='#0000ff')

        # Создаем тестовые обращения
        self.ticket1 = Ticket.objects.create(
            ticket_id='20231201-0001',
            user_id=1001,
            user_name='Иван Иванов',
            user_photo='https://example.com/photo1.jpg',
            subject='Проблема с входом',
            status='open',
            priority='high',
            vk_group=self.vk_group,
            admin=self.admin_user
        )
        self.ticket1.tags.add(self.tag_urgent, self.tag_bug)

        self.ticket2 = Ticket.objects.create(
            ticket_id='20231201-0002',
            user_id=1002,
            user_name='Петр Петров',
            user_photo='https://example.com/photo2.jpg',
            subject='Вопрос по оплате',
            status='answered',
            priority='medium',
            vk_group=self.vk_group
        )

        self.ticket3 = Ticket.objects.create(
            ticket_id='20231201-0003',
            user_id=1003,
            user_name='Сидор Сидоров',
            subject='Предложение по улучшению',
            status='closed',
            priority='low',
            vk_group=self.vk_group,
            closed_at=timezone.now() - timedelta(days=1)
        )
        self.ticket3.tags.add(self.tag_feature)

        # Создаем тестовые сообщения
        Message.objects.create(
            ticket=self.ticket1,
            message_id=1,
            text='Здравствуйте, не могу войти в систему',
            is_admin=False,
            is_read=False
        )

        Message.objects.create(
            ticket=self.ticket1,
            text='Проверьте ваш логин и пароль',
            is_admin=True,
            admin_author=self.admin_user,
            is_read=True
        )

        Message.objects.create(
            ticket=self.ticket2,
            message_id=2,
            text='Когда будет пополнение баланса?',
            is_admin=False,
            is_read=True
        )

        # Клиент для тестирования
        self.client = Client()

    def tearDown(self):
        """Очистка после тестов"""
        cache.clear()


class ModelTests(SupportAppTests):
    """Тесты моделей"""

    def test_ticket_creation(self):
        """Тест создания обращения"""
        ticket = Ticket.objects.create(
            user_id=9999,
            user_name='Тестовый пользователь',
            subject='Тестовое обращение',
            vk_group=self.vk_group
        )

        self.assertIsNotNone(ticket.ticket_id)
        self.assertEqual(ticket.status, 'open')
        self.assertEqual(ticket.priority, 'medium')
        self.assertIsNotNone(ticket.created_at)
        self.assertIsNotNone(ticket.updated_at)
        self.assertIsNone(ticket.closed_at)

    def test_ticket_id_generation(self):
        """Тест генерации уникального ID обращения"""
        # Первый тикет уже создан в setUp
        ticket_count_before = Ticket.objects.count()

        # Создаем новый тикет
        new_ticket = Ticket.objects.create(
            user_id=9998,
            user_name='Еще один пользователь',
            vk_group=self.vk_group
        )

        # Проверяем, что ID сгенерирован
        self.assertIsNotNone(new_ticket.ticket_id)
        self.assertIn(timezone.now().strftime('%Y%m%d'), new_ticket.ticket_id)

        # Проверяем, что ID уникален
        tickets_with_same_id = Ticket.objects.filter(ticket_id=new_ticket.ticket_id)
        self.assertEqual(tickets_with_same_id.count(), 1)

    def test_ticket_unread_messages_count(self):
        """Тест подсчета непрочитанных сообщений"""
        # У ticket1 есть одно непрочитанное сообщение от пользователя
        self.assertEqual(self.ticket1.get_unread_messages_count(), 1)

        # У ticket2 все сообщения прочитаны
        self.assertEqual(self.ticket2.get_unread_messages_count(), 0)

        # Добавляем новое непрочитанное сообщение
        Message.objects.create(
            ticket=self.ticket2,
            text='Еще вопрос',
            is_admin=False,
            is_read=False
        )

        # Обновляем кэш
        self.ticket2.refresh_from_db()
        self.assertEqual(self.ticket2.get_unread_messages_count(), 1)

    def test_message_creation(self):
        """Тест создания сообщения"""
        message = Message.objects.create(
            ticket=self.ticket1,
            text='Тестовое сообщение',
            is_admin=False
        )

        self.assertFalse(message.is_admin)
        self.assertFalse(message.is_read)
        self.assertIsNotNone(message.created_at)
        self.assertIsNone(message.admin_author)

    def test_tag_creation(self):
        """Тест создания тега"""
        tag = Tag.objects.create(name='Новый тег', color='#123456')
        self.assertEqual(str(tag), 'Новый тег')
        self.assertEqual(tag.color, '#123456')

    def test_ticket_status_transition(self):
        """Тест изменения статуса обращения"""
        self.ticket1.status = 'closed'
        self.ticket1.closed_at = timezone.now()
        self.ticket1.save()

        self.assertEqual(self.ticket1.status, 'closed')
        self.assertIsNotNone(self.ticket1.closed_at)

    def test_ticket_priority_update(self):
        """Тест изменения приоритета обращения"""
        self.ticket1.priority = 'critical'
        self.ticket1.save()

        self.assertEqual(self.ticket1.priority, 'critical')
        self.assertEqual(self.ticket1.get_priority_display(), 'Критический')


class ViewTests(SupportAppTests):
    """Тесты представлений"""

    def test_ticket_list_view_unauthorized(self):
        """Тест доступа к списку обращений без авторизации"""
        response = self.client.get(reverse('ticket_list'))
        # Должен быть редирект на страницу входа
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_ticket_list_view_authorized(self):
        """Тест доступа к списку обращений с авторизацией"""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('ticket_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'support/ticket_list.html')
        self.assertContains(response, 'Иван Иванов')
        self.assertContains(response, 'Петр Петров')

    def test_ticket_list_view_non_staff(self):
        """Тест доступа к списку обращений для не-администратора"""
        self.client.login(username='user', password='testpass123')
        response = self.client.get(reverse('ticket_list'))

        # Не-администратор не должен иметь доступ
        self.assertEqual(response.status_code, 302)

    def test_ticket_list_filters(self):
        """Тест фильтрации списка обращений"""
        self.client.login(username='admin', password='testpass123')

        # Фильтр по статусу "открыто"
        response = self.client.get(reverse('ticket_list') + '?status=open')
        self.assertContains(response, 'Иван Иванов')
        self.assertNotContains(response, 'Петр Петров')

        # Фильтр по статусу "закрыто"
        response = self.client.get(reverse('ticket_list') + '?status=closed')
        self.assertContains(response, 'Сидор Сидоров')
        self.assertNotContains(response, 'Иван Иванов')

        # Фильтр по приоритету "высокий"
        response = self.client.get(reverse('ticket_list') + '?priority=high')
        self.assertContains(response, 'Иван Иванов')
        self.assertNotContains(response, 'Петр Петров')

    def test_ticket_list_search(self):
        """Тест поиска в списке обращений"""
        self.client.login(username='admin', password='testpass123')

        # Поиск по имени пользователя
        response = self.client.get(reverse('ticket_list') + '?q=Иван')
        self.assertContains(response, 'Иван Иванов')
        self.assertNotContains(response, 'Петр Петров')

        # Поиск по теме
        response = self.client.get(reverse('ticket_list') + '?q=оплате')
        self.assertContains(response, 'Петр Петров')
        self.assertNotContains(response, 'Иван Иванов')

    def test_update_ticket_status(self):
        """Тест изменения статуса обращения"""
        self.client.login(username='admin', password='testpass123')

        response = self.client.post(
            reverse('ticket_detail', args=[self.ticket1.ticket_id]),
            {'status': 'closed'}
        )

        self.assertEqual(response.status_code, 200)

        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.status, 'closed')
        self.assertIsNotNone(self.ticket1.closed_at)

    def test_assign_ticket_to_admin(self):
        """Тест назначения обращения на администратора"""
        self.client.login(username='admin', password='testpass123')

        response = self.client.post(
            reverse('ticket_detail', args=[self.ticket2.ticket_id]),
            {'assign_to_me': 'true'}
        )

        self.assertEqual(response.status_code, 200)

        self.ticket2.refresh_from_db()
        self.assertEqual(self.ticket2.admin, self.admin_user)

    def test_update_ticket_tags(self):
        """Тест обновления тегов обращения"""
        self.client.login(username='admin', password='testpass123')

        response = self.client.post(
            reverse('ticket_detail', args=[self.ticket2.ticket_id]),
            {'tags': [self.tag_urgent.id, self.tag_feature.id]}
        )

        self.assertEqual(response.status_code, 200)

        self.ticket2.refresh_from_db()
        self.assertEqual(self.ticket2.tags.count(), 2)
        self.assertIn(self.tag_urgent, self.ticket2.tags.all())
        self.assertIn(self.tag_feature, self.ticket2.tags.all())
