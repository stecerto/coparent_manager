# core/pricing.py
from decimal import Decimal

# =========================
# 💰 PREZZI SPECIFICI PER RUOLO
# =========================
ROLE_PRICING = {
    'parent': {
        'starter': Decimal('5.00'),
        'pro': Decimal('12.00'),
        'enterprise': Decimal('19.90'),
    },
    'lawyer': {
        'starter': Decimal('19.99'),
        'pro': Decimal('39.99'),
        'enterprise': None,  # Custom
    },
    'mediator': {
        'starter': Decimal('24.99'),
        'pro': Decimal('49.99'),
        'enterprise': None,  # Custom
    },
    'consultant': {
        'starter': Decimal('19.99'),
        'pro': Decimal('34.99'),
        'enterprise': None,  # Custom
    }
}

# =========================
# 📝 METADATI E FEATURES SPECIFICHE PER RUOLO
# =========================
ROLE_PLAN_METADATA = {
    'parent': {
        'starter': {'title': 'Starter', 'limit': 'Gestione base familiare',
                    'features': [{'name': 'Gestione spese illimitata', 'active': True},
                                 {'name': 'Chat familiare sicura', 'active': True},
                                 {'name': 'Calendario turni base', 'active': True},
                                 {'name': 'Archivio documenti (2 GB)', 'active': True},
                                 {'name': 'Grafici e report avanzati', 'active': False},
                                 {'name': 'Export PDF illimitato', 'active': False}]},
        'pro': {'title': 'Pro', 'limit': 'Per famiglie esigenti', 'recommended': True,
                'features': [{'name': 'Tutto di Starter', 'active': True},
                             {'name': 'Grafici spese per categoria', 'active': True},
                             {'name': 'Trend mensili e comparativi', 'active': True},
                             {'name': 'Export PDF illimitato', 'active': True},
                             {'name': 'Fascicolo famigliare stampabile', 'active': True},
                             {'name': 'Archivio documenti (5 GB)', 'active': True}]},
        'enterprise': {'title': 'Enterprise', 'limit': 'Per famiglie complesse',
                       'features': [{'name': 'Tutto di Pro', 'active': True},
                                    {'name': 'Archivio documenti (10 GB)', 'active': True},
                                    {'name': 'Monitoraggio spazio in tempo reale', 'active': True},
                                    {'name': 'Audit log completo', 'active': True},
                                    {'name': 'Crittografia avanzata', 'active': True},
                                    {'name': 'Supporto prioritario', 'active': True}]}
    },
    'lawyer': {
        'starter': {'title': 'Studio Base', 'limit': 'Fino a 3 famiglie',
                    'features': [{'name': 'Dashboard multi-famiglia', 'active': True},
                                 {'name': 'Chat riservata assistito', 'active': True},
                                 {'name': 'Documenti e versioni', 'active': True},
                                 {'name': 'Export legale personalizzato', 'active': False}]},
        'pro': {'title': 'Studio Pro', 'limit': 'Fino a 10 famiglie', 'recommended': True,
                'features': [{'name': 'Tutto di Base', 'active': True},
                             {'name': 'Report per tribunale', 'active': True},
                             {'name': 'Firme digitali integrate', 'active': True},
                             {'name': 'Log attività e audit trail', 'active': True}]},
        'enterprise': {'title': 'Studio Enterprise', 'limit': 'Per studi legali strutturati', 'is_custom': True,
                       'features': [{'name': 'Famiglie illimitate', 'active': True},
                                    {'name': 'API dedicate', 'active': True},
                                    {'name': 'Onboarding dedicato', 'active': True},
                                    {'name': 'SLA garantito 99,9%', 'active': True}]}
    },
    'mediator': {
        'starter': {'title': 'Mediator Base', 'limit': 'Fino a 5 nuclei',
                    'features': [{'name': 'Spazio neutro condiviso', 'active': True},
                                 {'name': 'Chat moderata', 'active': True},
                                 {'name': 'Note di mediazione', 'active': True},
                                 {'name': 'Report avanzati', 'active': False}]},
        'pro': {'title': 'Mediator Pro', 'limit': 'Fino a 15 nuclei', 'recommended': True,
                'features': [{'name': 'Tutto di Base', 'active': True}, {'name': 'Verbali strutturati', 'active': True},
                             {'name': 'Timeline concordata', 'active': True},
                             {'name': 'Export per CTU/CTP', 'active': True}]},
        'enterprise': {'title': 'Centro Mediazione', 'limit': 'Per enti e associazioni', 'is_custom': True,
                       'features': [{'name': 'Multi-mediatore', 'active': True},
                                    {'name': 'Dashboard amministrativa', 'active': True},
                                    {'name': 'Whitelabel opzionale', 'active': True},
                                    {'name': 'Formazione inclusa', 'active': True}]}
    },
    'consultant': {
        'starter': {'title': 'Consulente Base', 'limit': 'Fino a 4 clienti',
                    'features': [{'name': 'Dashboard dedicata', 'active': True},
                                 {'name': 'Analisi spese familiari', 'active': True},
                                 {'name': 'Note riservate', 'active': True},
                                 {'name': 'Modelli personalizzabili', 'active': False}]},
        'pro': {'title': 'Consulente Pro', 'limit': 'Fino a 10 clienti', 'recommended': True,
                'features': [{'name': 'Tutto di Base', 'active': True},
                             {'name': 'Template report avanzati', 'active': True},
                             {'name': 'Simulatore economico', 'active': True},
                             {'name': 'Accesso API read-only', 'active': True}]},
        'enterprise': {'title': 'Agenzia / Studio', 'limit': 'Per team multidisciplinari', 'is_custom': True,
                       'features': [{'name': 'Clienti illimitati', 'active': True},
                                    {'name': 'Gestione ruoli interni', 'active': True},
                                    {'name': 'Audit e compliance', 'active': True},
                                    {'name': 'Supporto dedicato 24/7', 'active': True}]}
    }
}


def get_yearly_price(monthly_price):
    """Calcola il prezzo annuale con 1 mese gratis (paghi 11 mesi)"""
    if monthly_price is None:
        return None
    return monthly_price * 11


def format_price(amount, currency='EUR'):
    """Formatta un prezzo per la visualizzazione"""
    if amount is None:
        return "Custom"
    if currency == 'EUR':
        return f"€{amount:.2f}".replace('.', ',')
    return f"{amount:.2f} {currency}"


def get_plan_price(role, plan_id):
    """Ottiene il prezzo mensile di un piano per un ruolo specifico"""
    return ROLE_PRICING.get(role, ROLE_PRICING['parent']).get(plan_id, Decimal('0.00'))


def get_plan_currency(role='parent'):
    """Restituisce la valuta (fissa a EUR per ora)"""
    return 'EUR'


def get_role_plan_data(role):
    """Restituisce i dati dei piani completi e formattati per un ruolo specifico"""
    role_pricing = ROLE_PRICING.get(role, ROLE_PRICING['parent'])
    role_metadata = ROLE_PLAN_METADATA.get(role, ROLE_PLAN_METADATA['parent'])

    plans = []
    for plan_id in ['starter', 'pro', 'enterprise']:
        monthly_price = role_pricing.get(plan_id)
        metadata = role_metadata.get(plan_id, {})

        plans.append({
            'id': plan_id,
            'title': metadata.get('title', plan_id.title()),
            'limit': metadata.get('limit', ''),
            'monthly_price': monthly_price,
            'monthly_formatted': format_price(monthly_price),
            'yearly_formatted': format_price(get_yearly_price(monthly_price)),
            'features': metadata.get('features', []),
            'recommended': metadata.get('recommended', False),
            'is_custom': metadata.get('is_custom', False),
        })
    return plans