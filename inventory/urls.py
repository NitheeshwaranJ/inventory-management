
from django.urls import path

from .views import (
    InventoryMovementListAPIView,
    StockInAPIView,
    StockOutAPIView,
    LowStockReportAPIView,
    OutOfStockReportAPIView,
    InventoryValuationAPIView,
)

urlpatterns = [
    path(
        "movements/",
        InventoryMovementListAPIView.as_view(),
        name="inventory-movements",
    ),
    path(
        "stock-in/",
        StockInAPIView.as_view(),
        name="inventory-stock-in",
    ),
    path(
        "stock-out/",
        StockOutAPIView.as_view(),
        name="inventory-stock-out",
    ),
    path(
        "reports/low-stock/",
        LowStockReportAPIView.as_view(),
        name="inventory-low-stock",
    ),
    path(
        "reports/out-of-stock/",
        OutOfStockReportAPIView.as_view(),
        name="inventory-out-of-stock",
    ),
    path(
    "reports/valuation/",
    InventoryValuationAPIView.as_view(),
    name="inventory-valuation",
),
]
