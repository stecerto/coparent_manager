from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Elimina account inattivi più vecchi di 30 giorni'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Numero di giorni di inattività (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra solo cosa verrebbe eliminato, senza eliminare'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        cutoff_date = timezone.now() - timedelta(days=days)

        # Trova utenti inattivi vecchi
        inactive_users = User.objects.filter(
            is_active=False,
            date_joined__lt=cutoff_date
        )

        count = inactive_users.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ Nessun account inattivo da eliminare'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'🔍 [DRY RUN] Verrebbero eliminati {count} account inattivi:'
            ))
            for user in inactive_users[:10]:
                self.stdout.write(f'  - {user.email} (registrato il {user.date_joined})')
            if count > 10:
                self.stdout.write(f'  ... e altri {count - 10}')
        else:
            inactive_users.delete()
            self.stdout.write(self.style.SUCCESS(
                f'✅ Eliminati {count} account inattivi più vecchi di {days} giorni'
            ))
            logger.info(f"🗑️ Cleanup: eliminati {count} account inattivi")