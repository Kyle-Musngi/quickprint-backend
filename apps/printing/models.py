from django.db import models
from apps.shops.models import PrintingShop


class ShopPricingRule(models.Model):
    PAPER_SIZE_A4 = 'A4'
    PAPER_SIZE_LETTER = 'Letter'
    PAPER_SIZE_LEGAL = 'Legal'
    PAPER_SIZE_CHOICES = (
        (PAPER_SIZE_A4, 'A4 (8.27 x 11.69 in)'),
        (PAPER_SIZE_LETTER, 'Letter / Short (8.5 x 11 in)'),
        (PAPER_SIZE_LEGAL, 'Legal / Long (8.5 x 14 in)'),
    )

    COLOR_MODE_BW = 'bw'
    COLOR_MODE_COLOR = 'color'
    COLOR_MODE_CHOICES = (
        (COLOR_MODE_BW, 'Black & White'),
        (COLOR_MODE_COLOR, 'Colored'),
    )

    PRINT_SIDE_SINGLE = 'single'
    PRINT_SIDE_DOUBLE = 'double'
    PRINT_SIDE_CHOICES = (
        (PRINT_SIDE_SINGLE, 'Single-Sided'),
        (PRINT_SIDE_DOUBLE, 'Double-Sided'),
    )

    shop = models.ForeignKey(PrintingShop, on_delete=models.CASCADE, related_name='pricing_rules')
    paper_size = models.CharField(max_length=20, choices=PAPER_SIZE_CHOICES)
    color_mode = models.CharField(max_length=10, choices=COLOR_MODE_CHOICES)
    print_side = models.CharField(max_length=10, choices=PRINT_SIDE_CHOICES)
    price_per_page = models.DecimalField(max_digits=7, decimal_places=2)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('shop', 'paper_size', 'color_mode', 'print_side')
        ordering = ['paper_size', 'color_mode', 'print_side']

    def __str__(self):
        return f"{self.shop.name} | {self.paper_size} {self.color_mode} {self.print_side}: ₱{self.price_per_page}"


class PrintingService(models.Model):
    shop = models.ForeignKey(PrintingShop, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    base_price = models.DecimalField(max_digits=7, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.shop.name})"
