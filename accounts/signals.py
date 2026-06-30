from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile
from accounts.utils import generate_cf


@receiver(post_save, sender=UserProfile)
def calculate_fiscal_code(sender, instance, **kwargs):
    """Calcolo automatico CF quando i dati sono completi."""

    if not instance.user:
        return

    # ✅ Verifica dati necessari (incluso birth_place_code)
    if not all([
        instance.user.first_name,
        instance.user.last_name,
        instance.birth_date,
        instance.birth_place_code,  # ← codice catastale
        instance.gender
    ]):
        return

    # Calcola CF
    cf = generate_cf(
        first_name=instance.user.first_name,
        last_name=instance.user.last_name,
        birth_date=instance.birth_date,
        birth_place_code=instance.birth_place_code,  # ← codice
        gender=instance.gender
    )

    if not cf:
        return

    # Aggiorna evitando loop
    if instance.codice_fiscale != cf:
        UserProfile.objects.filter(pk=instance.pk).update(
            codice_fiscale=cf,
            cf_status='calculated'
        )

    # ⚠️ se birth_place NON è codice catastale → NON funziona
    cf = generate_cf(
        first_name=instance.user.first_name,
        last_name=instance.user.last_name,
        birth_date=instance.birth_date,
        birth_place_code=instance.birth_place,
        gender=instance.gender
    )

    if not cf:
        return

    # 🔁 evita loop + update diretto DB
    if instance.codice_fiscale != cf:
        UserProfile.objects.filter(pk=instance.pk).update(
            codice_fiscale=cf
        )