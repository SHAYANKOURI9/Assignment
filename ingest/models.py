from django.db import models


class Source(models.Model):
    class Kind(models.TextChoices):
        WIRE = "WIRE", "Wire"
        PRESS_RELEASE = "PRESS_RELEASE", "Press Release"
        BLOG = "BLOG", "Blog"
        SOCIAL = "SOCIAL", "Social"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    handle = models.CharField(max_length=50, blank=True)
    trust_tier = models.PositiveSmallIntegerField(default=3)  # 1=wire, 2=official, 3=blog/social
    homepage = models.URLField(blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["trust_tier", "name"]


class RawItem(models.Model):
    class State(models.TextChoices):
        UNTRIAGED = "UNTRIAGED", "Untriaged"
        CLUSTERED = "CLUSTERED", "Clustered"
        SPIKED = "SPIKED", "Spiked"

    class IngestMethod(models.TextChoices):
        FILE = "FILE", "File"
        IMAGE = "IMAGE", "Image / Screenshot"
        MANUAL = "MANUAL", "Manual"

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="items")
    external_id = models.CharField(max_length=100, unique=True)
    headline = models.CharField(max_length=500)
    body = models.TextField()
    url = models.URLField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField()  # dwell timer starts here
    ingest_method = models.CharField(max_length=10, choices=IngestMethod.choices, default=IngestMethod.FILE)
    image = models.ImageField(upload_to="ingest/images/", null=True, blank=True)
    extraction_notes = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.UNTRIAGED, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.external_id}: {self.headline[:60]}"

    class Meta:
        ordering = ["-received_at"]
