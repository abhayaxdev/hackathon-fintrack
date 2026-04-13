import logging

from django.core.management.base import BaseCommand
from core.models import Currency

logger = logging.getLogger(__name__)

DEFAULT_CURRENCIES = [
    {'code': 'NRS', 'name': 'Nepali Rupee',      'symbol': '₨'},
    {'code': 'USD', 'name': 'US Dollar',          'symbol': '$'},
    {'code': 'AUD', 'name': 'Australian Dollar',  'symbol': 'A$'},
]


class Command(BaseCommand):
    help = 'Seed the database with default currencies (NRS, USD, AUD).'

    def handle(self, *args, **kwargs):
        created_count = 0
        updated_count = 0
        existing_count = 0

        for data in DEFAULT_CURRENCIES:
            currency, created = Currency.objects.get_or_create(
                code=data['code'],
                defaults={'name': data['name'], 'symbol': data['symbol']},
            )

            if created:
                created_count += 1
                logger.info(f"Currency created: {data['code']} — {data['name']} ({data['symbol']})")
                self.stdout.write(self.style.SUCCESS(f"  [created]  {data['code']}  {data['name']}  ({data['symbol']})"))
            else:
                # Update name/symbol in case they were seeded with incorrect values previously
                changed = False
                if currency.name != data['name'] or currency.symbol != data['symbol']:
                    currency.name = data['name']
                    currency.symbol = data['symbol']
                    currency.save()
                    changed = True

                if changed:
                    updated_count += 1
                    logger.info(f"Currency updated: {data['code']} — {data['name']} ({data['symbol']})")
                    self.stdout.write(self.style.WARNING(f"  [updated]  {data['code']}  {data['name']}  ({data['symbol']})"))
                else:
                    existing_count += 1
                    logger.info(f"Currency already up to date, skipping: {data['code']}")
                    self.stdout.write(self.style.WARNING(f"  [exists]   {data['code']}  {data['name']}  ({data['symbol']})"))

        summary = (
            f"\nDone. {created_count} created, {updated_count} updated, {existing_count} already up to date."
        )
        logger.info(
            f"seed_currencies complete — created={created_count}, updated={updated_count}, existing={existing_count}"
        )
        self.stdout.write(self.style.SUCCESS(summary))
