import math
from decimal import Decimal
from apps.printing.models import ShopPricingRule
from apps.shops.models import PrintingShop
from apps.orders.document_inspector import parse_and_validate_page_range, DocumentInspectionError


def calculate_document_cost(
    shop: PrintingShop,
    paper_size: str,
    color_mode: str,
    print_side: str,
    page_count: int,
    copies: int,
    page_range: str = 'all'
):
    """
    Authoritative pricing calculator for a document based on shop pricing rules.
    Accurately accounts for:
      - Document pages: total digital pages in the uploaded document.
      - Selected page range: specific subset of pages to print.
      - Effective pages: count of pages included in the selected range.
      - Physical sheets of paper: ceil(effective_pages / 2) for double-sided; effective_pages for single-sided.
      - Billable printed sides: effective_pages printed.
      - Billable units: charged per sheet for double-sided printing, or per page for single-sided.
    """
    if page_count <= 0:
        return {
            "success": False,
            "error": "Document page count must be greater than zero."
        }

    if copies <= 0:
        return {
            "success": False,
            "error": "Number of copies must be at least 1."
        }

    # Validate and calculate effective pages from page_range
    try:
        _, effective_pages = parse_and_validate_page_range(page_range, int(page_count))
    except DocumentInspectionError as e:
        return {
            "success": False,
            "error": str(e)
        }

    rule = ShopPricingRule.objects.filter(
        shop=shop,
        paper_size=paper_size,
        color_mode=color_mode,
        print_side=print_side,
        is_available=True
    ).first()

    if not rule:
        mode_label = "Color" if color_mode == 'color' else "Black & White"
        side_label = "Double-Sided" if print_side == 'double' else "Single-Sided"
        return {
            "success": False,
            "error": f"{shop.name} does not support {paper_size} {mode_label} ({side_label}) printing."
        }

    unit_price = Decimal(str(rule.price_per_page))

    # Distinguish physical sheets vs printed sides based on effective pages
    document_pages = int(page_count)
    if print_side == 'double':
        physical_sheets = math.ceil(effective_pages / 2) * int(copies)
        sheets_per_copy = math.ceil(effective_pages / 2)
        billable_units = sheets_per_copy
    else:
        physical_sheets = effective_pages * int(copies)
        sheets_per_copy = effective_pages
        billable_units = effective_pages

    printed_sides = effective_pages * int(copies)

    total_for_one_copy = unit_price * Decimal(billable_units)
    grand_total = total_for_one_copy * Decimal(copies)

    return {
        "success": True,
        "rule_id": rule.id,
        "unit_price": unit_price,
        "document_pages": document_pages,
        "page_range": page_range or 'all',
        "effective_pages": effective_pages,
        "physical_sheets": physical_sheets,
        "sheets_per_copy": sheets_per_copy,
        "printed_sides": printed_sides,
        "billable_units": billable_units,
        "total_for_one_copy": total_for_one_copy,
        "calculated_total": grand_total,
        "paper_size": paper_size,
        "color_mode": color_mode,
        "print_side": print_side,
        "copies": copies
    }
