from pathlib import Path
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.http import HttpResponse, FileResponse
from django.conf import settings

FRONTEND_DIST = settings.BASE_DIR.parent / 'frontend' / 'dist'

def spa_view(request, path=""):
    target_file = FRONTEND_DIST / path
    if path and target_file.is_file():
        return FileResponse(open(target_file, 'rb'))
    index_file = FRONTEND_DIST / 'index.html'
    if index_file.exists():
        return HttpResponse(index_file.read_text(encoding='utf-8'), content_type='text/html')
    return HttpResponse("Frontend build not found. Please run 'npm run build' inside frontend/.", status=404)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('scheduler.urls')),
    re_path(r'^django-static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^(?P<path>.*)$', spa_view),
]
