from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CUSTOMER = 'customer'
    ROLE_SHOP_OWNER = 'shop_owner'
    ROLE_SHOP_STAFF = 'shop_staff'
    ROLE_ADMIN = 'admin'

    ROLE_CHOICES = (
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_SHOP_OWNER, 'Shop Owner'),
        (ROLE_SHOP_STAFF, 'Shop Staff'),
        (ROLE_ADMIN, 'Administrator'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)
    phone_number = models.CharField(max_length=20, blank=True, default='')
    student_id = models.CharField(max_length=50, blank=True, default='')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.username

    def is_customer(self):
        return self.role == self.ROLE_CUSTOMER

    def is_shop_owner(self):
        return self.role == self.ROLE_SHOP_OWNER

    def is_shop_staff(self):
        return self.role in [self.ROLE_SHOP_OWNER, self.ROLE_SHOP_STAFF]

    def is_platform_admin(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser
