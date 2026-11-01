
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import OrderCreateSerializer, OrderReadSerializer
from .services import create_order, cancel_order
from .reports import (
    get_order_summary,
    get_daily_sales_report,
    get_product_performance_report,
)


def django_validation_detail(exc):
    """Convert Django validation errors into REST API-friendly errors."""
    if hasattr(exc, "message_dict"):
        return exc.message_dict

    return {"detail": exc.messages}


def get_accessible_orders(user):
    """Staff can access all orders; other users can access their own."""
    queryset = Order.objects.all()

    if user.is_staff or user.is_superuser:
        return queryset

    return queryset.filter(created_by=user)


class OrderListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
      if getattr(self, "swagger_fake_view", False):
        return Order.objects.none()

      return get_accessible_orders(self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrderCreateSerializer

        return OrderReadSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = self.get_serializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.validated_data

        try:
            order = create_order(
                items=data["items"],
                customer_name=data.get("customer_name", ""),
                customer_email=data.get("customer_email", ""),
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                django_validation_detail(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = OrderReadSerializer(
            order,
            context=self.get_serializer_context(),
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = OrderReadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            get_accessible_orders(self.request.user)
            .select_related("created_by")
            .prefetch_related("items__product")
        )

@extend_schema(
    request=None,
    responses={
        200: OrderReadSerializer,
        400: OpenApiTypes.OBJECT,
        404: OpenApiTypes.OBJECT,
    },
    description="Cancel an accessible order and restore its stock.",
)
class OrderCancelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        get_object_or_404(
            get_accessible_orders(request.user),
            pk=pk,
        )

        try:
            order = cancel_order(
                order_id=pk,
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                django_validation_detail(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            OrderReadSerializer(order).data,
            status=status.HTTP_200_OK,
        )

@extend_schema(
    responses=OpenApiTypes.OBJECT,
    description="Returns aggregate order summary statistics.",
)
class OrderSummaryReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_order_summary())


class DailySalesQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, attrs):
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError(
                "start_date must be on or before end_date."
            )

        return attrs

@extend_schema(
    parameters=[DailySalesQuerySerializer],
    responses=OpenApiTypes.OBJECT,
    description="Returns daily sales for the requested date range.",
)
class DailySalesReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = DailySalesQuerySerializer(
            data=request.query_params
        )

        if not query_serializer.is_valid():
            return Response(
                query_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = get_daily_sales_report(
                start_date=query_serializer.validated_data["start_date"],
                end_date=query_serializer.validated_data["end_date"],
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(report)

@extend_schema(
    responses=OpenApiTypes.OBJECT,
    description="Returns product performance statistics.",
)
class ProductPerformanceReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_product_performance_report())
