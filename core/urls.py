from xml.etree.ElementInclude import include

from django.urls import path, include
from .views import home, lawyer_home_view, pricing_view, privacy_policy_view, change_plan_view, payment_page, \
    help_center, landing_page_view

urlpatterns = [
    path('', landing_page_view, name='landing'),

    # Home per utenti loggati
    path('home/', home, name='home'),
    path('lawyer/home/', lawyer_home_view, name='lawyer_home'),
    path("pricing/", pricing_view, name="pricing"),
    path("privacy/", privacy_policy_view, name="privacy_policy"),
    path('settings/change-plan/', change_plan_view, name='change_plan'),
    path("help/", help_center, name="help"),
    path('payment/', payment_page, name='payment'),
]