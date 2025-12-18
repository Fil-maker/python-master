from django.db import models


class VKUser(models.Model):
    vk_id = models.BigIntegerField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "VK Пользователь"
        verbose_name_plural = "VK Пользователи"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class VKMessage(models.Model):
    DIRECTION_CHOICES = [
        ('incoming', 'Входящее'),
        ('outgoing', 'Исходящее'),
    ]

    user = models.ForeignKey(VKUser, on_delete=models.CASCADE, related_name='messages')
    text = models.TextField()
    vk_message_id = models.BigIntegerField()
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['vk_message_id']),
            models.Index(fields=['timestamp']),
        ]
        verbose_name = "VK Сообщение"
        verbose_name_plural = "VK Сообщения"

    def __str__(self):
        return f"Message {self.vk_message_id} from {self.user}"