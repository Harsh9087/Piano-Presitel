from django.contrib import admin
from .models import Schedule, Device, ScheduleVersion
@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('day', 'start_time', 'seconds', 'enabled')
    list_filter = ('day', 'enabled')
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'name', 'last_seen', 'reported_version')
admin.site.register(ScheduleVersion)
