from django.db import models


class AlchemyEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["event_id"]),
        ]

    def __str__(self):
        return f"AlchemyEvent {self.event_id}"

    @classmethod
    def save_if_not_exists(cls, event_id):
        """
        Salva o event_id se ele não existir no banco.
        Retorna (objeto, created) onde created é True se foi criado, False se já existia
        """
        obj, created = cls.objects.get_or_create(event_id=event_id)
        return obj, created