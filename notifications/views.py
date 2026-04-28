from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from chat.services.message_service import send_message, get_family_messages
from families.utils import get_family_of_user

