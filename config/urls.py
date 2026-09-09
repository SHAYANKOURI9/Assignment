from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/ingest/", include("ingest.urls")),
    path("api/desk/", include("desk.urls")),
    path("api/analytics/", include("analytics.urls")),
    # Catch-all: serve the SPA for any non-API route
    re_path(r"^(?!api/).*$", TemplateView.as_view(template_name="index.html")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
