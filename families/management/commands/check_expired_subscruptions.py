from django.core.management.base import BaseCommand
from django.utils import timezone
from families.models import PaymentSubscription
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Controlla e disattiva account con abbonamento scaduto'

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. Trova abbonamenti scaduti ma ancora in periodo di grazia
        grace_period_expired = PaymentSubscription.objects.filter(
            status='active',
            subscription_end__lt=now,
            grace_period_end__gte=now
        )

        for sub in grace_period_expired:
            sub.status = 'grace_period'
            sub.save()
            logger.info(f"⚠️ {sub.user.email} entrato in periodo di grazia (scadenza: {sub.grace_period_end})")

        # ✅ NUOVO: Attiva piani pending alla scadenza
        pending_activations = PaymentSubscription.objects.filter(
            pending_plan__isnull=False,
            subscription_end__lt=now,
            status__in=['active', 'grace_period']
        )

        for sub in pending_activations:
            old_plan = sub.current_plan
            sub.activate_pending_plan()
            logger.info(f"✅ {sub.user.email} - Piano cambiato: {old_plan} → {sub.current_plan}")

        # 2. Trova abbonamenti oltre il periodo di grazia
        suspended = PaymentSubscription.objects.filter(
            status__in=['active', 'grace_period'],
            grace_period_end__lt=now
        )

        for sub in suspended:
            sub.mark_as_suspended()
            logger.warning(f"❌ {sub.user.email} disattivato per mancato pagamento")

        self.stdout.write(self.style.SUCCESS('✅ Controllo abbonamenti completato'))