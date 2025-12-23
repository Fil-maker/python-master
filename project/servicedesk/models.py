from django.db import models
from django.contrib.auth.models import User


class VKGroup(models.Model):
    group_id = models.IntegerField(unique=True, verbose_name="ID группы")
    name = models.CharField(max_length=255, verbose_name="Название группы")
    access_token = models.CharField(max_length=255, verbose_name="Токен доступа")
    secret_key = models.CharField(max_length=50, blank=True, verbose_name="Секретный ключ")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    def __str__(self):
        return f"{self.name} (id{self.group_id})"


class VKMessage(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новое'),
        ('in_progress', 'В обработке'),
        ('answered', 'Отвечено'),
        ('closed', 'Закрыто'),
    ]

    message_id = models.IntegerField(verbose_name="ID сообщения ВК")
    from_id = models.IntegerField(verbose_name="ID отправителя")
    from_name = models.CharField(max_length=255, verbose_name="Имя отправителя")
    text = models.TextField(verbose_name="Текст сообщения")
    attachments = models.JSONField(default=list, blank=True, verbose_name="Вложения")
    date = models.DateTimeField(verbose_name="Дата получения", auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ответственный")
    response = models.TextField(blank=True, verbose_name="Ответ администратора")
    response_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата ответа")
    vk_group = models.ForeignKey(VKGroup, on_delete=models.CASCADE, verbose_name="Группа ВК")

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Сообщение {self.message_id} от {self.from_name}"