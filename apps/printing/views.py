from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from decimal import Decimal
from .models import ShopPricingRule, PrintingService
from .serializers import ShopPricingRuleSerializer, PrintingServiceSerializer
from .pricing_calculator import calculate_document_cost
from apps.shops.models import PrintingShop


class ShopPricingListView(generics.ListAPIView):
    serializer_class = ShopPricingRuleSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shop_id = self.kwargs.get('shop_id')
        return ShopPricingRule.objects.filter(shop_id=shop_id, is_available=True)


class MyShopPricingManageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_shop(self):
        return PrintingShop.objects.filter(owner=self.request.user).first()

    def get(self, request):
        shop = self.get_shop()
        if not shop:
            return Response({"error": "No shop found for this user."}, status=status.HTTP_404_NOT_FOUND)
        rules = ShopPricingRule.objects.filter(shop=shop)
        return Response(ShopPricingRuleSerializer(rules, many=True).data)

    def put(self, request):
        shop = self.get_shop()
        if not shop:
            return Response({"error": "No shop found for this user."}, status=status.HTTP_404_NOT_FOUND)
        
        rules_data = request.data.get('rules', [])
        updated = []
        for r_data in rules_data:
            rule_id = r_data.get('id')
            if rule_id:
                try:
                    rule = ShopPricingRule.objects.get(id=rule_id, shop=shop)
                    if 'price_per_page' in r_data:
                        rule.price_per_page = Decimal(str(r_data['price_per_page']))
                    if 'is_available' in r_data:
                        rule.is_available = bool(r_data['is_available'])
                    rule.save()
                    updated.append(rule)
                except ShopPricingRule.DoesNotExist:
                    continue

        return Response(ShopPricingRuleSerializer(updated, many=True).data)


class ShopServicesListView(generics.ListAPIView):
    serializer_class = PrintingServiceSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shop_id = self.kwargs.get('shop_id')
        return PrintingService.objects.filter(shop_id=shop_id, is_active=True)


class MyShopServicesManageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_shop(self):
        return PrintingShop.objects.filter(owner=self.request.user).first()

    def get(self, request):
        shop = self.get_shop()
        if not shop:
            return Response({"error": "No shop found."}, status=status.HTTP_404_NOT_FOUND)
        services = PrintingService.objects.filter(shop=shop)
        return Response(PrintingServiceSerializer(services, many=True).data)

    def post(self, request):
        shop = self.get_shop()
        if not shop:
            return Response({"error": "No shop found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PrintingServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = serializer.save(shop=shop)
        return Response(PrintingServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class EstimateCostView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        shop_id = request.data.get('shop_id')
        items = request.data.get('items', [])

        if not shop_id or not items:
            return Response({"error": "shop_id and items list are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            shop = PrintingShop.objects.get(id=shop_id, status=PrintingShop.STATUS_APPROVED)
        except PrintingShop.DoesNotExist:
            return Response({"error": "Shop not found or not approved."}, status=status.HTTP_404_NOT_FOUND)

        subtotal = Decimal('0.00')
        breakdown = []

        for idx, item in enumerate(items):
            paper_size = item.get('paper_size', 'A4')
            color_mode = item.get('color_mode', 'bw')
            print_side = item.get('print_side', 'single')
            page_count = int(item.get('page_count', 1))
            copies = int(item.get('copies', 1))
            page_range = str(item.get('page_range', 'all') or 'all').strip()

            cost_res = calculate_document_cost(shop, paper_size, color_mode, print_side, page_count, copies, page_range=page_range)
            if not cost_res['success']:
                return Response({"error": f"Item {idx + 1}: {cost_res['error']}"}, status=status.HTTP_400_BAD_REQUEST)

            item_total = cost_res['calculated_total']
            subtotal += item_total
            breakdown.append({
                "index": idx,
                "paper_size": paper_size,
                "color_mode": color_mode,
                "print_side": print_side,
                "page_count": page_count,
                "page_range": cost_res.get('page_range', page_range),
                "effective_pages": cost_res.get('effective_pages', page_count),
                "document_pages": cost_res.get('document_pages', page_count),
                "physical_sheets": cost_res.get('physical_sheets', page_count),
                "sheets_per_copy": cost_res.get('sheets_per_copy', cost_res.get('physical_sheets', page_count)),
                "printed_sides": cost_res.get('printed_sides', page_count),
                "billable_units": cost_res.get('billable_units', page_count),
                "copies": copies,
                "unit_price": str(cost_res['unit_price']),
                "total_for_one_copy": str(cost_res.get('total_for_one_copy', cost_res['calculated_total'])),
                "calculated_total": str(item_total)
            })

        service_fee = Decimal('0.00')
        total = subtotal + service_fee

        return Response({
            "shop_id": shop.id,
            "shop_name": shop.name,
            "breakdown": breakdown,
            "subtotal": str(subtotal),
            "service_fee": str(service_fee),
            "total": str(total)
        })
