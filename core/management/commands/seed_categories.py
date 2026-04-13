import logging

from django.core.management.base import BaseCommand
from core.models import Category

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = [
    'Food',
    'Entertainment',
    'Transportation',
    'Health & Fitness',
    'Education',
    'Shopping',
    'Housing / Rent',
    'Furniture',
    'Pets',
    'Subscriptions',
    'Miscellaneous',
]


class Command(BaseCommand):
    help = 'Seed the database with default expense categories.'

    def handle(self, *args, **kwargs):
        created_count = 0
        existing_count = 0

        for name in DEFAULT_CATEGORIES:
            _, created = Category.objects.get_or_create(
                name=name,
                category_type='expense',
                user=None,
                defaults={'is_default': True},
            )
            if created:
                created_count += 1
                logger.info(f"Default category created: '{name}'")
                self.stdout.write(self.style.SUCCESS(f"  [created]  {name}"))
            else:
                existing_count += 1
                logger.info(f"Default category already exists, skipping: '{name}'")
                self.stdout.write(self.style.WARNING(f"  [exists]   {name}"))

        summary = (
            f"\nDone. {created_count} created, {existing_count} already existed."
        )
        logger.info(f"seed_categories complete — created={created_count}, existing={existing_count}")
        self.stdout.write(self.style.SUCCESS(summary))
