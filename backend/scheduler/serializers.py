from rest_framework import serializers
from .models import Schedule
class ScheduleSerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source='get_day_display', read_only=True)
    class Meta:
        model = Schedule
        fields = ['id', 'day', 'day_name', 'start_time', 'seconds', 'enabled']
    def validate_seconds(self, value):
        if value < 1 or value > 86400:
            raise serializers.ValidationError('Duration must be between 1 and 86400 seconds.')
        return value
    def validate_day(self, value):
        if value not in range(7):
            raise serializers.ValidationError('Invalid weekday.')
        return value
