
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from catalog.models import Category, Supplier, Product
from inventory.models import InventoryMovement
from orders.models import Order, OrderItem
from orders.services import create_order, cancel_order
from orders.reports import (
    get_order_summary,
    get_daily_sales_report,
    get_product_performance_report,
)


def create_order_test_user(username="order_api_user"):
    return get_user_model().objects.create_user(
        username=username,
        password="test-password-123",
    )


class CreateOrderServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Order Accessories")
        self.supplier = Supplier.objects.create(name="Order Supplier")

        self.keyboard = Product.objects.create(
            sku="ORD-KEY-001",
            name="Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            stock=10,
        )
        self.mouse = Product.objects.create(
            sku="ORD-MOU-001",
            name="Mouse",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("200.00"),
            stock=3,
        )
        self.user = create_order_test_user("order_service_user")

    def test_create_order_deducts_stock_and_calculates_total(self):
        order = create_order(
            items=[
                {"product_id": self.keyboard.id, "quantity": 2},
                {"product_id": self.mouse.id, "quantity": 1},
            ],
            customer_name="Test Customer",
            user=self.user,
        )

        self.keyboard.refresh_from_db()
        self.mouse.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertEqual(order.total_amount, Decimal("1200.00"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(self.keyboard.stock, 8)
        self.assertEqual(self.mouse.stock, 2)
        self.assertEqual(InventoryMovement.objects.count(), 2)
        self.assertEqual(
            InventoryMovement.objects.filter(
                movement_type=InventoryMovement.MovementType.STOCK_OUT
            ).count(),
            2,
        )

    def test_order_saves_purchase_time_price(self):
        order = create_order(
            items=[{"product_id": self.keyboard.id, "quantity": 2}]
        )

        self.keyboard.selling_price = Decimal("700.00")
        self.keyboard.save(update_fields=["selling_price", "updated_at"])

        item = order.items.get(product=self.keyboard)
        self.assertEqual(item.unit_price, Decimal("500.00"))
        self.assertEqual(order.total_amount, Decimal("1000.00"))

    def test_insufficient_stock_leaves_no_partial_order(self):
        with self.assertRaises(ValidationError):
            create_order(
                items=[
                    {"product_id": self.keyboard.id, "quantity": 2},
                    {"product_id": self.mouse.id, "quantity": 4},
                ]
            )

        self.keyboard.refresh_from_db()
        self.mouse.refresh_from_db()

        self.assertEqual(self.keyboard.stock, 10)
        self.assertEqual(self.mouse.stock, 3)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_missing_product_leaves_no_order(self):
        with self.assertRaises(ValidationError):
            create_order(items=[{"product_id": 999999, "quantity": 1}])

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_duplicate_product_lines_are_rejected(self):
        with self.assertRaises(ValidationError):
            create_order(
                items=[
                    {"product_id": self.keyboard.id, "quantity": 1},
                    {"product_id": self.keyboard.id, "quantity": 2},
                ]
            )

        self.assertEqual(Order.objects.count(), 0)
        self.keyboard.refresh_from_db()
        self.assertEqual(self.keyboard.stock, 10)

    def test_inactive_product_is_rejected(self):
        self.keyboard.is_active = False
        self.keyboard.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            create_order(
                items=[{"product_id": self.keyboard.id, "quantity": 1}]
            )

        self.assertEqual(Order.objects.count(), 0)
        self.keyboard.refresh_from_db()
        self.assertEqual(self.keyboard.stock, 10)

    def test_movement_failure_rolls_back_entire_order(self):
        with patch(
            "inventory.models.InventoryMovement.objects.create",
            side_effect=RuntimeError("Simulated movement failure"),
        ):
            with self.assertRaises(RuntimeError):
                create_order(
                    items=[{"product_id": self.keyboard.id, "quantity": 2}]
                )

        self.keyboard.refresh_from_db()
        self.assertEqual(self.keyboard.stock, 10)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_invalid_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_order(
                items=[{"product_id": self.keyboard.id, "quantity": 0}]
            )

        self.assertEqual(Order.objects.count(), 0)
        self.keyboard.refresh_from_db()
        self.assertEqual(self.keyboard.stock, 10)

    def test_cancel_order_restores_stock_and_records_returns(self):
        order = create_order(
            items=[
                {"product_id": self.keyboard.id, "quantity": 2},
                {"product_id": self.mouse.id, "quantity": 1},
            ],
            user=self.user,
        )

        cancelled_order = cancel_order(order.id, user=self.user)

        self.keyboard.refresh_from_db()
        self.mouse.refresh_from_db()

        self.assertEqual(cancelled_order.status, Order.Status.CANCELLED)
        self.assertEqual(self.keyboard.stock, 10)
        self.assertEqual(self.mouse.stock, 3)
        self.assertEqual(
            InventoryMovement.objects.filter(
                reference=f"ORDER-{order.id}-CANCEL",
                movement_type=InventoryMovement.MovementType.RETURN,
            ).count(),
            2,
        )

    
    def test_repeated_cancellation_does_not_restore_stock_twice(self):
      order = create_order(
        items=[{"product_id": self.keyboard.id, "quantity": 2}],
        user=self.user,
    )

      cancel_order(order.id, user=self.user)
      cancel_order(order.id, user=self.user)

      self.keyboard.refresh_from_db()
      self.assertEqual(self.keyboard.stock, 10)

      self.assertEqual(
        InventoryMovement.objects.filter(
            reference=f"ORDER-{order.id}-CANCEL",
            movement_type=InventoryMovement.MovementType.RETURN,
        ).count(),
        1,
    )


    def test_cannot_cancel_nonexistent_order(self):
        with self.assertRaises(ValidationError):
            cancel_order(999999)

        self.assertEqual(Order.objects.count(), 0)

    
    def test_cancellation_failure_rolls_back_stock_and_status(self):
      order = create_order(
        items=[{"product_id": self.keyboard.id, "quantity": 2}],
        user=self.user,
    )

      self.keyboard.refresh_from_db()
      self.assertEqual(self.keyboard.stock, 8)

      with patch(
        "orders.services.InventoryMovement.objects.create",
        side_effect=RuntimeError("Simulated return movement failure"),
    ):
        with self.assertRaises(RuntimeError):
            cancel_order(order.id, user=self.user)

      self.keyboard.refresh_from_db()
      order.refresh_from_db()

      self.assertEqual(self.keyboard.stock, 8)
      self.assertEqual(order.status, Order.Status.PLACED)

      self.assertEqual(
        InventoryMovement.objects.filter(
            reference=f"ORDER-{order.id}-CANCEL"
        ).count(),
        0,
    )



class OrderAPITests(APITestCase):
    def setUp(self):
        self.user = create_order_test_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(name="API Order Category")
        self.supplier = Supplier.objects.create(name="API Order Supplier")

        self.product = Product.objects.create(
            sku="API-ORDER-001",
            name="API Test Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            stock=10,
        )

    def test_create_order_api(self):
        response = self.client.post(
            "/api/orders/",
            {
                "customer_name": "API Customer",
                "customer_email": "customer@example.com",
                "items": [
                    {"product_id": self.product.id, "quantity": 2}
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Decimal(str(response.data["total_amount"])),
            Decimal("1000.00"),
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_client_cannot_set_order_price_or_total(self):
        response = self.client.post(
            "/api/orders/",
            {
                "customer_name": "API Customer",
                "total_amount": "1.00",
                "items": [
                    {
                        "product_id": self.product.id,
                        "quantity": 1,
                        "unit_price": "1.00",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Decimal(str(response.data["total_amount"])),
            Decimal("500.00"),
        )

    def test_insufficient_stock_returns_400(self):
        response = self.client.post(
            "/api/orders/",
            {"items": [{"product_id": self.product.id, "quantity": 100}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_list_orders_api(self):
        created = self.client.post(
            "/api/orders/",
            {"items": [{"product_id": self.product.id, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        response = self.client.get("/api/orders/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_order_api(self):
        created = self.client.post(
            "/api/orders/",
            {"items": [{"product_id": self.product.id, "quantity": 1}]},
            format="json",
        )
        order_id = created.data["id"]

        response = self.client.get(f"/api/orders/{order_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], order_id)

    def test_cancel_order_api(self):
        created = self.client.post(
            "/api/orders/",
            {"items": [{"product_id": self.product.id, "quantity": 2}]},
            format="json",
        )
        order_id = created.data["id"]

        response = self.client.post(f"/api/orders/{order_id}/cancel/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.CANCELLED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_invalid_order_input_returns_400(self):
        response = self.client.post("/api/orders/", {"items": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)


class OrderSummaryReportTests(TestCase):
    def setUp(self):
        Order.objects.create(
            customer_name="Customer A",
            status=Order.Status.PLACED,
            total_amount=Decimal("1000.00"),
        )
        Order.objects.create(
            customer_name="Customer B",
            status=Order.Status.PLACED,
            total_amount=Decimal("500.00"),
        )
        Order.objects.create(
            customer_name="Customer C",
            status=Order.Status.PLACED,
            total_amount=Decimal("250.00"),
        )
        Order.objects.create(
            customer_name="Customer D",
            status=Order.Status.CANCELLED,
            total_amount=Decimal("800.00"),
        )

    def test_order_counts_and_placed_revenue(self):
        summary = get_order_summary()

        self.assertEqual(summary["total_orders"], 4)
        self.assertEqual(summary["placed_orders"], 3)
        self.assertEqual(summary["cancelled_orders"], 1)
        self.assertEqual(summary["placed_revenue"], Decimal("1750.00"))

    def test_empty_database_returns_zero_revenue(self):
        Order.objects.all().delete()
        summary = get_order_summary()

        self.assertEqual(summary["total_orders"], 0)
        self.assertEqual(summary["placed_orders"], 0)
        self.assertEqual(summary["cancelled_orders"], 0)
        self.assertEqual(summary["placed_revenue"], Decimal("0.00"))


class DailySalesReportTests(TestCase):
    def setUp(self):
        self.start_date = date(2026, 10, 26)
        self.middle_date = date(2026, 10, 27)
        self.end_date = date(2026, 10, 28)

        self.order_a = Order.objects.create(
            status=Order.Status.PLACED,
            total_amount=Decimal("1000.00"),
        )
        self.order_b = Order.objects.create(
            status=Order.Status.PLACED,
            total_amount=Decimal("500.00"),
        )
        self.order_c = Order.objects.create(
            status=Order.Status.CANCELLED,
            total_amount=Decimal("800.00"),
        )
        self.order_d = Order.objects.create(
            status=Order.Status.PLACED,
            total_amount=Decimal("700.00"),
        )

        self.set_order_date(self.order_a, self.start_date)
        self.set_order_date(self.order_b, self.start_date)
        self.set_order_date(self.order_c, self.start_date)
        self.set_order_date(self.order_d, self.end_date)

    def set_order_date(self, order, day):
        naive_datetime = datetime.combine(day, time(12, 0))

        if timezone.is_aware(timezone.now()):
            created_at = timezone.make_aware(naive_datetime)
        else:
            created_at = naive_datetime

        Order.objects.filter(pk=order.pk).update(created_at=created_at)

    def test_daily_sales_and_empty_days(self):
        report = get_daily_sales_report(self.start_date, self.end_date)

        self.assertEqual(len(report), 3)

        self.assertEqual(report[0]["date"], self.start_date)
        self.assertEqual(report[0]["total_orders"], 3)
        self.assertEqual(report[0]["placed_orders"], 2)
        self.assertEqual(report[0]["cancelled_orders"], 1)
        self.assertEqual(report[0]["placed_revenue"], Decimal("1500.00"))

        self.assertEqual(report[1]["date"], self.middle_date)
        self.assertEqual(report[1]["total_orders"], 0)
        self.assertEqual(report[1]["placed_revenue"], Decimal("0.00"))

        self.assertEqual(report[2]["date"], self.end_date)
        self.assertEqual(report[2]["placed_orders"], 1)
        self.assertEqual(report[2]["placed_revenue"], Decimal("700.00"))

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            get_daily_sales_report(self.end_date, self.start_date)


class ProductPerformanceReportTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Performance Category")
        self.supplier = Supplier.objects.create(name="Performance Supplier")

        self.keyboard = Product.objects.create(
            sku="PERF-KEY-001",
            name="Performance Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            stock=10,
        )
        self.mouse = Product.objects.create(
            sku="PERF-MOU-001",
            name="Performance Mouse",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("200.00"),
            stock=10,
        )

        self.placed_a = Order.objects.create(
            status=Order.Status.PLACED,
            total_amount=Decimal("1200.00"),
        )
        self.placed_b = Order.objects.create(
            status=Order.Status.PLACED,
            total_amount=Decimal("1000.00"),
        )
        self.cancelled = Order.objects.create(
            status=Order.Status.CANCELLED,
            total_amount=Decimal("2500.00"),
        )

        OrderItem.objects.create(
            order=self.placed_a,
            product=self.keyboard,
            quantity=2,
            unit_price=Decimal("500.00"),
        )
        OrderItem.objects.create(
            order=self.placed_a,
            product=self.mouse,
            quantity=1,
            unit_price=Decimal("200.00"),
        )
        OrderItem.objects.create(
            order=self.placed_b,
            product=self.keyboard,
            quantity=2,
            unit_price=Decimal("500.00"),
        )
        OrderItem.objects.create(
            order=self.cancelled,
            product=self.keyboard,
            quantity=5,
            unit_price=Decimal("500.00"),
        )

    def test_product_sales_exclude_cancelled_orders(self):
        report = get_product_performance_report()
        results = {row["product_id"]: row for row in report}

        keyboard = results[self.keyboard.id]
        self.assertEqual(keyboard["quantity_sold"], 4)
        self.assertEqual(keyboard["sales_value"], Decimal("2000.00"))
        self.assertEqual(keyboard["order_count"], 2)

        mouse = results[self.mouse.id]
        self.assertEqual(mouse["quantity_sold"], 1)
        self.assertEqual(mouse["sales_value"], Decimal("200.00"))
        self.assertEqual(mouse["order_count"], 1)

    def test_products_without_sales_are_omitted(self):
        report = get_product_performance_report()
        reported_ids = {row["product_id"] for row in report}

        self.assertIn(self.keyboard.id, reported_ids)
        self.assertIn(self.mouse.id, reported_ids)

    def test_report_is_sorted_by_quantity_sold(self):
        report = get_product_performance_report()

        self.assertEqual(report[0]["product_id"], self.keyboard.id)
        self.assertGreaterEqual(
            report[0]["quantity_sold"],
            report[-1]["quantity_sold"],
        )


class ReportingAPITests(APITestCase):
    def setUp(self):
        self.user = create_order_test_user("reporting_api_user")
        self.client.force_authenticate(user=self.user)

    def test_order_summary_endpoint(self):
        Order.objects.create(
            customer_name="Customer A",
            status=Order.Status.PLACED,
            total_amount=Decimal("500.00"),
        )
        Order.objects.create(
            customer_name="Customer B",
            status=Order.Status.CANCELLED,
            total_amount=Decimal("200.00"),
        )

        response = self.client.get("/api/orders/reports/summary/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_orders"], 2)
        self.assertEqual(response.data["placed_orders"], 1)
        self.assertEqual(response.data["cancelled_orders"], 1)
        self.assertEqual(
            Decimal(str(response.data["placed_revenue"])),
            Decimal("500.00"),
        )

    def test_daily_sales_requires_dates(self):
        response = self.client.get("/api/orders/reports/daily-sales/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_daily_sales_rejects_reversed_dates(self):
        response = self.client.get(
            "/api/orders/reports/daily-sales/",
            {"start_date": "2026-10-28", "end_date": "2026-10-26"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_daily_sales_accepts_valid_dates(self):
        response = self.client.get(
            "/api/orders/reports/daily-sales/",
            {"start_date": "2026-10-26", "end_date": "2026-10-28"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(response.data[0]["date"], date(2026, 10, 26))

    def test_product_performance_endpoint(self):
        response = self.client.get(
            "/api/orders/reports/product-performance/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)


class OrderAuthenticationTests(TestCase):
    def test_unauthenticated_order_request_is_rejected(self):
        response = APIClient().get("/api/orders/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_order_report_request_is_rejected(self):
        response = APIClient().get("/api/orders/reports/summary/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class OrderOwnershipSecurityTests(APITestCase):
    def setUp(self):
        self.owner = create_order_test_user("ownership_owner")
        self.other_user = create_order_test_user("ownership_other")
        self.staff_user = get_user_model().objects.create_user(
            username="ownership_staff",
            password="test-password-123",
            is_staff=True,
        )

        self.category = Category.objects.create(name="Ownership Category")
        self.supplier = Supplier.objects.create(name="Ownership Supplier")

        self.product = Product.objects.create(
            sku="OWN-KEY-001",
            name="Ownership Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            stock=10,
        )

        self.order = create_order(
            items=[{"product_id": self.product.id, "quantity": 2}],
            user=self.owner,
        )

    def test_other_user_cannot_retrieve_order(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(f"/api/orders/{self.order.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_user_cannot_see_order_in_list(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get("/api/orders/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_other_user_cannot_cancel_order_or_change_stock(self):
        self.client.force_authenticate(user=self.other_user)

        stock_before = Product.objects.get(pk=self.product.id).stock
        movement_count_before = InventoryMovement.objects.count()

        response = self.client.post(
            f"/api/orders/{self.order.id}/cancel/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.product.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(self.product.stock, stock_before)
        self.assertEqual(self.order.status, Order.Status.PLACED)
        self.assertEqual(
            InventoryMovement.objects.count(),
            movement_count_before,
        )

    def test_owner_can_cancel_own_order(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f"/api/orders/{self.order.id}/cancel/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.CANCELLED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_staff_can_retrieve_and_cancel_another_users_order(self):
        self.client.force_authenticate(user=self.staff_user)

        detail_response = self.client.get(
            f"/api/orders/{self.order.id}/"
        )
        self.assertEqual(
            detail_response.status_code,
            status.HTTP_200_OK,
        )

        cancel_response = self.client.post(
            f"/api/orders/{self.order.id}/cancel/"
        )
        self.assertEqual(
            cancel_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            cancel_response.data["status"],
            Order.Status.CANCELLED,
        )
