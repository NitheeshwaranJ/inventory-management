
from django.urls import path
from .views import (
    OrderListCreateAPIView,
    OrderDetailAPIView,
    OrderCancelAPIView,
    OrderSummaryReportAPIView,
    DailySalesReportAPIView,
    ProductPerformanceReportAPIView,
)

urlpatterns = [
    path("orders/", OrderListCreateAPIView.as_view(), name="order-list-create"),
    path("orders/<int:pk>/", OrderDetailAPIView.as_view(), name="order-detail"),
    path(
        "orders/<int:pk>/cancel/",
        OrderCancelAPIView.as_view(),
        name="order-cancel",
    ),
    path(
        "orders/reports/summary/",
        OrderSummaryReportAPIView.as_view(),
        name="order-summary-report",
    ),
    path(
        "orders/reports/daily-sales/",
        DailySalesReportAPIView.as_view(),
        name="daily-sales-report",
    ),
    path(
        "orders/reports/product-performance/",
        ProductPerformanceReportAPIView.as_view(),
        name="product-performance-report",
    ),
]
