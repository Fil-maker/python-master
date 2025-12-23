from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class VKGroup(models.Model):
    group_id = models.IntegerField(unique=True, verbose_name="ID группы")
    name = models.CharField(max_length=255, verbose_name="Название группы")
    access_token = models.CharField(max_length=255, verbose_name="Токен доступа")
    secret_key = models.CharField(max_length=50, blank=True, verbose_name="Секретный ключ")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    def __str__(self):
        return f"{self.name} (id{self.group_id})"


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('open', 'Открыто'),
        ('answered', 'Отвечено'),
        ('waiting', 'Ожидание'),
        ('closed', 'Закрыто'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
        ('critical', 'Критический'),
    ]

    ticket_id = models.CharField(max_length=20, unique=True, verbose_name="Номер обращения")
    user_id = models.IntegerField(verbose_name="ID пользователя ВК")
    user_name = models.CharField(max_length=255, verbose_name="Имя пользователя")
    user_photo = models.URLField(max_length=2048, blank=True, verbose_name="Фото пользователя")
    subject = models.CharField(max_length=255, default="Без темы", verbose_name="Тема обращения")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Закрыто")
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='assigned_tickets', verbose_name="Ответственный")
    vk_group = models.ForeignKey(VKGroup, on_delete=models.CASCADE, verbose_name="Группа ВК")
    tags = models.ManyToManyField('Tag', blank=True, verbose_name="Теги")

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['user_id', 'created_at']),
        ]

    def __str__(self):
        return f"Обращение #{self.ticket_id} от {self.user_name}"

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            # Генерация уникального номера обращения
            date_prefix = timezone.now().strftime('%Y%m%d')
            last_ticket = Ticket.objects.filter(ticket_id__startswith=date_prefix).order_by('ticket_id').last()
            if last_ticket:
                last_num = int(last_ticket.ticket_id.split('-')[1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.ticket_id = f"{date_prefix}-{new_num:04d}"
        super().save(*args, **kwargs)

    def get_unread_messages_count(self):
        return self.messages.filter(is_read=False).exclude(is_admin=True).count()

    def get_last_message(self):
        return self.messages.order_by('-created_at').first()


class Message(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages', verbose_name="Обращение")
    message_id = models.IntegerField(null=True, blank=True, verbose_name="ID сообщения ВК")
    text = models.TextField(verbose_name="Текст сообщения")
    attachments = models.JSONField(default=list, blank=True, verbose_name="Вложения")
    is_admin = models.BooleanField(default=False, verbose_name="От администратора")
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    admin_author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     verbose_name="Автор (админ)")

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        author = "Админ" if self.is_admin else "Пользователь"
        return f"Сообщение от {author} в #{self.ticket.ticket_id}"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Название тега")
    color = models.CharField(max_length=7, default='#6c757d', verbose_name="Цвет (HEX)")

    def __str__(self):
        return self.name