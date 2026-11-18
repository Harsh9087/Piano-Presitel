from django.db import models

DAYS = [(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')]

class Schedule(models.Model):
    day = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    seconds = models.PositiveIntegerField(help_text='ON duration for each of relays 1–6, in seconds')
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day', 'start_time', 'id']

    def __str__(self):
        return f'{self.get_day_display()} {self.start_time:%H:%M} ({self.seconds}s each)'

class Device(models.Model):
    device_id = models.CharField(max_length=80, unique=True, default='pico-w-01')
    name = models.CharField(max_length=100, default='Relay Controller')
    last_seen = models.DateTimeField(null=True, blank=True)
    reported_version = models.PositiveIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return self.name

class ScheduleVersion(models.Model):
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'version': 1})
        return obj
