from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import date, time, timedelta

from apps.shops.models import PrintingShop, ShopStaffMembership, ShopOperatingHours
from apps.printing.models import ShopPricingRule, PrintingService
from apps.orders.models import PrintingOrder, OrderDocument, OrderStatusHistory, GlobalPickupSequence
from apps.payments.models import PaymentTransaction
from apps.notifications.models import Notification

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds local demonstration data for Univ Quick Print platform"

    def handle(self, *args, **options):
        self.stdout.write("Starting demonstration data seeding...")

        # 1. Create Administrator
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@univquickprint.ph",
                "first_name": "Admin",
                "last_name": "System",
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            }
        )
        if created:
            admin_user.set_password("AdminPass123!")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created admin user: admin / AdminPass123!"))

        # 2. Create Customers
        student_user, created = User.objects.get_or_create(
            username="student",
            defaults={
                "email": "student@university.example",
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "role": User.ROLE_CUSTOMER,
                "phone_number": "09171234567",
                "student_id": "CEBU-12048592"
            }
        )
        if created:
            student_user.set_password("StudentPass123!")
            student_user.save()
            self.stdout.write(self.style.SUCCESS("Created customer user: student / StudentPass123!"))

        maria_user, created = User.objects.get_or_create(
            username="maria",
            defaults={
                "email": "maria.santos@university.example",
                "first_name": "Maria",
                "last_name": "Santos",
                "role": User.ROLE_CUSTOMER,
                "phone_number": "09187654321",
                "student_id": "CEBU-2021-04921"
            }
        )
        if created:
            maria_user.set_password("MariaPass123!")
            maria_user.save()

        # 3. Create Shop Owners
        taft_owner, _ = User.objects.get_or_create(
            username="owner_taft",
            defaults={
                "email": "owner.taft@quickprint.ph",
                "first_name": "Eduardo",
                "last_name": "Reyes",
                "role": User.ROLE_SHOP_OWNER,
                "phone_number": "09191112233"
            }
        )
        taft_owner.set_password("OwnerPass123!")
        taft_owner.save()

        katipunan_owner, _ = User.objects.get_or_create(
            username="owner_katipunan",
            defaults={
                "email": "owner.katipunan@quickprint.ph",
                "first_name": "Grace",
                "last_name": "Lim",
                "role": User.ROLE_SHOP_OWNER,
                "phone_number": "09192223344"
            }
        )
        katipunan_owner.set_password("OwnerPass123!")
        katipunan_owner.save()

        espana_owner, _ = User.objects.get_or_create(
            username="owner_espana",
            defaults={
                "email": "owner.espana@quickprint.ph",
                "first_name": "Mateo",
                "last_name": "Bautista",
                "role": User.ROLE_SHOP_OWNER,
                "phone_number": "09193334455"
            }
        )
        espana_owner.set_password("OwnerPass123!")
        espana_owner.save()

        express_owner, _ = User.objects.get_or_create(
            username="owner_express",
            defaults={
                "email": "owner.express@quickprint.ph",
                "first_name": "Eduardo",
                "last_name": "Express",
                "role": User.ROLE_SHOP_OWNER,
                "phone_number": "09194445566"
            }
        )
        express_owner.set_password("OwnerPass123!")
        express_owner.save()

        corner_owner, _ = User.objects.get_or_create(
            username="owner_corner",
            defaults={
                "email": "owner.corner@quickprint.ph",
                "first_name": "Carlos",
                "last_name": "Corner",
                "role": User.ROLE_SHOP_OWNER,
                "phone_number": "09195556677"
            }
        )
        corner_owner.set_password("OwnerPass123!")
        corner_owner.save()

        # 4. Seed Demonstration Shops
        shops_data = [
            {
                "owner": taft_owner,
                "name": "Cebu Campus Print Hub",
                "description": "Fictional demo shop for university document printing, thesis binding, and copying in Cebu City.",
                "email": "cebu-campus@example.invalid",
                "phone_number": "032 000 0101",
                "address": "Fictional demo location near Cebu City campus",
                "city": "Cebu City",
                "barangay": "Demo District",
                "latitude": Decimal("10.3157000"),
                "longitude": Decimal("123.8854000"),
                "status": PrintingShop.STATUS_APPROVED,
                "opening_time": time(7, 30),
                "closing_time": time(19, 30),
                "operating_days": "Monday - Saturday",
                "pickup_slot_interval_minutes": 30,
                "slot_capacity": 6,
            },
            {
                "owner": katipunan_owner,
                "name": "Queen City Quick Prints",
                "description": "Fictional demo shop serving Cebu students with document printing and lamination.",
                "email": "queen-city@example.invalid",
                "phone_number": "032 000 0102",
                "address": "Fictional demo location near Lahug",
                "city": "Cebu City",
                "barangay": "Demo District",
                "latitude": Decimal("10.3380000"),
                "longitude": Decimal("123.9020000"),
                "status": PrintingShop.STATUS_APPROVED,
                "opening_time": time(8, 0),
                "closing_time": time(20, 0),
                "operating_days": "Monday - Saturday",
                "pickup_slot_interval_minutes": 30,
                "slot_capacity": 8,
            },
            {
                "owner": espana_owner,
                "name": "Sugbo Student Print Center",
                "description": "Fictional demo shop for reviewers, thesis printing, and rush student documents in Cebu City.",
                "email": "sugbo-student@example.invalid",
                "phone_number": "032 000 0103",
                "address": "Fictional demo location near Guadalupe",
                "city": "Cebu City",
                "barangay": "Demo District",
                "latitude": Decimal("10.3020000"),
                "longitude": Decimal("123.8950000"),
                "status": PrintingShop.STATUS_PENDING,
                "opening_time": time(7, 0),
                "closing_time": time(19, 0),
                "operating_days": "Monday - Saturday",
                "pickup_slot_interval_minutes": 20,
                "slot_capacity": 5,
            },
            {
                "owner": express_owner,
                "name": "Cebu Document Express",
                "description": "Fictional demo shop application awaiting approval in Cebu City.",
                "email": "cebu-document@example.invalid",
                "phone_number": "032 000 0104",
                "address": "Fictional demo location near Mandaue boundary",
                "city": "Cebu City",
                "barangay": "Demo District",
                "latitude": Decimal("10.3450000"),
                "longitude": Decimal("123.9500000"),
                "status": PrintingShop.STATUS_PENDING,
                "opening_time": time(8, 0),
                "closing_time": time(18, 0),
                "operating_days": "Monday - Friday",
                "pickup_slot_interval_minutes": 30,
                "slot_capacity": 4,
            },
            {
                "owner": corner_owner,
                "name": "University Print Corner Cebu",
                "description": "Fictional demo shop temporarily suspended for administrator testing.",
                "email": "cebu-corner@example.invalid",
                "phone_number": "032 000 0105",
                "address": "Fictional demo location near Banilad",
                "city": "Cebu City",
                "barangay": "Demo District",
                "latitude": Decimal("10.3550000"),
                "longitude": Decimal("123.9100000"),
                "status": PrintingShop.STATUS_SUSPENDED,
                "opening_time": time(8, 30),
                "closing_time": time(17, 30),
                "operating_days": "Monday - Friday",
                "pickup_slot_interval_minutes": 30,
                "slot_capacity": 4,
            }
        ]

        legacy_demo_names = {
            "QuickPrint DLSU Taft": "Cebu Campus Print Hub",
            "Katipunan Blue Prints & Copy Hub": "Queen City Quick Prints",
            "Thomasians Copy & Print Station": "Sugbo Student Print Center",
            "Campus Graphics Hub (Pending)": "Cebu Document Express",
            "Cebu Document Express (Pending)": "Cebu Document Express",
        }
        for old_name, new_name in legacy_demo_names.items():
            PrintingShop.objects.filter(
                name=old_name,
            ).update(name=new_name)

        created_shops = []
        for s_info in shops_data:
            shop, created = PrintingShop.objects.get_or_create(
                name=s_info["name"],
                defaults=s_info
            )
            if not created:
                for field, value in s_info.items():
                    setattr(shop, field, value)
                shop.save()
            created_shops.append(shop)

            # Pricing rules
            pricing_matrix = [
                ('A4', 'bw', 'single', Decimal('1.50')),
                ('A4', 'bw', 'double', Decimal('2.50')),
                ('A4', 'color', 'single', Decimal('5.00')),
                ('A4', 'color', 'double', Decimal('9.00')),
                ('Letter', 'bw', 'single', Decimal('1.50')),
                ('Letter', 'bw', 'double', Decimal('2.50')),
                ('Letter', 'color', 'single', Decimal('5.00')),
                ('Letter', 'color', 'double', Decimal('9.00')),
                ('Legal', 'bw', 'single', Decimal('2.00')),
                ('Legal', 'bw', 'double', Decimal('3.50')),
                ('Legal', 'color', 'single', Decimal('6.00')),
                ('Legal', 'color', 'double', Decimal('11.00')),
            ]
            for paper, color, side, price in pricing_matrix:
                ShopPricingRule.objects.get_or_create(
                    shop=shop,
                    paper_size=paper,
                    color_mode=color,
                    print_side=side,
                    defaults={"price_per_page": price, "is_available": True}
                )

            # Services
            services = [
                ("Document & PDF Printing", "Crisp laser printing for handouts, research papers, and assignments.", Decimal('1.50')),
                ("Hardbound & Ring Binding", "Professional ring binding, thermal tape, and hardbound thesis with gold stamping.", Decimal('50.00')),
                ("Document Lamination", "High-clarity plastic lamination for identification cards, menus, and certificates.", Decimal('25.00')),
            ]
            for s_name, s_desc, s_base in services:
                PrintingService.objects.get_or_create(
                    shop=shop,
                    name=s_name,
                    defaults={"description": s_desc, "base_price": s_base, "is_active": True}
                )

            # Operating hours (7 days)
            for day_idx in range(7):
                is_open = day_idx < 6 if "Saturday" in shop.operating_days else day_idx < 5
                ShopOperatingHours.objects.update_or_create(
                    shop=shop,
                    day_of_week=day_idx,
                    defaults={
                        "is_open": is_open,
                        "opening_time": shop.opening_time,
                        "closing_time": shop.closing_time,
                    }
                )

        # 5. Initialize Global Pickup Sequence with initial demonstration orders
        primary_shop = created_shops[0]  # Cebu Campus Print Hub
        tomorrow = (timezone.now() + timedelta(days=1)).date()

        # Demonstration Order 1: Accepted with Pickup Code UQP01
        order1, _ = PrintingOrder.objects.get_or_create(
            order_number="UQP-DEMO-001",
            defaults={
                "customer": student_user,
                "shop": primary_shop,
                "status": PrintingOrder.STATUS_READY_FOR_PICKUP,
                "payment_status": PrintingOrder.PAYMENT_STATUS_PAID,
                "subtotal_amount": Decimal("45.00"),
                "service_fee": Decimal("0.00"),
                "total_amount": Decimal("45.00"),
                "instructions": "Please staple top-left corner. Needs clean margins.",
                "pickup_date": tomorrow,
                "pickup_time_slot": "10:00 AM - 10:30 AM",
                "pickup_code": "UQP01"
            }
        )
        if not order1.documents.exists():
            OrderDocument.objects.create(
                order=order1,
                original_filename="Thesis_Chapter_1_Introduction.pdf",
                file_size=204800,
                page_count=15,
                paper_size="A4",
                color_mode="bw",
                print_side="single",
                copies=2,
                unit_price=Decimal("1.50"),
                calculated_total=Decimal("45.00")
            )
            OrderStatusHistory.objects.create(order=order1, status="submitted", notes="Order submitted by student.")
            OrderStatusHistory.objects.create(order=order1, status="accepted", notes="Accepted with code UQP01.")
            OrderStatusHistory.objects.create(order=order1, status="printing", notes="Printing started.")
            OrderStatusHistory.objects.create(order=order1, status="ready_for_pickup", notes="Packaged and ready for counter pickup.")

            PaymentTransaction.objects.create(
                order=order1,
                user=student_user,
                payment_method="gcash",
                transaction_reference="TXN-GCASH-DEMO001",
                amount=Decimal("45.00"),
                status=PaymentTransaction.STATUS_SUCCESS,
                simulated_mode=True,
                notes="Sandbox GCash payment successful."
            )

        # Demonstration Order 2: Accepted with Pickup Code UQP02
        order2, _ = PrintingOrder.objects.get_or_create(
            order_number="UQP-DEMO-002",
            defaults={
                "customer": maria_user,
                "shop": created_shops[1],  # Queen City Quick Prints
                "status": PrintingOrder.STATUS_ACCEPTED,
                "payment_status": PrintingOrder.PAYMENT_STATUS_PAID,
                "subtotal_amount": Decimal("90.00"),
                "service_fee": Decimal("0.00"),
                "total_amount": Decimal("90.00"),
                "instructions": "Full color presentation slides.",
                "pickup_date": tomorrow,
                "pickup_time_slot": "02:00 PM - 02:30 PM",
                "pickup_code": "UQP02"
            }
        )
        if not order2.documents.exists():
            OrderDocument.objects.create(
                order=order2,
                original_filename="Project_Deck_Final.pdf",
                file_size=1048576,
                page_count=10,
                paper_size="A4",
                color_mode="color",
                print_side="double",
                copies=2,
                unit_price=Decimal("9.00"),
                calculated_total=Decimal("90.00")
            )
            OrderStatusHistory.objects.create(order=order2, status="submitted")
            OrderStatusHistory.objects.create(order=order2, status="accepted", notes="Accepted with code UQP02.")

            PaymentTransaction.objects.create(
                order=order2,
                user=maria_user,
                payment_method="maya",
                transaction_reference="TXN-MAYA-DEMO002",
                amount=Decimal("90.00"),
                status=PaymentTransaction.STATUS_SUCCESS,
                simulated_mode=True,
                notes="Sandbox Maya payment successful."
            )

        # Update GlobalPickupSequence to 2 so next order gets UQP03
        seq, _ = GlobalPickupSequence.objects.get_or_create(id=1)
        if seq.last_number < 2:
            seq.last_number = 2
            seq.save()

        # Seed Notifications
        student_notification, _ = Notification.objects.get_or_create(
            recipient=student_user,
            title="Order Ready for Pickup!",
            defaults={
                "message": "Your order #UQP-DEMO-001 is ready for pickup! Present code UQP01 at Cebu Campus Print Hub.",
                "notification_type": Notification.TYPE_READY_FOR_PICKUP,
                "link": f"/tracking/{order1.id}",
                "is_read": False
            }
        )
        student_notification.message = "Your order #UQP-DEMO-001 is ready for pickup! Present code UQP01 at Cebu Campus Print Hub."
        student_notification.link = f"/tracking/{order1.id}"
        student_notification.save(update_fields=["message", "link"])

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully!"))
        self.stdout.write("---------------------------------------------")
        self.stdout.write("Admin:        admin / AdminPass123!")
        self.stdout.write("Customer 1:   student / StudentPass123!")
        self.stdout.write("Customer 2:   maria / MariaPass123!")
        self.stdout.write("Shop Owner 1: owner_taft / OwnerPass123!")
        self.stdout.write("Shop Owner 2: owner_katipunan / OwnerPass123!")
        self.stdout.write("Shop Owner 3: owner_espana / OwnerPass123!")
        self.stdout.write("Shop Owner 4: owner_express / OwnerPass123!")
        self.stdout.write("Shop Owner 5: owner_corner / OwnerPass123!")
        self.stdout.write("---------------------------------------------")
