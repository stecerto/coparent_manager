# core/middleware.py

from django.shortcuts import redirect
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)


class SubscriptionMiddleware:
    """Controlla lo stato dell'abbonamento ad ogni richiesta"""

    # ✅ URL SEMPRE PERMESSE (anche con abbonamento scaduto/sospeso)
    EXEMPT_URLS = [
        'login', 'logout', 'pricing', 'payment', 'change_plan',
        'account_suspended', 'static', 'media', 'admin',
        'unread_count', 'register', 'password_reset', 'home', 'lawyer_home',
        'activate', 'resend_activation', 'account_inactive',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ✅ IMPORTANTE: Controlla PRIMA di processare la request
        if request.user.is_authenticated:
            # Controlla se l'URL è esente
            url_name = None
            if request.resolver_match:
                url_name = request.resolver_match.url_name

            # Se è esento, processa normalmente
            if url_name and any(exempt in url_name for exempt in self.EXEMPT_URLS):
                return self.get_response(request)

            # Se non c'è url_name (es. statici), processa normalmente
            if not url_name:
                return self.get_response(request)

            # ✅ Controlla profilo in sicurezza
            profile = None
            try:
                profile = request.user.profile
            except Exception as e:
                logger.debug(f"Utente senza profilo: {request.user.email} - {e}")
                # Utente senza profilo, processa normalmente
                return self.get_response(request)

            if profile:
                try:
                    # ✅ Se l'abbonamento è scaduto e non è stato rinnovato
                    if hasattr(profile, 'is_expired') and profile.is_expired:
                        payment_status = getattr(profile, 'payment_status', '')

                        if payment_status == "active":
                            auto_renew = getattr(profile, 'auto_renew', True)
                            if auto_renew:
                                profile.payment_status = "pending_payment"
                                profile.save()
                            else:
                                profile.payment_status = "suspended"
                                profile.save()

                    # ✅ BLOCCO TOTALE: Se è sospeso (oltre i 25 giorni)
                    payment_status = getattr(profile, 'payment_status', '')
                    if payment_status == "suspended":
                        if url_name not in ['pricing', 'payment', 'change_plan', 'logout']:
                            messages.error(
                                request,
                                "🚫 Account sospeso. Il periodo di grazia di 25 giorni è terminato. Rinnova per riattivare l'accesso."
                            )
                            return redirect('pricing')

                    # ✅ BLOCCO PARZIALE: Se è scaduto (entro i 25 giorni)
                    elif getattr(profile, 'is_expired', False):
                        if url_name not in ['pricing', 'payment', 'change_plan', 'logout']:
                            messages.warning(
                                request,
                                "⏰ Abbonamento scaduto. Le funzioni sono limitate. Rinnova per accedere a tutte le funzionalità."
                            )
                            return redirect('pricing')

                except Exception as e:
                    logger.error(f"Errore controllo abbonamento: {e}", exc_info=True)
                    # In caso di errore, processa normalmente (non bloccare l'utente)
                    pass

        # ✅ Processa la request
        return self.get_response(request)

'''
            # Controlla stato abbonamento
            subscription = getattr(request.user, 'subscription', None)

            if subscription:
                # Se l'abbonamento è scaduto e non è stato rinnovato
                if subscription.is_expired and subscription.status == "active":
                    if subscription.auto_renew:
                        # Segna come pending_payment
                        subscription.status = "pending_payment"
                        subscription.save()
                        messages.warning(
                            request,
                            "⏳ Il tuo abbonamento è scaduto. Effettua il pagamento per continuare a usare il servizio."
                        )
                        return redirect('pricing')
                    else:
                        # Sospendi account
                        subscription.suspend()

                # Se l'account è sospeso, blocca accesso
                if subscription.status == "suspended":
                    messages.error(
                        request,
                        "🚫 Il tuo account è sospeso. Rinnova l'abbonamento per riattivare l'accesso."
                    )
                    return redirect('pricing')

        return self.get_response(request)
            '''