from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase

from catalog.models import Category, Supplier, Product
from orders.models import Order
from orders.services import create_order


class ConcurrentOrderTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        category = Category.objects.create(name="Concurrency Test")
        supplier = Supplier.objects.create(name="Concurrency Supplier")

        self.product = Product.objects.create(
            sku="CONC-001",
            name="Concurrency Keyboard",
            category=category,
            supplier=supplier,
            cost_price="500.00",
            selling_price="800.00",
            stock=5,
            low_stock_threshold=1,
        )

    def test_two_simultaneous_orders_cannot_oversell(self):
        barrier = Barrier(2)
        product_id = self.product.id

        def place_order(customer):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    order = create_order(
                        items=[
                            {"product_id": product_id, "quantity": 4}
                        ],
                        customer_name=customer,
                    )
                    return ("success", order.pk)
                except Exception as exc:
                    from django.core.exceptions import ValidationError

                    if isinstance(exc, ValidationError):
                        return ("rejected", str(exc))
                    raise
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(place_order, "Customer A"),
                executor.submit(place_order, "Customer B"),
            ]
            results = [future.result(timeout=30) for future in futures]

        self.product.refresh_from_db()

        self.assertEqual(
            sum(result[0] == "success" for result in results), 1
        )
        self.assertEqual(
            sum(result[0] == "rejected" for result in results), 1
        )
        self.assertEqual(self.product.stock, 1)
        self.assertEqual(
            Order.objects.filter(status=Order.Status.PLACED).count(), 1
        )