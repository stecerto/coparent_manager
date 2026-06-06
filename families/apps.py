from django.apps import AppConfig


class FamiliesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'families'

    def ready(self):
        # Importa i segnali per registrarli
        import families.signals
        import families.signal_handlers
