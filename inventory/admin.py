
from django.contrib import admin
from .models import InventoryMovement


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "movement_type",
        "quantity",
        "reference",
        "user",
        "created_at",
    )
    list_filter = ("movement_type", "created_at")
    search_fields = (
        "product__sku",
        "product__name",
        "reference",
        "note",
    )
    list_select_related = ("product", "user")
    readonly_fields = ("created_at",)
