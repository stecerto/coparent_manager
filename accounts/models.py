from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from children.models import ChildProfile


# =========================
# 🔹 USER
# =========================
class User(AbstractUser):
    username = models.CharField(
        max_length=150,
        blank=True
        )
    email = models.EmailField(unique=True)

   # is_parent = models.BooleanField(default=True)
   # is_lawyer = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

# =========================
# 🔹 USER PROFILE
# =========================
class UserProfile(models.Model):
    ROLE_CHOICES = (
        ("parent_a", "Genitore A"),
        ("parent_b", "Genitore B"),
        ('lawyer_a', 'Avvocato A'),
        ('lawyer_b', 'Avvocato B'),
        ("mediator", "Mediatore"),
        ("consultant", "Consulente"),

    )
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    #family = models.ForeignKey('families.Family', on_delete=models.CASCADE, null=True, blank=True)
    # dati personali (OK)
    address = models.CharField(max_length=255, blank=True)
    birth_place = models.CharField(max_length=255, blank=True)
    phone = PhoneNumberField(null=True, blank=True)
    firm_name = models.CharField(max_length=100,blank=True)

    # stato
    setup_complete = models.BooleanField(default=False)

    def __str__(self):
        return f"Profilo di {self.user.email}"

'''
    @property
    def children(self):
        if self.family:
            return self.family.children.all()
        return ChildProfile.objects.none()



    

'''

