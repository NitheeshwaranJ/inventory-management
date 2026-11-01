
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from catalog.models import Product
from catalog.serializers import ProductSerializer

from .models import InventoryMovement
from .serializers import (
    InventoryMovementSerializer,
    StockMovementRequestSerializer,
)
from .services import stock_in, stock_out
from .reports import get_inventory_valuation


def convert_validation_error(exc):
    """Convert service-layer validation errors into REST API-friendly errors."""
    if hasattr(exc, "message_dict"):
        detail = exc.message_dict
    else:
        detail = exc.messages

    raise ValidationError(detail)


class InventoryMovementListAPIView(generics.ListAPIView):
    serializer_class = InventoryMovementSerializer

    queryset = InventoryMovement.objects.select_related(
        "product",
        "user",
    ).all()

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        product_id = self.request.query_params.get("product")
        movement_type = self.request.query_params.get("movement_type")
        reference = self.request.query_params.get("reference")

        if product_id:
            if not product_id.isdigit():
                raise ValidationError(
                    {"product": "Provide a valid product ID."}
                )

            queryset = queryset.filter(product_id=int(product_id))

        if movement_type:
            valid_types = InventoryMovement.MovementType.values

            if movement_type not in valid_types:
                raise ValidationError({
                    "movement_type": (
                        f"Choose one of: {', '.join(valid_types)}."
                    )
                })

            queryset = queryset.filter(movement_type=movement_type)

        if reference:
            queryset = queryset.filter(reference__icontains=reference)

        return queryset

@extend_schema(
    request=StockMovementRequestSerializer,
    responses={
        201: InventoryMovementSerializer,
        400: None,
        404: None,
    },
    description="Add stock to an active product and record the movement.",
)
class StockInAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = StockMovementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            movement = stock_in(
                product_id=data["product"].pk,
                quantity=data["quantity"],
                user=request.user,
                reference=data["reference"],
                note=data["note"],
            )
        except DjangoValidationError as exc:
            convert_validation_error(exc)
        except Product.DoesNotExist:
            raise Http404("Product not found.")

        return Response(
            InventoryMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )

@extend_schema(
    request=StockMovementRequestSerializer,
    responses={
        201: InventoryMovementSerializer,
        400: None,
        404: None,
    },
    description="Remove stock from a product and record the movement.",
)
class StockOutAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = StockMovementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            movement = stock_out(
                product_id=data["product"].pk,
                quantity=data["quantity"],
                user=request.user,
                reference=data["reference"],
                note=data["note"],
            )
        except DjangoValidationError as exc:
            convert_validation_error(exc)
        except Product.DoesNotExist:
            raise Http404("Product not found.")

        return Response(
            InventoryMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )


class LowStockReportAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Product.objects
            .filter(
                is_active=True,
                stock__gt=0,
                stock__lte=F("low_stock_threshold"),
            )
            .select_related("category", "supplier")
            .order_by("stock", "name")
        )


class OutOfStockReportAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Product.objects
            .filter(
                is_active=True,
                stock=0,
            )
            .select_related("category", "supplier")
            .order_by("name")
        )

@extend_schema(
    responses=OpenApiTypes.OBJECT,
    description=(
        "Returns total inventory valuation and a per-product breakdown."
    ),
)
class InventoryValuationAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        report = get_inventory_valuation()

        return Response({
            "total_inventory_value": str(
                report["total_inventory_value"]
            ),
            "product_count": report["product_count"],
            "products": [
                {
                    **product,
                    "cost_price": str(product["cost_price"]),
                    "inventory_value": str(product["inventory_value"]),
                }
                for product in report["products"]
            ],
        })
