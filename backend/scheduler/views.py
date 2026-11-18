import csv
import io
import hmac
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from .models import Schedule, Device, ScheduleVersion
from .serializers import ScheduleSerializer

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def check_key(request, expected):
    supplied = request.headers.get('X-API-Key', '')
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise AuthenticationFailed('Invalid or missing API key.')

def bump_version():
    obj = ScheduleVersion.current()
    obj.version += 1
    obj.save(update_fields=['version', 'updated_at'])
    return obj.version

class ScheduleListCreate(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        check_key(request, settings.DASHBOARD_API_KEY)
    def get(self, request):
        rows = ScheduleSerializer(Schedule.objects.all(), many=True).data
        return Response({'version': ScheduleVersion.current().version, 'schedules': rows})
    def post(self, request):
        serializer = ScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        version = bump_version()
        return Response({'version': version, 'schedule': serializer.data}, status=status.HTTP_201_CREATED)

class ScheduleDetail(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        check_key(request, settings.DASHBOARD_API_KEY)
    def put(self, request, pk):
        try: obj = Schedule.objects.get(pk=pk)
        except Schedule.DoesNotExist: return Response({'detail': 'Not found'}, status=404)
        serializer = ScheduleSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(); version = bump_version()
        return Response({'version': version, 'schedule': serializer.data})
    def delete(self, request, pk):
        try: obj = Schedule.objects.get(pk=pk)
        except Schedule.DoesNotExist: return Response({'detail': 'Not found'}, status=404)
        obj.delete(); version = bump_version()
        return Response({'version': version}, status=204)

class DeviceVersion(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        check_key(request, settings.DEVICE_API_KEY)
    def get(self, request):
        return Response({'version': ScheduleVersion.current().version})

class DeviceScheduleCSV(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        check_key(request, settings.DEVICE_API_KEY)
    def get(self, request):
        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['Day', 'Start time', 'sec'])
        for item in Schedule.objects.filter(enabled=True).order_by('day', 'start_time', 'id'):
            writer.writerow([DAY_NAMES[item.day], item.start_time.strftime('%H:%M'), item.seconds])
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Cache-Control'] = 'no-store'
        response['X-Schedule-Version'] = str(ScheduleVersion.current().version)
        return response

class DeviceHeartbeat(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        check_key(request, settings.DEVICE_API_KEY)
    def post(self, request):
        device_id = str(request.data.get('device_id', 'pico-w-01'))[:80]
        version = request.data.get('version', 0)
        try: version = max(0, int(version))
        except (TypeError, ValueError): version = 0
        device, _ = Device.objects.get_or_create(device_id=device_id)
        device.last_seen = timezone.now()
        device.reported_version = version
        device.ip_address = request.META.get('REMOTE_ADDR')
        device.save(update_fields=['last_seen', 'reported_version', 'ip_address'])
        return Response({'ok': True})

class DashboardStatus(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        check_key(request, settings.DASHBOARD_API_KEY)
    def get(self, request):
        devices = []
        for d in Device.objects.all():
            devices.append({'device_id': d.device_id, 'name': d.name, 'last_seen': d.last_seen, 'reported_version': d.reported_version, 'ip_address': d.ip_address})
        return Response({'version': ScheduleVersion.current().version, 'devices': devices})
