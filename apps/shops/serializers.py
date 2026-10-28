from rest_framework import serializers
from .models import PrintingShop, ShopStaffMembership, ShopOperatingHours, ShopReview, ShopApplicationAuditLog
from apps.printing.models import ShopPricingRule, PrintingService
from apps.accounts.serializers import UserSerializer


class ShopApplicationAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True)

    class Meta:
        model = ShopApplicationAuditLog
        fields = ['id', 'actor', 'actor_name', 'action', 'from_status', 'to_status', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']


class ShopPricingRuleSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopPricingRule
        fields = ['id', 'paper_size', 'color_mode', 'print_side', 'price_per_page', 'is_available']


class PrintingServiceSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrintingService
        fields = ['id', 'name', 'description', 'base_price', 'is_active']


class ShopOperatingHoursSerializer(serializers.ModelSerializer):
    day_name = serializers.SerializerMethodField()

    class Meta:
        model = ShopOperatingHours
        fields = ['id', 'day_of_week', 'day_name', 'is_open', 'opening_time', 'closing_time']

    def get_day_name(self, obj):
        return dict(ShopOperatingHours.DAY_CHOICES).get(obj.day_of_week, '')


class ShopReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField(source='customer.full_name')
    order_number = serializers.ReadOnlyField(source='order.order_number')

    class Meta:
        model = ShopReview
        fields = [
            'id', 'shop', 'customer_name', 'order', 'order_number',
            'rating', 'review_text', 'is_moderated', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'customer_name', 'order_number', 'is_moderated', 'created_at', 'updated_at']


class PrintingShopListSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(source='is_currently_open', read_only=True)
    distance_km = serializers.SerializerMethodField()
    starting_price = serializers.SerializerMethodField()
    services_summary = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()

    class Meta:
        model = PrintingShop
        fields = [
            'id', 'name', 'description', 'address', 'city', 'barangay',
            'latitude', 'longitude', 'phone_number', 'email', 'image',
            'status', 'opening_time', 'closing_time', 'operating_days',
            'is_open', 'distance_km', 'starting_price', 'services_summary',
            'average_rating', 'review_count'
        ]

    def get_distance_km(self, obj):
        user_lat = self.context.get('user_lat')
        user_lng = self.context.get('user_lng')
        if user_lat is not None and user_lng is not None:
            return obj.distance_from(user_lat, user_lng)
        return None

    def get_starting_price(self, obj):
        rules = getattr(obj, '_prefetched_objects_cache', {}).get('pricing_rules')
        if rules is not None:
            available = [r for r in rules if r.is_available]
        else:
            available = list(obj.pricing_rules.filter(is_available=True))
        if available:
            return min(r.price_per_page for r in available)
        return None

    def get_services_summary(self, obj):
        services = getattr(obj, '_prefetched_objects_cache', {}).get('services')
        if services is not None:
            active = [s.name for s in services if s.is_active]
        else:
            active = list(obj.services.filter(is_active=True).values_list('name', flat=True))
        return active[:4]


class PrintingShopDetailSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(source='is_currently_open', read_only=True)
    pricing_rules = ShopPricingRuleSimpleSerializer(many=True, read_only=True)
    services = PrintingServiceSimpleSerializer(many=True, read_only=True)
    operating_hours = ShopOperatingHoursSerializer(many=True, read_only=True)
    audit_logs = ShopApplicationAuditLogSerializer(many=True, read_only=True)
    owner = UserSerializer(read_only=True)
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()

    class Meta:
        model = PrintingShop
        fields = [
            'id', 'owner', 'name', 'description', 'email', 'phone_number',
            'address', 'city', 'barangay', 'latitude', 'longitude', 'image',
            'government_id', 'business_permit', 'proof_of_ownership',
            'status', 'rejection_reason', 'is_active',
            'opening_time', 'closing_time', 'operating_days',
            'pickup_slot_interval_minutes', 'slot_capacity',
            'is_open', 'average_rating', 'review_count', 'pricing_rules',
            'services', 'operating_hours', 'audit_logs', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'rejection_reason', 'created_at', 'owner']


class ShopRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrintingShop
        fields = [
            'name', 'description', 'email', 'phone_number',
            'address', 'city', 'barangay', 'latitude', 'longitude',
            'image', 'government_id', 'business_permit', 'proof_of_ownership',
            'opening_time', 'closing_time', 'operating_days'
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        # Prevent duplicate/conflicting active applications
        existing_active = PrintingShop.objects.filter(
            owner=user,
            status__in=[PrintingShop.STATUS_PENDING, PrintingShop.STATUS_UNDER_REVIEW, PrintingShop.STATUS_APPROVED]
        ).first()
        if existing_active:
            if existing_active.status == PrintingShop.STATUS_APPROVED:
                raise serializers.ValidationError("You already own an active, approved printing shop.")
            else:
                raise serializers.ValidationError("You already have a pending printing shop application awaiting administrator review.")
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        # The user role is NOT upgraded here. The applicant remains a CUSTOMER
        # until an administrator verifies the identity documents and approves the shop.
        shop = PrintingShop.objects.create(
            owner=user,
            status=PrintingShop.STATUS_PENDING,
            **validated_data
        )

        # Record audit log entry
        ShopApplicationAuditLog.objects.create(
            shop=shop,
            actor=user,
            action='submitted',
            from_status='',
            to_status=PrintingShop.STATUS_PENDING,
            notes='Printing shop application and verification documents submitted by customer.'
        )

        # Create default pricing rules for new shop
        default_rules = [
            ('A4', 'bw', 'single', 1.50),
            ('A4', 'bw', 'double', 2.50),
            ('A4', 'color', 'single', 5.00),
            ('A4', 'color', 'double', 9.00),
            ('Letter', 'bw', 'single', 1.50),
            ('Letter', 'bw', 'double', 2.50),
            ('Letter', 'color', 'single', 5.00),
            ('Letter', 'color', 'double', 9.00),
            ('Legal', 'bw', 'single', 2.00),
            ('Legal', 'bw', 'double', 3.50),
            ('Legal', 'color', 'single', 6.00),
            ('Legal', 'color', 'double', 11.00),
        ]
        for paper, color, side, price in default_rules:
            ShopPricingRule.objects.create(
                shop=shop,
                paper_size=paper,
                color_mode=color,
                print_side=side,
                price_per_page=price
            )

        # Default services
        PrintingService.objects.bulk_create([
            PrintingService(shop=shop, name='Document Printing', description='Black & white or vibrant full-color document printing.'),
            PrintingService(shop=shop, name='Booklet & Thesis Binding', description='Spiral, ring, or hardbound thesis binding options.'),
            PrintingService(shop=shop, name='Document Lamination', description='Durable heat-pressed lamination for IDs, certificates, and badges.')
        ])

        return shop
