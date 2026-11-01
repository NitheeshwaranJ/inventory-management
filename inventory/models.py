
from django.conf import settings
from django.db import models



class InventoryMovement(models.Model):

    class MovementType(models.TextChoices):
        STOCK_IN = "STOCK_IN", "Stock In"
        STOCK_OUT = "STOCK_OUT", "Stock Out"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        RETURN = "RETURN", "Return"

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="inventory_movements",
    )

    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )

    # Positive quantity = units added or removed.
    # For adjustments, this is the signed stock change.
    quantity = models.IntegerField()

    reference = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)

    # Nullable so movements can also be created by system processes.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
    models.CheckConstraint(
        condition=~models.Q(quantity=0),
        name="movement_quantity_nonzero",
    ),
    models.CheckConstraint(
        condition=(
            models.Q(
                movement_type__in=["STOCK_IN", "RETURN"],
                quantity__gt=0,
            )
            | models.Q(
                movement_type="STOCK_OUT",
                quantity__lt=0,
            )
            | (
                models.Q(movement_type="ADJUSTMENT")
                & ~models.Q(quantity=0)
            )
        ),
        name="movement_quantity_matches_type",
    ),
]

    def __str__(self):
        return (
            f"{self.product.sku} | "
            f"{self.movement_type} | {self.quantity}"
        )
