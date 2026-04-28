from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import confirmed_required, first_login_required


def home(request):
    return render(request, 'core/home.html')

@login_required
@confirmed_required
@first_login_required
def dashboard(request):
    return render(request, "core/dashboard.html")

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