
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Product
from .serializers import ProductSerializer


class ProductListCreateAPIView(generics.ListCreateAPIView):
    queryset = Product.objects.select_related(
        "category",
        "supplier",
    ).all()

    serializer_class = ProductSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = {
        "category": ["exact"],
        "supplier": ["exact"],
        "is_active": ["exact"],
        "stock": ["exact", "gte", "lte"],
    }

    search_fields = ["name", "sku", "description"]

    ordering_fields = [
        "name",
        "selling_price",
        "cost_price",
        "stock",
        "created_at",
    ]

    ordering = ["name"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUser()]

        return [IsAuthenticated()]


class ProductDetailAPIView(generics.RetrieveUpdateAPIView):
    queryset = Product.objects.select_related(
        "category",
        "supplier",
    ).all()

    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            return [IsAdminUser()]

        return [IsAuthenticated()]
