
from django.contrib import admin
from .models import Category, Supplier, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "phone")
    search_fields = ("name", "email")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sku",
        "name",
        "category",
        "supplier",
        "cost_price",
        "selling_price",
        "stock",
        "low_stock_threshold",
        "is_active",
    )

    list_filter = ("category", "supplier", "is_active")
    search_fields = ("sku", "name")
    list_select_related = ("category", "supplier")
