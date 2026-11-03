from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from project.example.models import Article, Gallery, Page, PageItem, PageSection, Photo


class Command(BaseCommand):
    help = "Create the fixtures the Playwright e2e suite depends on (idempotent)."

    def handle(self, *args, **options):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com"},
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password("admin")
        user.save()

        Article.objects.get_or_create(title="Seed Article")

        gallery, created = Gallery.objects.get_or_create(title="Seed Gallery")
        if created:
            for position, caption in enumerate(["First photo", "Second photo"]):
                Photo.objects.create(
                    gallery=gallery, position=position, caption=caption
                )

        page, created = Page.objects.get_or_create(title="Seed Page")
        if created:
            section = PageSection.objects.create(
                page=page, title="Seed Section", position=0
            )
            PageItem.objects.create(section=section, title="Seed Item", position=0)

        self.stdout.write(self.style.SUCCESS("Seeded e2e fixtures."))
