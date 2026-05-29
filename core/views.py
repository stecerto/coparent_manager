from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from accounts.decorators import confirmed_required, first_login_required
from core.choices import RoleChoices


def home(request):
    return render(request, 'core/home.html')

@login_required
@confirmed_required
@first_login_required
def dashboard(request):
    return render(request, "families/family_dashboard.html")


@login_required
def lawyer_home_view(request):
    # 🔒 Sicurezza: solo avvocati possono accedere
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role not in RoleChoices.lawyer_roles():
        return redirect('home')  # O 'families:lawyer_dashboard' se preferisci

    context = {
        'user': request.user,
        'profile': profile,
    }
    return render(request, 'core/lawyer_home.html', context)
'''
@login_required(login_url='/accounts/login/')
def dashboard(request):
    return render(request, "dashboard.html")

@login_required
def dashboard(request):
    if not request.user.is_active:
        return HttpResponse("Devi confermare la email")

    return render(request, "dashboard.html")

@confirmed_required
def dashboard(request):
    return render(request, "core/dashboard.html")

@permission_required('auth.view_user')
def admin_area(request):
    return render(request, "admin.html")


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"
    login_url = '/accounts/login/'

def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
'''