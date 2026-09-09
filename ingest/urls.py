from django.urls import path
from . import views

urlpatterns = [
    path("sources/", views.SourceListView.as_view()),
    path("items/", views.RawItemListView.as_view()),
    path("manual/", views.ingest_manual),
    path("screenshot/", views.ingest_screenshot),
]
