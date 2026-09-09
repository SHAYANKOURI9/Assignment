from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        REPORTER = "REPORTER", "Reporter"
        EDITOR = "EDITOR", "Editor"
        DESK_HEAD = "DESK_HEAD", "Desk Head"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.REPORTER)

    @property
    def is_reporter(self):
        return self.role == self.Role.REPORTER

    @property
    def is_editor(self):
        return self.role == self.Role.EDITOR

    @property
    def is_desk_head(self):
        return self.role == self.Role.DESK_HEAD

    def __str__(self):
        return f"{self.username} ({self.role})"
