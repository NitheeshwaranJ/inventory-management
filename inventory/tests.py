
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Category, Supplier, Product
from .models import InventoryMovement
from .services import stock_in, stock_out, adjust_stock


def create_test_user(username="inventory_api_user", is_staff=False):
    return get_user_model().objects.create_user(
        username=username,
        password="test-password-123",
        is_staff=is_staff,
    )


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Accessories")
        self.supplier = Supplier.objects.create(name="Test Supplier")

        self.product = Product.objects.create(
            sku="INV-001",
            name="Test Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            stock=10,
        )

        self.user = create_test_user("inventory_service_user")

    def test_stock_in_increases_stock_and_creates_history(self):
        movement = stock_in(
            self.product.id,
            5,
            user=self.user,
            reference="PO-001",
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)
        self.assertEqual(movement.quantity, 5)
        self.assertEqual(
            movement.movement_type,
            InventoryMovement.MovementType.STOCK_IN,
        )
        self.assertEqual(movement.reference, "PO-001")

    def test_stock_out_decreases_stock_and_records_negative_quantity(self):
        movement = stock_out(self.product.id, 3)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        self.assertEqual(movement.quantity, -3)

    def test_stock_out_rejects_insufficient_stock(self):
        with self.assertRaises(ValidationError):
            stock_out(self.product.id, 11)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_adjustment_records_stock_difference(self):
        movement = adjust_stock(self.product.id, 7)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        self.assertEqual(movement.quantity, -3)
        self.assertEqual(
            movement.movement_type,
            InventoryMovement.MovementType.ADJUSTMENT,
        )

    def test_adjustment_rejects_negative_stock(self):
        with self.assertRaises(ValidationError):
            adjust_stock(self.product.id, -1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_invalid_stock_in_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            stock_in(self.product.id, 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_inactive_product_cannot_receive_stock(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            stock_in(self.product.id, 5)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_stock_in_rolls_back_if_movement_creation_fails(self):
        with patch(
            "inventory.services.InventoryMovement.objects.create",
            side_effect=RuntimeError("Simulated database failure"),
        ):
            with self.assertRaises(RuntimeError):
                stock_in(self.product.id, 5)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)


class InventoryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.staff_user = create_test_user(
            "inventory_staff_user",
            is_staff=True,
        )
        self.normal_user = create_test_user("inventory_normal_user")

        # Successful stock operations require staff privileges.
        self.client.force_authenticate(user=self.staff_user)

        self.category = Category.objects.create(name="API Accessories")
        self.supplier = Supplier.objects.create(name="API Supplier")

        self.product = Product.objects.create(
            sku="INV-API-001",
            name="API Test Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            stock=10,
        )

        self.stock_in_url = "/api/inventory/stock-in/"
        self.stock_out_url = "/api/inventory/stock-out/"
        self.movements_url = "/api/inventory/movements/"

    def test_stock_in_api(self):
        response = self.client.post(
            self.stock_in_url,
            {
                "product": self.product.id,
                "quantity": 5,
                "reference": "PO-API-001",
                "note": "Received shipment",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)
        self.assertEqual(response.data["quantity"], 5)
        self.assertEqual(response.data["reference"], "PO-API-001")

    def test_stock_out_api(self):
        response = self.client.post(
            self.stock_out_url,
            {"product": self.product.id, "quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        self.assertEqual(response.data["quantity"], -3)

    def test_stock_out_api_rejects_insufficient_stock(self):
        response = self.client.post(
            self.stock_out_url,
            {"product": self.product.id, "quantity": 11},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_stock_api_rejects_zero_quantity(self):
        response = self.client.post(
            self.stock_in_url,
            {"product": self.product.id, "quantity": 0},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_movement_history_api(self):
        stock_in(self.product.id, 5, reference="PO-HISTORY-001")
        stock_out(self.product.id, 2, reference="ISSUE-HISTORY-001")

        response = self.client.get(self.movements_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_movement_history_can_filter_by_product(self):
        stock_in(self.product.id, 5)

        response = self.client.get(
            self.movements_url,
            {"product": self.product.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["product"], self.product.id)

    def test_normal_user_cannot_stock_in(self):
        self.client.force_authenticate(user=self.normal_user)

        response = self.client.post(
            self.stock_in_url,
            {"product": self.product.id, "quantity": 5},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_normal_user_cannot_stock_out(self):
        self.client.force_authenticate(user=self.normal_user)

        response = self.client.post(
            self.stock_out_url,
            {"product": self.product.id, "quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 0)


class InventoryReportAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            user=create_test_user("report_api_user")
        )

        self.category = Category.objects.create(name="Report Accessories")
        self.supplier = Supplier.objects.create(name="Report Supplier")

        self.low_stock_url = "/api/inventory/reports/low-stock/"
        self.out_of_stock_url = "/api/inventory/reports/out-of-stock/"

    def create_product(self, sku, name, stock, threshold=5, active=True):
        return Product.objects.create(
            sku=sku,
            name=name,
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            stock=stock,
            low_stock_threshold=threshold,
            is_active=active,
        )

    def test_low_stock_report_includes_products_at_threshold(self):
        self.create_product("LOW-001", "Low Keyboard", stock=5, threshold=5)
        response = self.client.get(self.low_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["sku"], "LOW-001")

    def test_low_stock_report_excludes_zero_stock(self):
        self.create_product("ZERO-001", "Empty Keyboard", stock=0)
        response = self.client.get(self.low_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_low_stock_report_excludes_healthy_stock(self):
        self.create_product("HIGH-001", "Healthy Keyboard", stock=6)
        response = self.client.get(self.low_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_out_of_stock_report_includes_zero_stock(self):
        self.create_product("OUT-001", "Empty Mouse", stock=0)
        response = self.client.get(self.out_of_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["sku"], "OUT-001")

    def test_reports_exclude_inactive_products(self):
        self.create_product(
            "INACTIVE-001",
            "Inactive Product",
            stock=0,
            active=False,
        )

        low_response = self.client.get(self.low_stock_url)
        out_response = self.client.get(self.out_of_stock_url)

        self.assertEqual(low_response.status_code, status.HTTP_200_OK)
        self.assertEqual(out_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(low_response.data), 0)
        self.assertEqual(len(out_response.data), 0)


class InventoryValuationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            user=create_test_user("valuation_api_user")
        )

        self.category = Category.objects.create(name="Valuation Category")
        self.supplier = Supplier.objects.create(name="Valuation Supplier")
        self.url = "/api/inventory/reports/valuation/"

    def create_product(self, sku, stock, cost_price, active=True):
        return Product.objects.create(
            sku=sku,
            name=f"Product {sku}",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal(cost_price),
            selling_price=Decimal("999.00"),
            stock=stock,
            is_active=active,
        )

    def test_inventory_valuation_total(self):
        self.create_product("VAL-001", 10, "500.00")
        self.create_product("VAL-002", 20, "200.00")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(str(response.data["total_inventory_value"])),
            Decimal("9000.00"),
        )
        self.assertEqual(response.data["product_count"], 2)

    def test_zero_stock_and_inactive_products_are_excluded(self):
        self.create_product("VAL-003", 0, "500.00")
        self.create_product("VAL-004", 10, "100.00", active=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(str(response.data["total_inventory_value"])),
            Decimal("0.00"),
        )
        self.assertEqual(response.data["product_count"], 0)

    def test_empty_inventory_has_zero_value(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(str(response.data["total_inventory_value"])),
            Decimal("0.00"),
        )
        self.assertEqual(response.data["products"], [])


class InventoryAuthenticationTests(TestCase):
    def test_unauthenticated_movement_request_is_rejected(self):
        response = APIClient().get("/api/inventory/movements/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_stock_in_is_rejected(self):
        response = APIClient().post(
            "/api/inventory/stock-in/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_stock_out_is_rejected(self):
        response = APIClient().post(
            "/api/inventory/stock-out/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
