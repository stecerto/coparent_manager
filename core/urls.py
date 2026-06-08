from xml.etree.ElementInclude import include

from django.urls import path, include
from .views import dashboard, home, lawyer_home_view, pricing_view, privacy_policy_view, change_plan_view

urlpatterns = [
    path("", home, name="home"),
    path("dashboard/", dashboard, name="dashboard"),
    path('lawyer/home/', lawyer_home_view, name='lawyer_home'),
    path("pricing/", pricing_view, name="pricing"),
    path("privacy/", privacy_policy_view, name="privacy_policy"),
    path('settings/change-plan/', change_plan_view, name='change_plan'),
]