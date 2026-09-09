from django.contrib import admin
from .models import Story, StoryItem, BriefRevision, Publication, Merge, AuditEvent

admin.site.register(Story)
admin.site.register(StoryItem)
admin.site.register(BriefRevision)
admin.site.register(Publication)
admin.site.register(Merge)
admin.site.register(AuditEvent)
