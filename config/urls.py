"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from django.urls import path
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from django.urls import path
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import traceback


@csrf_exempt
def create_admin_temp(request):
    """URL TEMPORANEO - RIMUOVERE DOPO USO!"""
    output = []

    try:
        output.append("<h2>🔍 Debug Info</h2>")

        # Importa il modello User
        from django.contrib.auth import get_user_model
        User = get_user_model()
        output.append(f"<p>✅ User model: {User.__name__}</p>")
        output.append(f"<p>✅ Campi User: {[f.name for f in User._meta.get_fields()]}</p>")
        username = 'stecerto'
        email = 'admin@coparentmanager.com'
        password = 'Kx9mP2vL5nQ8wR4tY7hJ3bN6q'

        # Controlla se l'utente esiste già
        if User.objects.filter(email=email).exists():
            return HttpResponse(f"""
            <h1>⚠️ Admin Già Esistente</h1>
            <p>L'utente {email} esiste già nel database.</p>
            <p><a href="/admin/">Vai all'Admin Panel →</a></p>
            """)

        output.append("<p>✅ Utente non esiste, procedo con creazione...</p>")

        # Prova a creare l'admin con solo email e password
        admin = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )

        output.append(f"<p>✅ Admin creato: {admin.email}</p>")

        return HttpResponse(f"""
        <h1>✅ Admin Creato con Successo!</h1>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Password:</strong> {password}</p>
        <p style="color:red;"><strong>⚠️ IMPORTANTE: Rimuovi questo URL da urls.py immediatamente!</strong></p>
        <p><a href="/admin/">Vai all'Admin Panel →</a></p>
        <hr>
        <h3>Debug Info:</h3>
        {''.join(output)}
        """)

    except Exception as e:
        error_msg = traceback.format_exc()
        return HttpResponse(f"""
        <h1>❌ Errore</h1>
        <p><strong>Tipo:</strong> {type(e).__name__}</p>
        <p><strong>Messaggio:</strong> {str(e)}</p>
        <hr>
        <h3>Debug Info:</h3>
        {''.join(output) if output else 'Nessuna info'}
        <hr>
        <h3>Traceback Completo:</h3>
        <pre style="background:#f4f4f4;padding:10px;overflow:auto;font-size:12px;">{error_msg}</pre>
        """, status=500)

urlpatterns = [
    path('temp-create-admin-xyz123/', create_admin_temp),
    path('admin/', admin.site.urls),
    path("accounts/", include("accounts.urls")),
#Core
    path("", include("core.urls")),
# Children
    path("children/", include("children.urls")),
#Documents
    path("documents/", include("documents.urls")),
#Families
    path("families/", include("families.urls")),
# Expenses
    path("expenses/", include("expenses.urls")),
# Calendar
    path("calendar/", include("calendar_app.urls")),
# Chat
    path("chat/", include("chat.urls")),
#notification
    path("notifications/", include("notifications.urls", namespace='notifications')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )