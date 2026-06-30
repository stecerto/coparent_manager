from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Elimina account inattivi (fallita registrazione) dopo 15 giorni'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=15,
            help='Numero di giorni di inattività (default: 15)'
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

        # Trova utenti inattivi (is_active=False) più vecchi di 15 giorni
        inactive_users = User.objects.filter(
            is_active=False,
            date_joined__lt=cutoff_date
        )

        count = inactive_users.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Nessun account inattivo da eliminare (più vecchi di {days} giorni)'
            ))
            return

        self.stdout.write(self.style.WARNING(
            f'🔍 Trovati {count} account inattivi più vecchi di {days} giorni'
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'🔍 [DRY RUN] Verrebbero eliminati {count} account:'
            ))
            for user in inactive_users[:20]:
                days_old = (timezone.now() - user.date_joined).days
                self.stdout.write(
                    f'  - {user.email} (registrato {days_old} giorni fa)'
                )
            if count > 20:
                self.stdout.write(f'  ... e altri {count - 20}')
        else:
            # Elimina anche i profili associati
            for user in inactive_users:
                # Elimina profilo se esiste
                if hasattr(user, 'userprofile'):
                    user.userprofile.delete()

                # Elimina inviti pendenti
                if hasattr(user, 'sent_invitations'):
                    user.sent_invitations.filter(status='pending').delete()

                # Elimina utente
                user.delete()
                logger.info(f"🗑️ Eliminato account inattivo: {user.email}")

            self.stdout.write(self.style.SUCCESS(
                f'✅ Eliminati {count} account inattivi più vecchi di {days} giorni'
            ))