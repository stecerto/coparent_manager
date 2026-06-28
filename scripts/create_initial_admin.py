import os
from django.contrib.auth import get_user_model

User = get_user_model()

# ✅ Leggi password da variabile d'ambiente
password = os.getenv('ADMIN_PASSWORD')

if not password:
    print("❌ ADMIN_PASSWORD non impostata nelle variabili d'ambiente")
    exit(1)

if not User.objects.filter(email='admin@coparentmanager.com').exists():
    admin = User.objects.create_superuser(
        email='admin@coparentmanager.com',
        password=password,  # ✅ Password da env
        first_name='Admin',
        last_name='CoParent'
    )
    print(f"✅ Admin creato: {admin.email}")
else:
    print("⚠️ Admin già esistente")

    '''
    Soluzione Migliore: createsuperuser Interattivo
Invece dello script, usa il comando Django interattivo (più sicuro):
Su Render Shell:
bash
# 1. Apri Shell dal dashboard Render
# 2. Esegui:
python manage.py createsuperuser


Ti chiederà:

Email: admin@coparentmanager.com
First name: Admin
Last name: CoParent
Password: ********  (digiti senza vedere)
Password (again): ********
Superuser created successfully.

    
    
    '''