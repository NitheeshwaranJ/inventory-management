
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Category, Supplier, Product


class ProductAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.staff_user = get_user_model().objects.create_user(
            username="catalog_staff_user",
            password="test-password-123",
            is_staff=True,
        )
        self.normal_user = get_user_model().objects.create_user(
            username="catalog_normal_user",
            password="test-password-123",
        )

        # Product creation and update require staff permissions.
        self.client.force_authenticate(user=self.staff_user)

        self.category = Category.objects.create(name="Accessories")
        self.supplier = Supplier.objects.create(name="Test Supplier")
        self.url = "/api/products/"

        self.valid_data = {
            "sku": "KEY-100",
            "name": "Keyboard",
            "description": "USB keyboard",
            "category": self.category.id,
            "supplier": self.supplier.id,
            "cost_price": "500.00",
            "selling_price": "800.00",
            "low_stock_threshold": 5,
        }

    def test_create_product(self):
        response = self.client.post(
            self.url, self.valid_data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        product = Product.objects.get(sku="KEY-100")
        self.assertEqual(product.name, "Keyboard")
        self.assertEqual(product.stock, 0)
        self.assertEqual(product.selling_price, Decimal("800.00"))

    def test_duplicate_sku_is_rejected(self):
        Product.objects.create(
            sku="KEY-100",
            name="Existing Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
        )

        response = self.client.post(
            self.url, self.valid_data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Product.objects.filter(sku="KEY-100").count(), 1)

    def test_negative_selling_price_is_rejected(self):
        data = {
            **self.valid_data,
            "sku": "KEY-NEG",
            "selling_price": "-10.00",
        }

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Product.objects.filter(sku="KEY-NEG").exists())

    def test_search_by_product_name(self):
        Product.objects.create(
            sku="KEY-200",
            name="Mechanical Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
        )

        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(self.url, {"search": "Mechanical"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["sku"], "KEY-200")

    def test_normal_user_cannot_create_product(self):
        self.client.force_authenticate(user=self.normal_user)

        response = self.client.post(
            self.url, self.valid_data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Product.objects.filter(sku="KEY-100").exists())

    def test_normal_user_cannot_update_product(self):
        product = Product.objects.create(
            sku="KEY-UPDATE",
            name="Original Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
        )

        self.client.force_authenticate(user=self.normal_user)

        response = self.client.patch(
            f"/api/products/{product.id}/",
            {"name": "Changed Keyboard"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        product.refresh_from_db()
        self.assertEqual(product.name, "Original Keyboard")

    def test_staff_can_update_product(self):
        product = Product.objects.create(
            sku="KEY-STAFF-UPDATE",
            name="Original Keyboard",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
        )

        response = self.client.patch(
            f"/api/products/{product.id}/",
            {"name": "Updated Keyboard"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        product.refresh_from_db()
        self.assertEqual(product.name, "Updated Keyboard")


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/products/"

        self.user = get_user_model().objects.create_user(
            username="catalog_token_user",
            password="test-password-123",
        )

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_token_allows_access(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
