from django.urls import path
from .views import ScheduleListCreate, ScheduleDetail, DeviceVersion, DeviceScheduleCSV, DeviceHeartbeat, DashboardStatus
urlpatterns = [
    path('schedules/', ScheduleListCreate.as_view()),
    path('schedules/<int:pk>/', ScheduleDetail.as_view()),
    path('device/version/', DeviceVersion.as_view()),
    path('device/schedule.csv', DeviceScheduleCSV.as_view()),
    path('device/heartbeat/', DeviceHeartbeat.as_view()),
    path('dashboard/status/', DashboardStatus.as_view()),
]
