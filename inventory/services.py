
from django.core.exceptions import ValidationError
from django.db import transaction

from catalog.models import Product
from .models import InventoryMovement


@transaction.atomic
def stock_in(
    product_id,
    quantity,
    user=None,
    reference="",
    note="",
):
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValidationError("Quantity must be a whole number.")

    if quantity <= 0:
        raise ValidationError("Stock-in quantity must be greater than zero.")

    product = Product.objects.select_for_update().get(pk=product_id)

    if not product.is_active:
        raise ValidationError("Cannot add stock to an inactive product.")

    product.stock += quantity
    product.save(update_fields=["stock", "updated_at"])

    return InventoryMovement.objects.create(
        product=product,
        movement_type=InventoryMovement.MovementType.STOCK_IN,
        quantity=quantity,
        user=user,
        reference=reference,
        note=note,
    )


@transaction.atomic
def stock_out(
    product_id,
    quantity,
    user=None,
    reference="",
    note="",
):
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValidationError("Quantity must be a whole number.")

    if quantity <= 0:
        raise ValidationError("Stock-out quantity must be greater than zero.")

    product = Product.objects.select_for_update().get(pk=product_id)

    if quantity > product.stock:
        raise ValidationError(
            f"Insufficient stock. Available: {product.stock}, "
            f"requested: {quantity}."
        )

    product.stock -= quantity
    product.save(update_fields=["stock", "updated_at"])

    return InventoryMovement.objects.create(
        product=product,
        movement_type=InventoryMovement.MovementType.STOCK_OUT,
        quantity=-quantity,
        user=user,
        reference=reference,
        note=note,
    )


@transaction.atomic
def adjust_stock(
    product_id,
    new_stock,
    user=None,
    reference="",
    note="",
):
    if isinstance(new_stock, bool) or not isinstance(new_stock, int):
        raise ValidationError("New stock must be a whole number.")

    if new_stock < 0:
        raise ValidationError("Stock cannot be negative.")

    product = Product.objects.select_for_update().get(pk=product_id)

    difference = new_stock - product.stock

    if difference == 0:
        raise ValidationError("New stock is the same as current stock.")

    product.stock = new_stock
    product.save(update_fields=["stock", "updated_at"])

    return InventoryMovement.objects.create(
        product=product,
        movement_type=InventoryMovement.MovementType.ADJUSTMENT,
        quantity=difference,
        user=user,
        reference=reference,
        note=note,
    )
