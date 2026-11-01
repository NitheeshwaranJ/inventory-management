
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Count, F, Q, Sum, DecimalField, ExpressionWrapper
from orders.models import Order, OrderItem
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate

from .models import Order
from django.db.models import Count, Q, Sum

from .models import Order


def get_order_summary():
    """
    Return order counts and revenue from currently placed orders.
    Cancelled orders are excluded from revenue.
    """

    summary = Order.objects.aggregate(
        total_orders=Count("id"),
        placed_orders=Count(
            "id",
            filter=Q(status=Order.Status.PLACED),
        ),
        cancelled_orders=Count(
            "id",
            filter=Q(status=Order.Status.CANCELLED),
        ),
        placed_revenue=Sum(
            "total_amount",
            filter=Q(status=Order.Status.PLACED),
        ),
    )

    # Sum returns None when there are no matching orders.
    summary["placed_revenue"] = (
        summary["placed_revenue"] or Decimal("0.00")
    )

    return summary



def get_daily_sales_report(start_date, end_date):
    """
    Return daily order counts and placed-order revenue
    for an inclusive date range. Days without orders
    are included with zero values.
    """

    if not isinstance(start_date, date) or isinstance(start_date, type(None)):
        raise ValidationError("start_date must be a date.")

    if not isinstance(end_date, date):
        raise ValidationError("end_date must be a date.")

    if start_date > end_date:
        raise ValidationError("start_date cannot be after end_date.")

    daily_rows = (
        Order.objects
        .filter(created_at__date__range=(start_date, end_date))
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            total_orders=Count("id"),
            placed_orders=Count(
                "id",
                filter=Q(status=Order.Status.PLACED),
            ),
            cancelled_orders=Count(
                "id",
                filter=Q(status=Order.Status.CANCELLED),
            ),
            placed_revenue=Sum(
                "total_amount",
                filter=Q(status=Order.Status.PLACED),
            ),
        )
        .order_by("day")
    )

    # Convert database results to a date-keyed dictionary.
    rows_by_date = {
        row["day"]: row for row in daily_rows
    }

    report = []
    current_date = start_date

    while current_date <= end_date:
        row = rows_by_date.get(current_date, {})

        report.append({
            "date": current_date,
            "total_orders": row.get("total_orders", 0),
            "placed_orders": row.get("placed_orders", 0),
            "cancelled_orders": row.get("cancelled_orders", 0),
            "placed_revenue": (
                row.get("placed_revenue") or Decimal("0.00")
            ),
        })

        current_date += timedelta(days=1)

    return report

def get_product_performance_report():
    """
    Return sales performance for products in placed orders.

    Cancelled orders are excluded.
    Products without placed-order sales are omitted.
    """

    line_sales = ExpressionWrapper(
        F("quantity") * F("unit_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    return list(
        OrderItem.objects
        .filter(order__status=Order.Status.PLACED)
        .values(
            "product_id",
            "product__sku",
            "product__name",
        )
        .annotate(
            quantity_sold=Sum("quantity"),
            sales_value=Sum(line_sales),
            order_count=Count("order_id", distinct=True),
        )
        .order_by("-quantity_sold", "product__name")
    )

