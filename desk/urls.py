from django.urls import path
from . import views

urlpatterns = [
    path("stories/", views.story_list),
    path("stories/<int:pk>/", views.story_detail),
    path("stories/<int:pk>/claim/", views.story_claim),
    path("stories/<int:pk>/revise/", views.story_revise),
    path("stories/<int:pk>/submit/", views.story_submit),
    path("stories/<int:pk>/publish/", views.story_publish),
    path("stories/<int:pk>/correct/", views.story_correct),
    path("stories/<int:pk>/merge/", views.story_merge),
    path("stories/<int:pk>/spike/", views.story_spike),
    path("stories/<int:pk>/detach/", views.story_detach_item),
    path("cluster/", views.run_cluster),
    path("published/<slug:slug>/", views.published_detail),
    path("audit/", views.audit_log),
]
