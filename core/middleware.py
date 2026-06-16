# core/middleware.py
from django.shortcuts import redirect
from django.contrib import messages


class SubscriptionMiddleware:
    """Controlla lo stato dell'abbonamento ad ogni richiesta"""

    # ✅ URL SEMPRE PERMESSE (anche con abbonamento scaduto/sospeso)
    EXEMPT_URLS = [
        'login', 'logout', 'pricing', 'payment', 'change_plan',
        'account_suspended', 'static', 'media', 'admin',
        'unread_count',
        'register', 'password_reset', 'home', 'lawyer_home',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ✅ IMPORTANTE: Processa PRIMA la request
        response = self.get_response(request)

        # Solo per utenti autenticati
        if request.user.is_authenticated:
            # Controlla se l'URL è esente
            url_name = None
            if request.resolver_match:
                url_name = request.resolver_match.url_name

            # Se è esento, ritorna la response senza fare nulla
            if url_name and any(exempt in url_name for exempt in self.EXEMPT_URLS):
                return response

            # Se non c'è url_name (es. statici), ritorna la response
            if not url_name:
                return response

            # Controlla profilo
            profile = getattr(request.user, 'profile', None)
            if profile:
                # ✅ Se l'abbonamento è scaduto e non è stato rinnovato
                if hasattr(profile, 'is_expired') and profile.is_expired and getattr(profile, 'payment_status',
                                                                                     '') == "active":
                    if getattr(profile, 'auto_renew', True):
                        profile.payment_status = "pending_payment"
                        profile.save()
                    else:
                        profile.payment_status = "suspended"
                        profile.save()

                # ✅ BLOCCO TOTALE: Se è sospeso (oltre i 25 giorni)
                if getattr(profile, 'payment_status', '') == "suspended":
                    if url_name not in ['pricing', 'payment', 'change_plan', 'logout']:
                        messages.error(
                            request,
                            "🚫 Account sospeso. Il periodo di grazia di 25 giorni è terminato. Rinnova per riattivare l'accesso."
                        )
                        return redirect('pricing')

                # ✅ BLOCCO PARZIALE: Se è scaduto (entro i 25 giorni)
                # Blocca TUTTO tranne pricing/payment/logout
                elif getattr(profile, 'is_expired', False):
                    if url_name not in ['pricing', 'payment', 'change_plan', 'logout']:
                        messages.warning(
                            request,
                            "⏰ Abbonamento scaduto. Le funzioni sono limitate. Rinnova per accedere a tutte le funzionalità."
                        )
                        return redirect('pricing')

        # ✅ CRITICO: Ritorna SEMPRE la response
        return response

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