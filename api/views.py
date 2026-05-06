from django.shortcuts import render
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.exceptions import ValidationError, PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q, Count, Sum, Avg
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings as django_settings
from datetime import datetime, timedelta
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
import math
import requests
import threading
import time

from accounts.models import User
from .models import (
    Restaurant, Category, Product, Order, OrderDetail,
    Payment, Review, ProductReview, DeliveryStatusLog, Notification,
    SearchHistory, PopularSearch, UserFavorite, AnalyticsDaily,
    RestaurantAnalytics, ProductAnalytics, AppSettings, Language, Translation,
    GuestOrder, GuestOrderDetail, GuestDeliveryStatusLog, Advertisement,
    RestaurantTable, DineInCart, DineInCartItem, DineInOrder,
    DineInOrderDetail, DineInStatusLog, DineInProduct,
    Country, City,
    EntertainmentVenue, VenueImage, VenueCategory, VenueReview
)
from .serializers import (
    RestaurantSerializer, CategorySerializer, ProductSerializer,
    OrderSerializer, CreateOrderSerializer, OrderDetailSerializer, PaymentSerializer,
    ReviewSerializer, ProductReviewSerializer, DeliveryStatusLogSerializer,
    NotificationSerializer, SearchHistorySerializer, PopularSearchSerializer,
    UserFavoriteSerializer, AnalyticsDailySerializer, RestaurantAnalyticsSerializer,
    ProductAnalyticsSerializer, MultiRestaurantOrderSerializer, AppSettingsSerializer,
    LanguageSerializer, TranslationSerializer, GuestOrderSerializer, 
    CreateGuestOrderSerializer, GuestOrderTrackingSerializer, GuestMultiRestaurantOrderSerializer,
    AdvertisementSerializer, RestaurantTableSerializer, DineInCartSerializer,
    DineInCartItemSerializer, DineInOrderSerializer, DineInOrderDetailSerializer,
    DineInStatusLogSerializer, AddToCartSerializer, UpdateCartItemSerializer,
    CreateDineInOrderSerializer, UpdateDineInOrderStatusSerializer, DineInProductSerializer,
    CountrySerializer, CitySerializer,
    EntertainmentVenueSerializer, EntertainmentVenueListSerializer, VenueImageSerializer, VenueCategorySerializer,
    VenueReviewSerializer
)

# Logger instance
logger = logging.getLogger(__name__)


# -------------------- Health Check Endpoint --------------------
# ALB/ELB ใช้เรียกตรวจสอบสถานะเซิร์ฟเวอร์ ควรตอบ HTTP 200 เสมอ
@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def health_check(request):
    """Simple health check view for load balancer."""
    return Response({"status": "ok"})


# -------------------- Offline Sync Status Endpoint --------------------
@api_view(["GET"])
@permission_classes([AllowAny])
def sync_status(request):
    """
    คืนค่า version hash สำหรับ offline sync
    Client ใช้เปรียบเทียบกับ version ที่ cache ไว้
    ถ้าต่างกัน → ต้อง sync ข้อมูลใหม่
    """
    from django.db.models import Max
    import hashlib

    def iso(dt):
        return dt.isoformat() if dt else ""

    def safe_max_ts(model, field="updated_at"):
        """ดึง max timestamp อย่างปลอดภัย — fallback เป็น count ถ้าไม่มี field"""
        try:
            return model.objects.aggregate(v=Max(field))["v"]
        except Exception:
            # model ไม่มี updated_at → ใช้ record count แทน
            return str(model.objects.count())

    venue_ts = safe_max_ts(EntertainmentVenue)
    restaurant_ts = safe_max_ts(Restaurant)
    category_ts = safe_max_ts(VenueCategory)
    country_ts = safe_max_ts(Country)
    city_ts = safe_max_ts(City)

    raw = "|".join([
        iso(venue_ts) if hasattr(venue_ts, "isoformat") else str(venue_ts or ""),
        iso(restaurant_ts) if hasattr(restaurant_ts, "isoformat") else str(restaurant_ts or ""),
        iso(category_ts) if hasattr(category_ts, "isoformat") else str(category_ts or ""),
        iso(country_ts) if hasattr(country_ts, "isoformat") else str(country_ts or ""),
        str(city_ts or ""),
    ])
    version = hashlib.md5(raw.encode()).hexdigest()[:12]

    return Response({
        "version": version,
    })


NOMINATIM_BASE_URL = getattr(
    django_settings,
    "NOMINATIM_BASE_URL",
    "https://nominatim.openstreetmap.org",
).rstrip("/")
NOMINATIM_TIMEOUT_SECONDS = int(getattr(django_settings, "NOMINATIM_TIMEOUT_SECONDS", 8))
NOMINATIM_CACHE_TTL_SECONDS = int(getattr(django_settings, "NOMINATIM_CACHE_TTL_SECONDS", 60 * 60 * 24))
NOMINATIM_USER_AGENT = getattr(
    django_settings,
    "NOMINATIM_USER_AGENT",
    "FoodDeliveryAseanMall/1.0 (local geocoding proxy)",
)
NOMINATIM_MIN_INTERVAL_SECONDS = float(getattr(django_settings, "NOMINATIM_MIN_INTERVAL_SECONDS", 1.1))
NOMINATIM_RETRY_BACKOFF_SECONDS = float(getattr(django_settings, "NOMINATIM_RETRY_BACKOFF_SECONDS", 2.0))
NOMINATIM_RETRY_ATTEMPTS = max(0, int(getattr(django_settings, "NOMINATIM_RETRY_ATTEMPTS", 1)))
NOMINATIM_REVERSE_CACHE_PRECISION = max(
    3,
    min(6, int(getattr(django_settings, "NOMINATIM_REVERSE_CACHE_PRECISION", 4))),
)
NOMINATIM_RATE_LIMIT_COOLDOWN_SECONDS = max(
    5, int(getattr(django_settings, "NOMINATIM_RATE_LIMIT_COOLDOWN_SECONDS", 30))
)
NOMINATIM_RATE_LIMIT_CACHE_KEY = "nominatim:rate_limited_until"

_nominatim_lock = threading.Lock()
_nominatim_last_request_at = 0.0


def _nominatim_wait_for_rate_slot():
    global _nominatim_last_request_at
    if NOMINATIM_MIN_INTERVAL_SECONDS <= 0:
        return

    with _nominatim_lock:
        now = time.monotonic()
        elapsed = now - _nominatim_last_request_at
        wait_seconds = NOMINATIM_MIN_INTERVAL_SECONDS - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        _nominatim_last_request_at = now


def _parse_retry_after_seconds(value):
    if not value:
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if parsed < 0:
        return None

    return min(parsed, 60.0)


def _nominatim_request(endpoint: str, params: dict, cache_key: str):
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, None

    now_epoch = time.time()
    rate_limited_until = cache.get(NOMINATIM_RATE_LIMIT_CACHE_KEY)
    if isinstance(rate_limited_until, (int, float)) and rate_limited_until > now_epoch:
        retry_after = max(1, int(math.ceil(rate_limited_until - now_epoch)))
        return None, Response(
            {
                "detail": "Geocoding provider rate limit exceeded. Please retry shortly.",
                "retry_after_seconds": retry_after,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    attempt = 0
    response = None
    while attempt <= NOMINATIM_RETRY_ATTEMPTS:
        _nominatim_wait_for_rate_slot()
        try:
            response = requests.get(
                f"{NOMINATIM_BASE_URL}/{endpoint}",
                params=params,
                headers={
                    "User-Agent": NOMINATIM_USER_AGENT,
                    "Accept": "application/json",
                },
                timeout=NOMINATIM_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            return None, Response(
                {"detail": "Failed to connect to geocoding provider."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != 429:
            break

        retry_after_header = response.headers.get("Retry-After")
        retry_after_seconds = _parse_retry_after_seconds(retry_after_header)
        cooldown_seconds = retry_after_seconds or NOMINATIM_RATE_LIMIT_COOLDOWN_SECONDS
        limited_until = time.time() + cooldown_seconds
        cache.set(NOMINATIM_RATE_LIMIT_CACHE_KEY, limited_until, timeout=max(1, int(math.ceil(cooldown_seconds))))

        if attempt >= NOMINATIM_RETRY_ATTEMPTS:
            return None, Response(
                {
                    "detail": "Geocoding provider rate limit exceeded. Please retry shortly.",
                    "retry_after_seconds": max(1, int(math.ceil(cooldown_seconds))),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        backoff_seconds = retry_after_seconds or NOMINATIM_RETRY_BACKOFF_SECONDS
        time.sleep(max(0.5, backoff_seconds))
        attempt += 1

    if response is None:
        return None, Response(
            {"detail": "Geocoding provider returned an unexpected response."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code >= 400:
        return None, Response(
            {"detail": "Geocoding provider returned an unexpected response."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        data = response.json()
    except ValueError:
        return None, Response(
            {"detail": "Invalid geocoding response format."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    cache.set(cache_key, data, NOMINATIM_CACHE_TTL_SECONDS)
    return data, None


@api_view(["GET"])
@permission_classes([AllowAny])
def reverse_geocode_proxy(request):
    lat_raw = request.query_params.get("lat")
    lon_raw = request.query_params.get("lon") or request.query_params.get("lng")

    if lat_raw is None or lon_raw is None:
        return Response(
            {"detail": "Both lat and lon are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (TypeError, ValueError):
        return Response(
            {"detail": "lat/lon must be valid numbers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return Response(
            {"detail": "lat/lon are out of valid range."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    rounded_lat = f"{lat:.{NOMINATIM_REVERSE_CACHE_PRECISION}f}"
    rounded_lon = f"{lon:.{NOMINATIM_REVERSE_CACHE_PRECISION}f}"
    cache_key = f"nominatim:reverse:{rounded_lat}:{rounded_lon}"
    data, error_response = _nominatim_request(
        endpoint="reverse",
        params={
            "format": "jsonv2",
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
            "addressdetails": 1,
        },
        cache_key=cache_key,
    )

    if error_response is not None:
        if error_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            fallback_data = {
                "display_name": f"{lat:.7f}, {lon:.7f}",
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
                "address": {},
                "provider_rate_limited": True,
                "source": "coordinate_fallback",
            }
            cache.set(cache_key, fallback_data, 60)
            logger.warning(
                "Nominatim reverse geocoding rate-limited for lat=%s lon=%s. Returning coordinate fallback.",
                rounded_lat,
                rounded_lon,
            )
            return Response(fallback_data, status=status.HTTP_200_OK)
        return error_response

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def geocode_search_proxy(request):
    query = (request.query_params.get("q") or "").strip()
    if not query:
        return Response([], status=status.HTTP_200_OK)

    try:
        limit = int(request.query_params.get("limit", 5))
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 10))

    normalized_query = " ".join(query.lower().split())
    cache_key = f"nominatim:search:{normalized_query}:{limit}"
    data, error_response = _nominatim_request(
        endpoint="search",
        params={
            "format": "jsonv2",
            "q": query,
            "limit": limit,
            "addressdetails": 1,
        },
        cache_key=cache_key,
    )

    if error_response is not None:
        if error_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            logger.warning("Nominatim search rate-limited for query=%s", normalized_query)
            return Response([], status=status.HTTP_200_OK)
        return error_response

    return Response(data if isinstance(data, list) else [])


class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.select_related('country', 'city').all()
    serializer_class = RestaurantSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['restaurant_name', 'description', 'address', 'country__name', 'city__name']
    ordering_fields = ['average_rating', 'created_at', 'restaurant_name']
    ordering = ['-average_rating']
    filterset_fields = ['status', 'is_special', 'country', 'city']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'products', 'reviews', 'analytics', 'special', 'nearby']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def products(self, request, pk=None):
        restaurant = self.get_object()
        products = restaurant.products.filter(is_available=True)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def reviews(self, request, pk=None):
        restaurant = self.get_object()
        reviews = restaurant.reviews.all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def analytics(self, request, pk=None):
        restaurant = self.get_object()
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        analytics = restaurant.analytics.all()
        if date_from:
            analytics = analytics.filter(date__gte=date_from)
        if date_to:
            analytics = analytics.filter(date__lte=date_to)
        
        serializer = RestaurantAnalyticsSerializer(analytics, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def special(self, request):
        queryset = Restaurant.objects.filter(is_special=True)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def nearby(self, request):
        # This is a placeholder for location-based search
        # In real implementation, you would use geographic queries
        queryset = Restaurant.objects.filter(status='open')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_image(self, request, pk=None):
        """อัปโหลดรูปภาพหน้าร้าน"""
        restaurant = self.get_object()
        
        # Check permissions (restaurant owner or admin only)
        if request.user.role == 'admin' or (hasattr(request.user, 'restaurant') and request.user.restaurant == restaurant):
            pass
        else:
            return Response({'error': 'You do not have permission to edit this restaurant'}, status=status.HTTP_403_FORBIDDEN)
        
        if 'image' not in request.FILES:
            return Response({'error': 'Please select an image file'}, status=status.HTTP_400_BAD_REQUEST)
        
        image_file = request.FILES['image']
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
        if image_file.content_type not in allowed_types:
            return Response({'error': 'Only JPG, PNG and GIF files are supported'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check file size (limit to 10MB for restaurant images)
        if image_file.size > 10 * 1024 * 1024:
            return Response({'error': 'File size must not exceed 10MB'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Upload file
        restaurant.image = image_file
        restaurant.save()
        
        serializer = RestaurantSerializer(restaurant, context={'request': request})
        return Response({
            'message': 'Restaurant image uploaded successfully',
            'restaurant': serializer.data
        })


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['category_name', 'translations__translated_name']
    ordering_fields = ['category_name', 'category_id', 'sort_order']
    ordering = ['sort_order', 'category_name']
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # เพิ่มเพื่อรองรับ image upload
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'products']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = Category.objects.prefetch_related('translations__language').order_by('sort_order', 'category_name')
        
        # กรองหมวดหมู่ตามประเภทร้าน
        restaurant_type = self.request.query_params.get('restaurant_type')
        if restaurant_type == 'general':
            # ร้านทั่วไป - แสดงเฉพาะหมวดหมู่ที่ไม่ใช่เฉพาะร้านพิเศษ
            queryset = queryset.filter(is_special_only=False)
        elif restaurant_type == 'special':
            # ร้านพิเศษ - แสดงหมวดหมู่ทั้งหมด (ไม่ต้องกรอง)
            pass
        
        return queryset
    
    def get_serializer_context(self):
        """ส่ง context ให้ serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        """จัดการการสร้าง Category พร้อมรูปภาพและการแปล"""
        # ถ้ามีไฟล์รูปภาพใน request ให้เพิ่มเข้าไปใน serializer
        if 'image' in self.request.FILES:
            serializer.save(image=self.request.FILES['image'])
        else:
            serializer.save()
    
    def perform_update(self, serializer):
        """จัดการการอัปเดต Category พร้อมรูปภาพและการแปล"""
        # ถ้ามีไฟล์รูปภาพใหม่ใน request ให้เพิ่มเข้าไปใน serializer
        if 'image' in self.request.FILES:
            serializer.save(image=self.request.FILES['image'])
        else:
            serializer.save()
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def products(self, request, pk=None):
        category = self.get_object()
        products = category.products.filter(is_available=True)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['product_name', 'description', 'translations__translated_name', 'translations__translated_description']
    ordering_fields = ['price', 'created_at', 'product_name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'reviews']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = Product.objects.select_related('restaurant', 'category').prefetch_related('translations__language')
        
        # Filter by restaurant
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        
        # Filter by category
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Filter by availability
        is_available = self.request.query_params.get('is_available')
        if is_available is not None:
            queryset = queryset.filter(is_available=is_available.lower() == 'true')
        
        return queryset
    
    def get_serializer_context(self):
        """ส่ง context ให้ serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        """ตรวจสอบว่าหมวดหมู่เข้ากันได้กับประเภทร้านก่อนสร้างสินค้า"""
        category = serializer.validated_data.get('category')
        restaurant = serializer.validated_data.get('restaurant')
        
        if category and restaurant:
            # Check if special category can be used with general restaurant
            if category.is_special_only and not restaurant.is_special:
                raise ValidationError({
                    'category': 'General restaurants cannot use special-only categories'
                })
        
        # ถ้ามีไฟล์รูปภาพใน request ให้เพิ่มเข้าไปใน serializer
        if 'image' in self.request.FILES:
            serializer.save(image=self.request.FILES['image'])
        else:
            serializer.save()
    
    def perform_update(self, serializer):
        """ตรวจสอบว่าหมวดหมู่เข้ากันได้กับประเภทร้านก่อนอัปเดตสินค้า"""
        category = serializer.validated_data.get('category')
        product = serializer.instance
        restaurant = product.restaurant
        
        if category:
            # Check if special category can be used with general restaurant
            if category.is_special_only and not restaurant.is_special:
                raise ValidationError({
                    'category': 'General restaurants cannot use special-only categories'
                })
        
        serializer.save()
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def reviews(self, request, pk=None):
        product = self.get_object()
        reviews = product.reviews.all()
        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_image(self, request, pk=None):
        """อัปโหลดรูปภาพสินค้า"""
        product = self.get_object()
        
        if 'image' not in request.FILES:
            return Response({'error': 'Please select an image file'}, status=status.HTTP_400_BAD_REQUEST)
        
        image_file = request.FILES['image']
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
        if image_file.content_type not in allowed_types:
            return Response({'error': 'Only JPG, PNG and GIF files are supported'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check file size (limit to 5MB)
        if image_file.size > 5 * 1024 * 1024:
            return Response({'error': 'File size must not exceed 5MB'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Upload file
        product.image = image_file
        product.save()
        
        serializer = ProductSerializer(product)
        return Response({
            'message': 'Product image uploaded successfully',
            'product': serializer.data
        })


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'customer':
            return Order.objects.filter(user=user)
        elif user.role in ['special_restaurant', 'general_restaurant']:
            try:
                restaurant = user.restaurant
                return Order.objects.filter(restaurant=restaurant)
            except Restaurant.DoesNotExist:
                return Order.objects.none()
        else:  # admin
            return Order.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateOrderSerializer
        elif self.action == 'multi':
            return MultiRestaurantOrderSerializer
        return OrderSerializer
    
    def create(self, request, *args, **kwargs):
        """สร้างคำสั่งซื้อจากร้านเดียว พร้อมข้อมูลการชำระเงิน"""
        try:
            # ตรวจสอบว่าส่งข้อมูลแบบ FormData หรือ JSON
            if 'order_data' in request.data:
                # ข้อมูลแบบ FormData
                order_data_str = request.data.get('order_data')
                payment_data_str = request.data.get('payment_data')
                proof_of_payment = request.FILES.get('proof_of_payment')
                
                if not order_data_str:
                    return Response({'error': 'order_data is required'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Parse JSON data
                import json
                order_data = json.loads(order_data_str)
                payment_data = json.loads(payment_data_str) if payment_data_str else {}
            else:
                # ข้อมูลแบบ JSON (backward compatibility)
                order_data = request.data
                payment_data = {}
                proof_of_payment = None
            
            # สร้าง order
            serializer = self.get_serializer(data=order_data)
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            
            # สร้าง Payment record หากมีข้อมูลการชำระเงิน
            if payment_data:
                payment = Payment.objects.create(
                    order=order,
                    amount_paid=payment_data.get('amount_paid', order.total_amount),
                    payment_method=payment_data.get('payment_method', 'bank_transfer'),
                    status=payment_data.get('status', 'pending'),
                    proof_of_payment=proof_of_payment
                )
                # print(f"✅ Payment record created for single order: {payment.payment_id}")
            
            # ส่ง notification ไปยังแอดมินทุกคน (ลูกค้าใช้ delivery_status_log แทน)
            admin_users = User.objects.filter(role='admin')
            for admin_user in admin_users:
                Notification.objects.create(
                    user=admin_user,
                    title='New Order Received',
                    message=f'Order #{order.order_id} was placed by {order.user.username}',
                    type='order',
                    related_order=order
                )

            # ส่ง WebSocket notification ไปยังกลุ่มแอดมิน
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "orders_admin",
                {
                    'type': 'new_order',
                    'order_id': order.order_id,
                    'customer_name': order.user.username,
                    'restaurant_name': order.restaurant.restaurant_name if order.restaurant else '',
                    'total_amount': str(order.total_amount),
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to create order: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def multi(self, request):
        """สร้างคำสั่งซื้อจากหลายร้านในครั้งเดียว พร้อมข้อมูลการชำระเงิน"""
        try:
            # ดึงข้อมูลจาก FormData
            order_data_str = request.data.get('order_data')
            payment_data_str = request.data.get('payment_data')
            proof_of_payment = request.FILES.get('proof_of_payment')
            
            if not order_data_str:
                return Response({'error': 'order_data is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse JSON data
            import json
            order_data = json.loads(order_data_str)
            payment_data = json.loads(payment_data_str) if payment_data_str else {}
            
            # สร้าง order จากข้อมูล
            serializer = MultiRestaurantOrderSerializer(data=order_data)
            if serializer.is_valid():
                # สร้าง order จากหลายร้าน
                order = serializer.save()
                
                # สร้าง Payment record หากมีข้อมูลการชำระเงิน
                if payment_data:
                    payment = Payment.objects.create(
                        order=order,
                        amount_paid=payment_data.get('amount_paid', order.total_amount),
                        payment_method=payment_data.get('payment_method', 'bank_transfer'),
                        status=payment_data.get('status', 'pending'),
                        proof_of_payment=proof_of_payment
                    )
                    # print(f"✅ Payment record created: {payment.payment_id}")
                
                # ส่ง notification ไปยังแอดมินทุกคน (ลูกค้าใช้ delivery_status_log แทน)
                admin_users = User.objects.filter(role='admin')
                for admin_user in admin_users:
                    Notification.objects.create(
                        user=admin_user,
                        title='New Multi-Restaurant Order Received',
                        message=f'Multi-restaurant order #{order.order_id} was placed by {order.user.username}',
                        type='order',
                        related_order=order
                    )

                # ส่ง WebSocket notification ไปยังกลุ่มแอดมิน
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "orders_admin",
                    {
                        'type': 'new_order',
                        'order_id': order.order_id,
                        'customer_name': order.user.username,
                        'restaurant_name': 'Multi-Restaurant Order',
                        'total_amount': str(order.total_amount),
                        'timestamp': timezone.now().isoformat()
                    }
                )
                
                # ส่ง WebSocket notification
                if order.user:
                    channel_layer = get_channel_layer()
                    room_group_name = f"orders_user_{order.user.id}"
                    
                    async_to_sync(channel_layer.group_send)(
                        room_group_name,
                        {
                            'type': 'order_status_update',
                            'order_id': order.order_id,
                            'old_status': '',
                            'new_status': order.current_status,
                            'timestamp': timezone.now().isoformat(),
                            'restaurant_name': 'Multi-Restaurant Order',
                            'user_id': order.user.id
                        }
                    )
                
                return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response(
                {'error': f'Failed to create multi-restaurant order: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        old_status = order.current_status
        new_status = request.data.get('status')
        
        if new_status not in dict(Order.STATUS_CHOICES):
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Update order status
        order.current_status = new_status
        order.save()
        
        # Create status log
        DeliveryStatusLog.objects.create(
            order=order,
            status=new_status,
            updated_by_user=request.user
        )
        
        # ไม่ส่ง notification ให้ customer (ใช้ delivery_status_log แทน)
        
        # Send WebSocket notification to customer
        if order.user:
            channel_layer = get_channel_layer()
            room_group_name = f"orders_user_{order.user.id}"
            
            # print(f"🚀 Sending WebSocket update to room: {room_group_name}")
            # print(f"📦 Order {order.order_id}: {old_status} → {new_status}")
            # print(f"👤 User: {order.user.id} ({order.user.username})")
            
            try:
                async_to_sync(channel_layer.group_send)(
                    room_group_name,
                    {
                        'type': 'order_status_update',
                        'order_id': order.order_id,
                        'old_status': old_status,
                        'new_status': new_status,
                        'timestamp': timezone.now().isoformat(),
                        'restaurant_name': order.restaurant.restaurant_name if order.restaurant else 'Multi-Restaurant Order',
                        'user_id': order.user.id
                    }
                )
                # print(f"✅ WebSocket message sent successfully")
            except Exception as e:
                # print(f"❌ Error sending WebSocket message: {str(e)}")
                pass
        
        return Response(OrderSerializer(order).data)
    
    @action(detail=True, methods=['get'])
    def status_logs(self, request, pk=None):
        order = self.get_object()
        logs = order.status_logs.all()
        serializer = DeliveryStatusLogSerializer(logs, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        old_status = order.current_status
        
        if order.current_status in ['completed', 'cancelled']:
            return Response({'error': 'Cannot cancel this order'}, status=status.HTTP_400_BAD_REQUEST)
        
        order.current_status = 'cancelled'
        order.save()
        
        # Create status log
        DeliveryStatusLog.objects.create(
            order=order,
            status='cancelled',
            updated_by_user=request.user
        )
        
        # Send WebSocket notification to customer
        if order.user:
            channel_layer = get_channel_layer()
            room_group_name = f"orders_user_{order.user.id}"
            
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'order_status_update',
                    'order_id': order.order_id,
                    'old_status': old_status,
                    'new_status': 'cancelled',
                    'timestamp': timezone.now().isoformat(),
                    'restaurant_name': order.restaurant.restaurant_name if order.restaurant else '',
                    'user_id': order.user.id
                }
            )
        
        return Response(OrderSerializer(order).data)
    
    def destroy(self, request, pk=None):
        """ลบออเดอร์ (เฉพาะแอดมิน)"""
        # ตรวจสอบ permission - เฉพาะ admin เท่านั้น
        if request.user.role != 'admin':
            return Response(
                {'error': 'เฉพาะแอดมินเท่านั้นที่สามารถลบออเดอร์ได้'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        order = self.get_object()
        order_id = order.order_id
        customer_user = order.user
        
        # ส่งการแจ้งเตือนให้ลูกค้าก่อนลบ (ถ้าเป็นคำสั่งซื้อของผู้ใช้ที่ล็อกอิน)
        if customer_user:
            channel_layer = get_channel_layer()
            room_group_name = f"orders_user_{customer_user.id}"
            
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'order_deleted',
                    'order_id': order_id,
                    'message': 'คำสั่งซื้อของคุณถูกลบโดยระบบ',
                    'timestamp': timezone.now().isoformat(),
                    'restaurant_name': order.restaurant.restaurant_name if order.restaurant else '',
                    'user_id': customer_user.id
                }
            )
        
        # ลบออเดอร์ (Django จะลบข้อมูลที่เกี่ยวข้องอัตโนมัติเพราะ CASCADE)
        order.delete()
        
        return Response(
            {
                'success': True, 
                'message': f'ลบออเดอร์ #{order_id} เรียบร้อยแล้ว'
            },
            status=status.HTTP_200_OK
        )

    def perform_update(self, serializer):
        """Override to send WebSocket notification when order status changes via PUT/PATCH"""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from django.utils import timezone
        
        # Keep old status before saving
        instance = self.get_object()
        old_status = instance.current_status
        
        # Save changes
        updated_order = serializer.save()
        new_status = updated_order.current_status
        
        # If status changed, notify customer via WebSocket
        if old_status != new_status and updated_order.user:
            channel_layer = get_channel_layer()
            room_group_name = f"orders_user_{updated_order.user.id}"
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    "type": "order_status_update",
                    "order_id": updated_order.order_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "timestamp": timezone.now().isoformat(),
                    "restaurant_name": updated_order.restaurant.restaurant_name if updated_order.restaurant else "",
                    "user_id": updated_order.user.id,
                },
            )
        
        return updated_order


class OrderDetailViewSet(viewsets.ModelViewSet):
    queryset = OrderDetail.objects.all()
    serializer_class = OrderDetailSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = OrderDetail.objects.all()
        
        # Filter by order
        order_id = self.request.query_params.get('order_id')
        if order_id:
            queryset = queryset.filter(order_id=order_id)
        
        # Filter by product
        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        # Check permissions
        user = self.request.user
        if user.role == 'customer':
            # Customers can only see their own order details
            queryset = queryset.filter(order__user=user)
        elif user.role in ['special_restaurant', 'general_restaurant']:
            # Restaurant owners can see order details for their restaurant
            try:
                restaurant = user.restaurant
                queryset = queryset.filter(order__restaurant=restaurant)
            except Restaurant.DoesNotExist:
                queryset = OrderDetail.objects.none()
        
        return queryset


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'customer':
            return Payment.objects.filter(order__user=user)
        elif user.role in ['special_restaurant', 'general_restaurant']:
            try:
                restaurant = user.restaurant
                return Payment.objects.filter(order__restaurant=restaurant)
            except Restaurant.DoesNotExist:
                return Payment.objects.none()
        else:  # admin
            return Payment.objects.all()
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        payment = self.get_object()
        payment.status = 'completed'
        payment.save()
        
        # Update order status
        order = payment.order
        order.current_status = 'paid'
        order.save()
        
        # ไม่ส่ง notification ให้ customer (ใช้ delivery_status_log แทน)
        
        return Response(PaymentSerializer(payment).data)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    ordering = ['-review_date']  # เรียงตามวันที่รีวิวล่าสุด
    
    def get_permissions(self):
        """Allow anyone to view, require authentication for create/update/delete"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = Review.objects.all()
        
        # Filter by restaurant
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set the user to the current user and check for existing review"""
        restaurant = serializer.validated_data['restaurant']
        user = self.request.user
        order = serializer.validated_data.get('order')
        
        # If order is provided, check if order has already been reviewed
        if order:
            if Review.objects.filter(order=order).exists():
                raise ValidationError({'error': 'This order has already been reviewed'})
        else:
            # If no order, check if user has already reviewed this restaurant
            existing_review = Review.objects.filter(restaurant=restaurant, user=user, order__isnull=True).first()
            if existing_review:
                raise ValidationError({'error': 'You have already reviewed this restaurant. You can update your existing review instead.'})
        
        serializer.save(user=user)
        
        # Update order as reviewed if order is provided
        if order and serializer.instance:
            Order.objects.filter(order_id=order.order_id).update(is_reviewed=True)
    
    def perform_update(self, serializer):
        """Only allow user to update their own review"""
        review = self.get_object()
        if review.user != self.request.user:
            raise ValidationError({'error': 'You can only update your own review.'})
        serializer.save()
    
    def perform_destroy(self, instance):
        """Only allow user to delete their own review"""
        if instance.user != self.request.user:
            raise ValidationError({'error': 'You can only delete your own review.'})
        instance.delete()


class ProductReviewViewSet(viewsets.ModelViewSet):
    queryset = ProductReview.objects.all()
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['-review_date']  # เรียงตามวันที่รีวิวล่าสุด
    
    def get_queryset(self):
        queryset = ProductReview.objects.all()
        
        # Filter by product
        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by rating
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.filter(rating_product__gte=min_rating)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        order_detail_id = request.data.get('order_detail')
        
        # Check if product has already been reviewed
        if ProductReview.objects.filter(order_detail_id=order_detail_id).exists():
            return Response({'error': 'This product has already been reviewed'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        return super().create(request, *args, **kwargs)


class DeliveryStatusLogViewSet(viewsets.ModelViewSet):
    queryset = DeliveryStatusLog.objects.all()
    serializer_class = DeliveryStatusLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = DeliveryStatusLog.objects.all()
        
        # Filter by order
        order_id = self.request.query_params.get('order_id')
        if order_id:
            queryset = queryset.filter(order_id=order_id)
        
        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        
        return queryset.order_by('-timestamp')
    
    def create(self, request, *args, **kwargs):
        # Add current user as updated_by_user
        request.data['updated_by_user'] = request.user.id
        return super().create(request, *args, **kwargs)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['-created_at']  # เรียงตามวันที่สร้างล่าสุด
    
    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user).order_by('-created_at')
        # รองรับการกรองสถานะการอ่านผ่าน query param: ?is_read=true|false
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            try:
                is_read_bool = str(is_read).lower() == 'true'
                queryset = queryset.filter(is_read=is_read_bool)
            except Exception:
                pass
        return queryset
    
    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        """Mark notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        return Response(NotificationSerializer(notification).data)
    
    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return Response({'message': 'All notifications marked as read'})
    
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """Get unread notifications count"""
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['get'], url_path='badge-counts')
    def badge_counts(self, request):
        """Get badge counts for regular and guest orders separately"""
        # นับ notifications ที่ยังไม่อ่านตาม type
        unread_notifications = Notification.objects.filter(user=request.user, is_read=False)
        
        # นับ regular orders (ที่ล็อกอิน)
        regular_orders_count = unread_notifications.filter(
            type='order',
            related_order__isnull=False
        ).count()
        
        # นับ guest orders (ที่ไม่ล็อกอิน)
        guest_orders_count = unread_notifications.filter(
            type='guest_order',
            related_guest_order__isnull=False
        ).count()
        
        return Response({
            'regular_orders_count': regular_orders_count,
            'guest_orders_count': guest_orders_count,
            'total_unread_count': regular_orders_count + guest_orders_count
        })
    
    @action(detail=False, methods=['post'], url_path='mark-order-read')
    def mark_order_read(self, request):
        """Mark notifications related to specific order as read"""
        order_id = request.data.get('order_id')
        order_type = request.data.get('order_type')  # 'regular' หรือ 'guest'
        
        if not order_id:
            return Response({'error': 'order_id is required'}, status=400)
        
        # Mark all notifications related to this order as read
        from django.db.models import Q
        
        # ใช้ order_type เพื่อกำหนด field ที่ถูกต้อง
        if order_type == 'guest':
            # สำหรับ guest orders ใช้ related_guest_order_id
            notifications = Notification.objects.filter(
                related_guest_order_id=order_id,
                user=request.user,
                is_read=False
            )
        elif order_type == 'regular':
            # สำหรับ regular orders ใช้ related_order_id  
            notifications = Notification.objects.filter(
                related_order_id=order_id,
                user=request.user,
                is_read=False
            )
        else:
            # ถ้าไม่ระบุ order_type ให้ใช้ logic เดิม (fallback)
            # Try to find the order to determine if it's a regular order or guest order
            try:
                # First try to find as a regular order
                from .models import Order
                regular_order = Order.objects.get(order_id=order_id)
                # If found, search by related_order_id
                notifications = Notification.objects.filter(
                    related_order_id=order_id,
                    user=request.user,
                    is_read=False
                )
            except Order.DoesNotExist:
                # If not found as regular order, try as guest order
                try:
                    from .models import GuestOrder
                    guest_order = GuestOrder.objects.get(guest_order_id=order_id)
                    # If found, search by related_guest_order_id
                    notifications = Notification.objects.filter(
                        related_guest_order_id=order_id,
                        user=request.user,
                        is_read=False
                    )
                except GuestOrder.DoesNotExist:
                    # If neither found, use original logic (fallback)
                    notifications = Notification.objects.filter(
                        Q(related_order_id=order_id) | Q(related_guest_order_id=order_id),
                        user=request.user,
                        is_read=False
                    )
        
        count = notifications.count()
        notifications.update(
            is_read=True,
            read_at=timezone.now()
        )
        
        return Response({
            'message': f'Marked {count} notifications as read for order {order_id}',
            'marked_count': count
        })


class UserFavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = UserFavoriteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return UserFavorite.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        # Auto-assign current user
        request.data['user'] = request.user.id
        
        # Check for duplicates
        favorite_type = request.data.get('favorite_type')
        restaurant_id = request.data.get('restaurant')
        product_id = request.data.get('product')
        
        if favorite_type == 'restaurant' and restaurant_id:
            if UserFavorite.objects.filter(
                user=request.user, 
                favorite_type='restaurant', 
                restaurant_id=restaurant_id
            ).exists():
                return Response(
                    {'error': 'This restaurant is already in your favorites'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if favorite_type == 'product' and product_id:
            if UserFavorite.objects.filter(
                user=request.user, 
                favorite_type='product', 
                product_id=product_id
            ).exists():
                return Response(
                    {'error': 'This product is already in your favorites'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return super().create(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    def restaurants(self, request):
        favorites = self.get_queryset().filter(favorite_type='restaurant')
        serializer = self.get_serializer(favorites, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def products(self, request):
        favorites = self.get_queryset().filter(favorite_type='product')
        serializer = self.get_serializer(favorites, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def toggle_restaurant(self, request):
        """Toggle restaurant favorite - add if not exists, remove if exists"""
        restaurant_id = request.data.get('restaurant_id')
        if not restaurant_id:
            return Response({'error': 'restaurant_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            restaurant = Restaurant.objects.get(restaurant_id=restaurant_id)
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        favorite, created = UserFavorite.objects.get_or_create(
            user=request.user,
            restaurant=restaurant,
            favorite_type='restaurant'
        )
        
        if not created:
            favorite.delete()
            return Response({'message': 'Restaurant removed from favorites', 'is_favorite': False})
        else:
            return Response({'message': 'Restaurant added to favorites', 'is_favorite': True})
    
    @action(detail=False, methods=['post'])
    def toggle_product(self, request):
        """Toggle product favorite - add if not exists, remove if exists"""
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        favorite, created = UserFavorite.objects.get_or_create(
            user=request.user,
            product=product,
            favorite_type='product'
        )
        
        if not created:
            favorite.delete()
            return Response({'message': 'Product removed from favorites', 'is_favorite': False})
        else:
            return Response({'message': 'Product added to favorites', 'is_favorite': True})


class SearchViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '')
        search_type = request.query_params.get('type', 'all')
        
        if not query:
            return Response({'results': []})
        
        results = {
            'restaurants': [],
            'products': [],
            'categories': []
        }
        
        # Search restaurants
        if search_type in ['all', 'restaurant']:
            restaurants = Restaurant.objects.filter(
                Q(restaurant_name__icontains=query) |
                Q(description__icontains=query)
            )[:10]
            results['restaurants'] = RestaurantSerializer(restaurants, many=True).data
        
        # Search products
        if search_type in ['all', 'product']:
            # ค้นหาในชื่อสินค้าและคำอธิบายหลัก
            products = Product.objects.filter(
                Q(product_name__icontains=query) |
                Q(description__icontains=query)
            ).filter(is_available=True)
            
            # ค้นหาในข้อมูลการแปลภาษา
            translated_products = Product.objects.filter(
                Q(translations__translated_name__icontains=query) |
                Q(translations__translated_description__icontains=query)
            ).filter(is_available=True).distinct()
            
            # รวมผลลัพธ์และเรียงลำดับ
            all_products = (products | translated_products).distinct()[:10]
            results['products'] = ProductSerializer(all_products, many=True).data
        
        # Search categories
        if search_type in ['all', 'category']:
            # ค้นหาในชื่อหมวดหมู่หลัก
            categories = Category.objects.filter(
                category_name__icontains=query
            )
            
            # ค้นหาในข้อมูลการแปลภาษา
            translated_categories = Category.objects.filter(
                translations__translated_name__icontains=query
            ).distinct()
            
            # รวมผลลัพธ์
            all_categories = (categories | translated_categories).distinct()[:10]
            results['categories'] = CategorySerializer(all_categories, many=True).data
        
        # Save search history for authenticated users
        if request.user.is_authenticated:
            total_results = (len(results['restaurants']) + 
                           len(results['products']) + 
                           len(results['categories']))
            
            SearchHistory.objects.create(
                user=request.user,
                search_query=query,
                search_type=search_type if search_type != 'all' else 'restaurant',
                results_count=total_results
            )
        
        # Update popular searches
        popular_search, created = PopularSearch.objects.get_or_create(
            search_query=query
        )
        if not created:
            popular_search.search_count += 1
            popular_search.save()
        
        return Response(results)
    
    @action(detail=False, methods=['get'])
    def popular(self, request):
        popular_searches = PopularSearch.objects.order_by('-search_count')[:10]
        serializer = PopularSearchSerializer(popular_searches, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        if not request.user.is_authenticated:
            return Response([])
        
        history = SearchHistory.objects.filter(user=request.user).order_by('-created_at')[:20]
        serializer = SearchHistorySerializer(history, many=True)
        return Response(serializer.data)


class AnalyticsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def daily(self, request):
        if request.user.role != 'admin':
            return Response({'error': 'Admin access required'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        analytics = AnalyticsDaily.objects.all()
        if date_from:
            analytics = analytics.filter(date__gte=date_from)
        if date_to:
            analytics = analytics.filter(date__lte=date_to)
        
        serializer = AnalyticsDailySerializer(analytics, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def restaurant(self, request):
        # Get restaurant ID from query params or user's restaurant
        restaurant_id = request.query_params.get('restaurant_id')
        
        if not restaurant_id and hasattr(request.user, 'restaurant'):
            restaurant_id = request.user.restaurant.restaurant_id
        
        if not restaurant_id:
            return Response({'error': 'Restaurant ID required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        analytics = RestaurantAnalytics.objects.filter(restaurant_id=restaurant_id)
        if date_from:
            analytics = analytics.filter(date__gte=date_from)
        if date_to:
            analytics = analytics.filter(date__lte=date_to)
        
        serializer = RestaurantAnalyticsSerializer(analytics, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def product(self, request):
        product_id = request.query_params.get('product_id')
        restaurant_id = request.query_params.get('restaurant_id')
        
        if not product_id:
            return Response({'error': 'Product ID required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        analytics = ProductAnalytics.objects.filter(product_id=product_id)
        if restaurant_id:
            analytics = analytics.filter(restaurant_id=restaurant_id)
        if date_from:
            analytics = analytics.filter(date__gte=date_from)
        if date_to:
            analytics = analytics.filter(date__lte=date_to)
        
        serializer = ProductAnalyticsSerializer(analytics, many=True)
        return Response(serializer.data)


class SearchHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = SearchHistorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Admin can see all search history
        if user.role == 'admin':
            return SearchHistory.objects.all()
        
        # Others can only see their own search history
        return SearchHistory.objects.filter(user=user)
    
    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """Clear user's search history"""
        SearchHistory.objects.filter(user=request.user).delete()
        return Response({'message': 'Search history cleared'})
    
    @action(detail=False, methods=['get'])
    def top_searches(self, request):
        """Get top searches by user"""
        searches = self.get_queryset().values('search_query').annotate(
            count=Count('search_id')
        ).order_by('-count')[:10]
        return Response(searches)


class PopularSearchViewSet(viewsets.ModelViewSet):
    queryset = PopularSearch.objects.all()
    serializer_class = PopularSearchSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'trending']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def trending(self, request):
        """Get trending searches (most searched in last 24 hours)"""
        yesterday = timezone.now() - timedelta(days=1)
        trending = PopularSearch.objects.filter(
            last_searched__gte=yesterday
        ).order_by('-search_count')[:10]
        serializer = self.get_serializer(trending, many=True)
        return Response(serializer.data)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def admin(self, request):
        """Admin dashboard statistics"""
        if request.user.role != 'admin':
            return Response({'error': 'Admin access required'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        today = timezone.now().date()
        
        # Today's statistics (include both logged-in orders and guest orders)
        today_orders_count = (
            Order.objects.filter(order_date__date=today).count() +
            GuestOrder.objects.filter(order_date__date=today).count()
        )
        today_revenue_logged_in = Order.objects.filter(order_date__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        today_revenue_guest = GuestOrder.objects.filter(order_date__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        today_revenue = today_revenue_logged_in + today_revenue_guest
        
        # Overall statistics
        total_users = User.objects.count()
        total_restaurants = Restaurant.objects.count()
        total_orders = Order.objects.count() + GuestOrder.objects.count()
        active_statuses = ['pending', 'paid', 'preparing', 'ready_for_pickup', 'delivering']
        active_orders = (
            Order.objects.filter(current_status__in=active_statuses).count() +
            GuestOrder.objects.filter(current_status__in=active_statuses).count()
        )
        
        # Revenue statistics (include guest orders)
        total_revenue_logged_in = Order.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_revenue_guest = GuestOrder.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_revenue = total_revenue_logged_in + total_revenue_guest
        
        # Popular items
        from django.db.models import Count
        popular_products = OrderDetail.objects.values(
            'product__product_name', 'product__product_id'
        ).annotate(
            order_count=Count('order_detail_id')
        ).order_by('-order_count')[:5]
        
        return Response({
            'today': {
                'orders': today_orders_count,
                'revenue': today_revenue,
                'new_users': User.objects.filter(date_joined__date=today).count(),
            },
            'overview': {
                'total_users': total_users,
                'total_restaurants': total_restaurants,
                'total_orders': total_orders,
                'active_orders': active_orders,
                'total_revenue': total_revenue,
            },
            'popular_products': popular_products,
        })
    
    @action(detail=False, methods=['get'])
    def restaurant(self, request):
        """Restaurant owner dashboard"""
        if request.user.role not in ['special_restaurant', 'general_restaurant', 'admin']:
            return Response({'error': 'Restaurant access required'},
                          status=status.HTTP_403_FORBIDDEN)
        
        try:
            restaurant = request.user.restaurant
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # NOTE เรื่องเวลา:
        # - ระบบนี้ตั้งค่า TIME_ZONE='Asia/Bangkok' และ USE_TZ=True
        # - Django จะ “เก็บ” datetime ในฐานข้อมูลเป็น UTC เสมอ (ปกติ/ถูกต้อง)
        # - เวลาที่ผู้ใช้เห็นควรแปลงเป็นเวลาไทยตอนแสดงผล
        #
        # สำหรับสถิติ "วันนี้" ให้ยึดตามวันของไทย (Asia/Bangkok) แล้วแปลงเป็นช่วงเวลา UTC เพื่อ query
        import pytz
        from django.utils import timezone as tz
        from django.utils.timezone import localtime

        bangkok_tz = pytz.timezone('Asia/Bangkok')
        now_utc = tz.now()
        now_bangkok = localtime(now_utc, bangkok_tz)
        today = now_bangkok.date()

        start_of_day_bangkok = bangkok_tz.localize(datetime.combine(today, datetime.min.time()))
        end_of_day_bangkok = bangkok_tz.localize(datetime.combine(today, datetime.max.time()))
        start_of_day_utc = start_of_day_bangkok.astimezone(pytz.UTC)
        end_of_day_utc = end_of_day_bangkok.astimezone(pytz.UTC)

        today_delivery_orders = Order.objects.filter(
            restaurant=restaurant,
            order_date__gte=start_of_day_utc,
            order_date__lte=end_of_day_utc
        )
        today_dine_in_orders = DineInOrder.objects.filter(
            restaurant=restaurant,
            order_date__gte=start_of_day_utc,
            order_date__lte=end_of_day_utc
        )
        
        today_orders_count = today_delivery_orders.count() + today_dine_in_orders.count()
        
        today_delivery_revenue = today_delivery_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        today_dine_in_revenue = today_dine_in_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        today_revenue = float(today_delivery_revenue) + float(today_dine_in_revenue)
        
        # Pending orders
        pending_orders = Order.objects.filter(
            restaurant=restaurant,
            current_status__in=['paid', 'preparing']
        ).count()
        
        # Monthly statistics
        month_start = today.replace(day=1)
        monthly_orders = Order.objects.filter(
            restaurant=restaurant,
            order_date__date__gte=month_start
        )
        monthly_revenue = monthly_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        # Popular products
        popular_products = OrderDetail.objects.filter(
            order__restaurant=restaurant
        ).values(
            'product__product_name', 'product__product_id'
        ).annotate(
            order_count=Count('order_detail_id')
        ).order_by('-order_count')[:5]
        
        # Recent reviews
        recent_reviews = Review.objects.filter(
            restaurant=restaurant
        ).order_by('-review_date')[:5]
        
        return Response({
            'server_time': {
                'utc': now_utc.isoformat(),
                'bangkok': now_bangkok.isoformat(),
            },
            'restaurant': {
                'name': restaurant.restaurant_name,
                'average_rating': restaurant.average_rating,
                'total_reviews': restaurant.total_reviews,
            },
            'today': {
                'orders': today_orders_count,
                'revenue': today_revenue,
                'pending_orders': pending_orders,
            },
            'monthly': {
                'orders': monthly_orders.count(),
                'revenue': monthly_revenue,
            },
            'popular_products': popular_products,
            'recent_reviews': ReviewSerializer(recent_reviews, many=True).data,
        })
    
    @action(detail=False, methods=['get'])
    def customer(self, request):
        """Customer dashboard"""
        user = request.user
        
        # Order statistics
        total_orders = Order.objects.filter(user=user).count()
        active_orders = Order.objects.filter(
            user=user,
            current_status__in=['pending', 'paid', 'preparing', 'ready_for_pickup', 'delivering']
        ).count()
        
        # Spending statistics
        total_spent = Order.objects.filter(
            user=user,
            current_status='completed'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        # Favorite restaurants
        from django.db.models import Count
        favorite_restaurants = Order.objects.filter(
            user=user
        ).values(
            'restaurant__restaurant_id', 'restaurant__restaurant_name'
        ).annotate(
            order_count=Count('order_id')
        ).order_by('-order_count')[:5]
        
        # Recent orders
        recent_orders = Order.objects.filter(
            user=user
        ).order_by('-order_date')[:5]
        
        return Response({
            'statistics': {
                'total_orders': total_orders,
                'active_orders': active_orders,
                'total_spent': total_spent,
            },
            'favorite_restaurants': favorite_restaurants,
            'recent_orders': OrderSerializer(recent_orders, many=True).data,
        })


class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def sales(self, request):
        """Generate sales report"""
        if request.user.role not in ['admin', 'special_restaurant', 'general_restaurant']:
            return Response({'error': 'Permission denied'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        # Get date range
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        # Base query
        orders = Order.objects.filter(current_status='completed')
        
        # Filter by restaurant for restaurant owners
        if request.user.role in ['special_restaurant', 'general_restaurant']:
            try:
                restaurant = request.user.restaurant
                orders = orders.filter(restaurant=restaurant)
            except Restaurant.DoesNotExist:
                return Response({'error': 'Restaurant not found'}, 
                              status=status.HTTP_404_NOT_FOUND)
        
        # Apply date filters
        if date_from:
            orders = orders.filter(order_date__date__gte=date_from)
        if date_to:
            orders = orders.filter(order_date__date__lte=date_to)
        
        # Calculate statistics
        total_sales = orders.count()
        total_revenue = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        average_order_value = total_revenue / total_sales if total_sales > 0 else 0
        
        # Sales by day
        daily_sales = orders.extra(
            select={'date': 'DATE(order_date)'}
        ).values('date').annotate(
            count=Count('order_id'),
            revenue=Sum('total_amount')
        ).order_by('date')
        
        return Response({
            'summary': {
                'total_sales': total_sales,
                'total_revenue': total_revenue,
                'average_order_value': average_order_value,
            },
            'daily_sales': list(daily_sales),
        })
    
    @action(detail=False, methods=['get'])
    def products(self, request):
        """Generate product performance report"""
        if request.user.role not in ['admin', 'special_restaurant', 'general_restaurant']:
            return Response({'error': 'Permission denied'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        # Get filters
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        restaurant_id = request.query_params.get('restaurant_id')
        
        # Base query
        order_details = OrderDetail.objects.filter(
            order__current_status='completed'
        )
        
        # Filter by restaurant
        if request.user.role in ['special_restaurant', 'general_restaurant']:
            try:
                restaurant = request.user.restaurant
                order_details = order_details.filter(order__restaurant=restaurant)
            except Restaurant.DoesNotExist:
                return Response({'error': 'Restaurant not found'}, 
                              status=status.HTTP_404_NOT_FOUND)
        elif restaurant_id:
            order_details = order_details.filter(order__restaurant_id=restaurant_id)
        
        # Apply date filters
        if date_from:
            order_details = order_details.filter(order__order_date__date__gte=date_from)
        if date_to:
            order_details = order_details.filter(order__order_date__date__lte=date_to)
        
        # Product performance
        product_performance = order_details.values(
            'product__product_id',
            'product__product_name',
            'product__category__category_name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('subtotal'),
            order_count=Count('order_detail_id')
        ).order_by('-total_revenue')[:20]
        
        return Response({
            'products': list(product_performance),
        })


class AppSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing application settings
    Only admin can modify settings, but everyone can read
    """
    serializer_class = AppSettingsSerializer
    http_method_names = ['get', 'put', 'patch']  # ไม่อนุญาต create/delete เพราะมี settings record เดียว
    
    def get_queryset(self):
        # ใช้ singleton pattern - มี settings record เดียว
        settings = AppSettings.get_settings()
        if not settings:
            return AppSettings.objects.none()
        return AppSettings.objects.filter(pk=settings.pk).order_by('pk')
    
    def get_permissions(self):
        """
        อนุญาตให้ทุกคนอ่านได้ แต่แก้ไขได้เฉพาะ admin
        """
        if self.action in ['list', 'retrieve', 'public']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated, IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def perform_update(self, serializer):
        """บันทึกผู้ที่แก้ไขล่าสุด"""
        serializer.save(updated_by=self.request.user)
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def public(self, request):
        """
        Endpoint สำหรับดึงข้อมูล public settings ที่ไม่ต้อง authentication
        """
        try:
            settings = AppSettings.get_settings()
            
            # ใช้ serializer ปกติเพื่อความปลอดภัย
            serializer = self.get_serializer(settings)
            data = serializer.data
            
            # สร้าง public data ที่ปลอดภัย
            public_data = {
                'id': data.get('id'),
                'app_name': data.get('app_name', ''),
                'app_description': data.get('app_description', ''),
                'logo_url': data.get('logo_url', ''),
                'banner_url': data.get('banner_url', ''),
                'contact_email': data.get('contact_email', ''),
                'contact_phone': data.get('contact_phone', ''),
                'contact_address': data.get('contact_address', ''),
                'hero_title': data.get('hero_title', ''),
                'hero_subtitle': data.get('hero_subtitle', ''),
                'feature_1_title': data.get('feature_1_title', ''),
                'feature_1_description': data.get('feature_1_description', ''),
                'feature_1_icon': data.get('feature_1_icon', ''),
                'feature_2_title': data.get('feature_2_title', ''),
                'feature_2_description': data.get('feature_2_description', ''),
                'feature_2_icon': data.get('feature_2_icon', ''),
                'feature_3_title': data.get('feature_3_title', ''),
                'feature_3_description': data.get('feature_3_description', ''),
                'feature_3_icon': data.get('feature_3_icon', ''),
                'facebook_url': data.get('facebook_url', ''),
                'instagram_url': data.get('instagram_url', ''),
                'twitter_url': data.get('twitter_url', ''),
                'maintenance_mode': data.get('maintenance_mode', False),
                'maintenance_message': data.get('maintenance_message', ''),
                'timezone': data.get('timezone', 'Asia/Bangkok'),
                'currency': data.get('currency', 'THB'),
                'bank_name': data.get('bank_name', ''),
                'bank_account_number': data.get('bank_account_number', ''),
                'bank_account_name': data.get('bank_account_name', ''),
                'qr_code_url': data.get('qr_code_url', ''),
                # ข้อมูลค่าจัดส่ง - ใช้ค่าจาก serializer
                'base_delivery_fee': data.get('base_delivery_fee', 20.0),
                'free_delivery_minimum': data.get('free_delivery_minimum', 200.0),
                'free_delivery_minimum_amount': data.get('free_delivery_minimum', 200.0),
                'max_delivery_distance': data.get('max_delivery_distance', 10.0),
                'per_km_fee': data.get('per_km_fee', 5.0),
                # ไม่ใช้ multi_restaurant_base_fee และ multi_restaurant_additional_fee แล้ว
                # 'multi_restaurant_base_fee': data.get('multi_restaurant_base_fee', 2.0),
                # 'multi_restaurant_additional_fee': data.get('multi_restaurant_additional_fee', 1.0),
                'delivery_time_slots': data.get('delivery_time_slots', '09:00-21:00'),
                'enable_scheduled_delivery': data.get('enable_scheduled_delivery', True),
                'rush_hour_multiplier': data.get('rush_hour_multiplier', 1.5),
                'weekend_multiplier': data.get('weekend_multiplier', 1.2),
            }
            
            return Response(public_data)
            
        except AppSettings.DoesNotExist:
            return Response({"detail": "App settings not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print("---------------------------------------------------")
            print(f"Error in public app settings endpoint: {e}")
            import traceback
            traceback.print_exc()
            print("---------------------------------------------------")
            return Response({"detail": "An internal server error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LanguageViewSet(viewsets.ModelViewSet):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name']
    ordering_fields = ['code', 'name', 'created_at']
    ordering = ['code']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]  # เฉพาะ admin เท่านั้นที่สามารถแก้ไขข้อมูลภาษาได้
        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['get'])
    def default(self, request):
        """Get default language"""
        try:
            default_lang = Language.objects.get(is_default=True)
            serializer = self.get_serializer(default_lang)
            return Response(serializer.data)
        except Language.DoesNotExist:
            return Response({'error': 'No default language set'}, status=status.HTTP_404_NOT_FOUND)


class TranslationViewSet(viewsets.ModelViewSet):
    queryset = Translation.objects.all()
    serializer_class = TranslationSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['key', 'value']
    ordering_fields = ['key', 'group', 'created_at']
    ordering = ['key']
    filterset_fields = ['language', 'group']

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'by_language']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]  # เฉพาะ admin เท่านั้นที่สามารถแก้ไขข้อมูลแปลได้
        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['get'])
    def by_language(self, request):
        """Get translations for a specific language"""
        lang_code = request.query_params.get('lang', None)
        if not lang_code:
            return Response({'error': 'Language code is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            language = Language.objects.get(code=lang_code, is_active=True)
        except Language.DoesNotExist:
            return Response({'error': 'Language not found or not active'}, status=status.HTTP_404_NOT_FOUND)

        translations = self.get_queryset().filter(language=language)
        
        # Group translations if requested
        group_by = request.query_params.get('group_by', None)
        if group_by == 'group':
            grouped_translations = {}
            for trans in translations:
                if trans.group not in grouped_translations:
                    grouped_translations[trans.group] = {}
                grouped_translations[trans.group][trans.key] = trans.value
            return Response(grouped_translations)
        
        serializer = self.get_serializer(translations, many=True)
        
        # เพิ่ม metadata สำหรับ cache management
        # ส่ง last_updated timestamp เพื่อให้ frontend ตรวจสอบว่าควร refresh cache หรือไม่
        last_updated = translations.order_by('-updated_at').first()
        response_data = serializer.data
        
        # ถ้ามี only_check_version parameter ให้ส่งแค่ metadata
        if request.query_params.get('only_check_version') == 'true':
            return Response({
                'last_updated': last_updated.updated_at.isoformat() if last_updated and last_updated.updated_at else None,
                'count': translations.count()
            })
        
        # เพิ่ม header สำหรับ version checking
        response = Response(response_data)
        if last_updated and last_updated.updated_at:
            response['X-Translations-Last-Updated'] = last_updated.updated_at.isoformat()
            response['X-Translations-Count'] = str(translations.count())
        
        return response


class GuestOrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับการสั่งซื้อแบบไม่ต้องล็อกอิน
    ใช้ Temporary ID เพื่อติดตามคำสั่งซื้อ
    รองรับ multi-restaurant จริง
    """
    serializer_class = GuestOrderSerializer
    permission_classes = [AllowAny]  # ไม่ต้องล็อกอิน
    
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if user.role == 'admin':
                return GuestOrder.objects.all()
            elif user.role in ['special_restaurant', 'general_restaurant']:
                try:
                    # filter ทั้ง single restaurant และ multi-restaurant ที่มีร้านนี้อยู่
                    restaurant = user.restaurant
                    return GuestOrder.objects.filter(
                        Q(restaurant=restaurant) |
                        Q(restaurants__contains=[{"restaurant_id": restaurant.restaurant_id}])
                    )
                except Restaurant.DoesNotExist:
                    return GuestOrder.objects.none()
        return GuestOrder.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateGuestOrderSerializer
        elif self.action == 'track':
            return GuestOrderTrackingSerializer
        elif self.action == 'multi':
            return GuestMultiRestaurantOrderSerializer
        return GuestOrderSerializer

    def create(self, request, *args, **kwargs):
        try:
            if 'order_data' in request.data:
                order_data_str = request.data.get('order_data')
                proof_of_payment = request.FILES.get('proof_of_payment')
                if not order_data_str:
                    return Response({'error': 'order_data is required'}, status=status.HTTP_400_BAD_REQUEST)
                import json
                order_data = json.loads(order_data_str)
            else:
                order_data = request.data
                proof_of_payment = None
            serializer = self.get_serializer(data=order_data)
            serializer.is_valid(raise_exception=True)
            guest_order = serializer.save()
            if proof_of_payment:
                guest_order.proof_of_payment = proof_of_payment
                guest_order.save()
            # ไม่ส่ง notification และ WebSocket สำหรับ phone orders (ไม่มี email)
            if guest_order.customer_email:
                admin_users = User.objects.filter(role='admin')
                for admin_user in admin_users:
                    Notification.objects.create(
                        user=admin_user,
                        title='New Guest Order Received',
                        message=f'Guest order #{guest_order.guest_order_id} ({guest_order.temporary_id}) was placed by {guest_order.customer_name}',
                        type='guest_order',
                        related_guest_order=guest_order
                    )
                # ส่ง WebSocket notification ไปยังกลุ่มแอดมิน (รองรับ multi-restaurant)
                channel_layer = get_channel_layer()
                restaurant_name = 'Multi-Restaurant Guest Order' if guest_order.is_multi_restaurant else (guest_order.restaurant.restaurant_name if guest_order.restaurant else '-')
                async_to_sync(channel_layer.group_send)(
                    "orders_admin",
                    {
                        'type': 'new_guest_order',
                        'order_id': guest_order.guest_order_id,
                        'temporary_id': guest_order.temporary_id,
                        'customer_name': guest_order.customer_name,
                        'restaurant_name': restaurant_name,
                        'total_amount': str(guest_order.total_amount),
                        'timestamp': timezone.now().isoformat()
                    }
                )
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            return Response(
                {'error': f'Failed to create guest order: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def track(self, request):
        temporary_id = request.query_params.get('temporary_id')
        if not temporary_id:
            return Response({'error': 'temporary_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            guest_order = GuestOrder.objects.select_related('restaurant').prefetch_related(
                'order_details__product__translations__language'
            ).get(temporary_id=temporary_id)
            from django.utils import timezone
            if guest_order.expires_at and guest_order.expires_at < timezone.now():
                return Response({'error': 'Order has expired'}, status=status.HTTP_410_GONE)
            serializer = GuestOrderTrackingSerializer(guest_order, context={'request': request})
            return Response(serializer.data)
        except GuestOrder.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def update_status(self, request, pk=None):
        guest_order = self.get_object()
        new_status = request.data.get('status')
        note = request.data.get('note', '')
        if not new_status:
            return Response({'error': 'status is required'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status not in dict(GuestOrder.STATUS_CHOICES):
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        old_status = guest_order.current_status
        guest_order.current_status = new_status
        guest_order.save()
        GuestDeliveryStatusLog.objects.create(
            guest_order=guest_order,
            status=new_status,
            note=note,
            updated_by_user=request.user
        )
        
        # ไม่ต้องส่ง notification ให้แอดมิน เพราะแอดมินเป็นคนอัปเดตเอง
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"guest_order_{guest_order.temporary_id}",
            {
                'type': 'guest_order_status_update',
                'order_id': guest_order.guest_order_id,
                'temporary_id': guest_order.temporary_id,
                'old_status': old_status,
                'new_status': new_status,
                'note': note,
                'timestamp': timezone.now().isoformat()
            }
        )
        async_to_sync(channel_layer.group_send)(
            "guest_orders_all",
            {
                'type': 'guest_order_status_update',
                'order_id': guest_order.guest_order_id,
                'temporary_id': guest_order.temporary_id,
                'old_status': old_status,
                'new_status': new_status,
                'note': note,
                'timestamp': timezone.now().isoformat()
            }
        )
        return Response({
            'message': 'Status updated successfully',
            'old_status': old_status,
            'new_status': new_status
        })

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def multi(self, request):
        try:
            order_data_str = request.data.get('order_data')
            proof_of_payment = request.FILES.get('proof_of_payment')
            if not order_data_str:
                return Response({'error': 'order_data is required'}, status=status.HTTP_400_BAD_REQUEST)
            import json
            order_data = json.loads(order_data_str)
            serializer = GuestMultiRestaurantOrderSerializer(data=order_data)
            if serializer.is_valid():
                guest_order = serializer.save()
                if proof_of_payment:
                    guest_order.proof_of_payment = proof_of_payment
                    guest_order.save()
                # ไม่ส่ง notification และ WebSocket สำหรับ phone orders (ไม่มี email)
                if guest_order.customer_email:
                    admin_users = User.objects.filter(role='admin')
                    for admin_user in admin_users:
                        Notification.objects.create(
                            user=admin_user,
                            title='New Multi-Restaurant Guest Order Received',
                            message=f'Multi-restaurant guest order #{guest_order.guest_order_id} ({guest_order.temporary_id}) was placed by {guest_order.customer_name}',
                            type='guest_order',
                            related_guest_order=guest_order
                        )
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        "orders_admin",
                        {
                            'type': 'new_guest_order',
                            'order_id': guest_order.guest_order_id,
                            'temporary_id': guest_order.temporary_id,
                            'customer_name': guest_order.customer_name,
                            'restaurant_name': 'Multi-Restaurant Guest Order',
                            'total_amount': str(guest_order.total_amount),
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                return Response(GuestOrderSerializer(guest_order).data, status=status.HTTP_201_CREATED)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Failed to create multi-restaurant guest order: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        """ลบ Guest Order (เฉพาะแอดมิน)"""
        # ตรวจสอบ permission - เฉพาะ admin เท่านั้น
        if request.user.role != 'admin':
            return Response(
                {'error': 'เฉพาะแอดมินเท่านั้นที่สามารถลบ Guest Order ได้'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        guest_order = self.get_object()
        order_id = guest_order.guest_order_id
        temporary_id = guest_order.temporary_id
        
        # ส่ง WebSocket notification ก่อนลบ
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"guest_order_{temporary_id}",
            {
                'type': 'guest_order_deleted',
                'order_id': order_id,
                'temporary_id': temporary_id,
                'message': 'Guest Order ของคุณถูกลบโดยระบบ',
                'timestamp': timezone.now().isoformat()
            }
        )
        
        # ส่ง notification ให้แอดมินคนอื่น
        async_to_sync(channel_layer.group_send)(
            "guest_orders_all",
            {
                'type': 'guest_order_deleted',
                'order_id': order_id,
                'temporary_id': temporary_id,
                'message': f'Guest Order #{temporary_id} ถูกลบโดย {request.user.username}',
                'timestamp': timezone.now().isoformat()
            }
        )
        
        # ลบ Guest Order (Django จะลบข้อมูลที่เกี่ยวข้องอัตโนมัติเพราะ CASCADE)
        guest_order.delete()
        
        return Response(
            {
                'success': True, 
                'message': f'ลบ Guest Order #{temporary_id} เรียบร้อยแล้ว'
            },
            status=status.HTTP_200_OK
        )


class AdvertisementViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับจัดการโฆษณา/แบนเนอร์ (เก็บแค่รูปภาพ)
    - Admin: สามารถจัดการได้ทั้งหมด (CRUD)
    - ผู้ใช้ทั่วไป: ดูได้เฉพาะโฆษณาที่เปิดใช้งาน
    """
    queryset = Advertisement.objects.all()
    serializer_class = AdvertisementSerializer
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    ordering_fields = ['sort_order', 'created_at']
    ordering = ['sort_order', '-created_at']
    filterset_fields = ['is_active']
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    def get_queryset(self):
        queryset = Advertisement.objects.all()
        
        # ถ้าไม่ใช่แอดมิน ให้แสดงเฉพาะโฆษณาที่เปิดใช้งาน
        if not self.request.user.is_authenticated or self.request.user.role != 'admin':
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    def get_permissions(self):
        """
        - list, retrieve, active: ทุกคนดูได้
        - create, update, delete: เฉพาะ admin
        """
        if self.action in ['list', 'retrieve', 'active']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated, IsAdminUser]
        return [permission() for permission in permission_classes]
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def active(self, request):
        """
        ดึงเฉพาะโฆษณาที่เปิดใช้งาน สำหรับแสดงบนหน้าเว็บ
        """
        advertisements = Advertisement.objects.filter(
            is_active=True
        ).order_by('sort_order', '-created_at')
        
        serializer = self.get_serializer(advertisements, many=True)
        return Response(serializer.data)


# API endpoint สำหรับคำนวณค่าจัดส่งตามระยะทาง
@api_view(['POST'])
@permission_classes([AllowAny])
def calculate_delivery_fee_api(request):
    """
    API endpoint สำหรับคำนวณค่าจัดส่งตามระยะทาง
    รับ restaurant_id และ delivery coordinates
    """
    try:
        restaurant_id = request.data.get('restaurant_id')
        delivery_lat = request.data.get('delivery_latitude')
        delivery_lon = request.data.get('delivery_longitude')
        order_subtotal_raw = request.data.get('order_subtotal')

        if not all([restaurant_id, delivery_lat, delivery_lon]):
            return Response(
                {'error': 'Missing required fields: restaurant_id, delivery_latitude, delivery_longitude'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_subtotal = None
        if order_subtotal_raw not in (None, ''):
            try:
                order_subtotal = float(order_subtotal_raw)
            except (TypeError, ValueError):
                return Response(
                    {'error': 'order_subtotal must be a valid number'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if order_subtotal < 0:
                return Response(
                    {'error': 'order_subtotal must be greater than or equal to 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            restaurant = Restaurant.objects.get(restaurant_id=restaurant_id)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not restaurant.latitude or not restaurant.longitude:
            return Response(
                {'error': 'Restaurant location not set. Please set restaurant coordinates in admin.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .utils import calculate_delivery_fee_by_distance
        fee = calculate_delivery_fee_by_distance(
            restaurant.latitude, restaurant.longitude,
            delivery_lat, delivery_lon
        )

        # คำนวณระยะทางด้วย
        from .utils import calculate_distance_km
        distance = calculate_distance_km(
            restaurant.latitude, restaurant.longitude,
            delivery_lat, delivery_lon
        )

        settings = AppSettings.get_settings()
        max_delivery_distance = (
            float(settings.max_delivery_distance)
            if settings and settings.max_delivery_distance is not None
            else None
        )
        free_delivery_minimum = (
            float(settings.free_delivery_minimum)
            if settings and settings.free_delivery_minimum is not None
            else None
        )
        is_free_delivery = (
            order_subtotal is not None
            and free_delivery_minimum is not None
            and free_delivery_minimum > 0
            and order_subtotal >= free_delivery_minimum
        )

        if max_delivery_distance is not None and distance > max_delivery_distance:
            return Response(
                {
                    'delivery_fee': 0.0,
                    'error': (
                        f'Delivery location is out of range. '
                        f'Maximum distance is {max_delivery_distance:.2f} km.'
                    ),
                    'error_code': 'out_of_delivery_range',
                    'within_delivery_range': False,
                    'distance_km': round(distance, 2),
                    'max_delivery_distance_km': round(max_delivery_distance, 2),
                    'free_delivery_minimum_amount': round(free_delivery_minimum, 2) if free_delivery_minimum is not None else None,
                    'order_subtotal': round(order_subtotal, 2) if order_subtotal is not None else None,
                    'restaurant_id': restaurant.restaurant_id,
                    'restaurant_name': restaurant.restaurant_name,
                },
                status=status.HTTP_200_OK
            )

        final_fee = 0.0 if is_free_delivery else float(fee)
        return Response({
            'delivery_fee': round(final_fee, 5),
            'distance_km': round(distance, 2),
            'max_delivery_distance_km': round(max_delivery_distance, 2) if max_delivery_distance is not None else None,
            'free_delivery_minimum_amount': round(free_delivery_minimum, 2) if free_delivery_minimum is not None else None,
            'order_subtotal': round(order_subtotal, 2) if order_subtotal is not None else None,
            'is_free_delivery': is_free_delivery,
            'within_delivery_range': True
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def calculate_multi_restaurant_delivery_fee_api(request):
    """
    API endpoint สำหรับคำนวณค่าจัดส่งสำหรับ multi-restaurant order
    รับ list ของ restaurant_ids และ delivery coordinates
    ใช้วิธี Base + Additional: ค่าจัดส่งร้านหลัก + ค่าเพิ่มต่อร้านเพิ่มเติม
    """
    try:
        restaurant_ids = request.data.get('restaurant_ids', [])
        delivery_lat = request.data.get('delivery_latitude')
        delivery_lon = request.data.get('delivery_longitude')
        order_subtotal_raw = request.data.get('order_subtotal')
        
        if not all([restaurant_ids, delivery_lat, delivery_lon]):
            return Response(
                {'error': 'Missing required fields: restaurant_ids (array), delivery_latitude, delivery_longitude'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not isinstance(restaurant_ids, list):
            return Response(
                {'error': 'restaurant_ids must be an array'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        order_subtotal = None
        if order_subtotal_raw not in (None, ''):
            try:
                order_subtotal = float(order_subtotal_raw)
            except (TypeError, ValueError):
                return Response(
                    {'error': 'order_subtotal must be a valid number'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if order_subtotal < 0:
                return Response(
                    {'error': 'order_subtotal must be greater than or equal to 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        from .utils import calculate_delivery_fee_by_distance, calculate_distance_km
        from .models import AppSettings
        
        # ดึงการตั้งค่าค่าจัดส่งสำหรับ multi-restaurant
        settings = AppSettings.get_settings()
        # ไม่ใช้ base_fee_override เพื่อป้องกันการ override ค่าจัดส่งจริง
        # base_fee_override = float(settings.multi_restaurant_base_fee) if settings and settings.multi_restaurant_base_fee else None
        additional_fee_per_restaurant = float(settings.multi_restaurant_additional_fee) if settings and settings.multi_restaurant_additional_fee else 15.00
        max_delivery_distance = (
            float(settings.max_delivery_distance)
            if settings and settings.max_delivery_distance is not None
            else None
        )
        free_delivery_minimum = (
            float(settings.free_delivery_minimum)
            if settings and settings.free_delivery_minimum is not None
            else None
        )
        
        max_fee = 0.0
        max_distance = 0.0
        base_restaurant_id = None
        restaurant_details = []
        out_of_range_restaurants = []
        
        # หาร้านที่ไกลที่สุด (จะเป็นร้านหลัก)
        for restaurant_id in restaurant_ids:
            try:
                restaurant = Restaurant.objects.get(restaurant_id=restaurant_id)
            except Restaurant.DoesNotExist:
                continue
            
            if not restaurant.latitude or not restaurant.longitude:
                continue
            
            distance = calculate_distance_km(
                restaurant.latitude, restaurant.longitude,
                delivery_lat, delivery_lon
            )
            
            fee = calculate_delivery_fee_by_distance(
                restaurant.latitude, restaurant.longitude,
                delivery_lat, delivery_lon
            )
            
            restaurant_details.append({
                'restaurant_id': restaurant.restaurant_id,
                'restaurant_name': restaurant.restaurant_name,
                'distance_km': round(distance, 2),
                'individual_delivery_fee': round(float(fee), 2)
            })

            if max_delivery_distance is not None and distance > max_delivery_distance:
                out_of_range_restaurants.append({
                    'restaurant_id': restaurant.restaurant_id,
                    'restaurant_name': restaurant.restaurant_name,
                    'distance_km': round(distance, 2)
                })
            
            # หาร้านที่มีค่าจัดส่งสูงสุด (ไกลสุด) เป็นร้านหลัก
            if fee > max_fee:
                max_fee = fee
                max_distance = distance
                base_restaurant_id = restaurant.restaurant_id
        
        if not restaurant_details:
            return Response(
                {'error': 'No valid restaurants found'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if out_of_range_restaurants:
            farthest_restaurant = max(out_of_range_restaurants, key=lambda item: item['distance_km'])
            return Response(
                {
                    'total_delivery_fee': 0.0,
                    'original_total_delivery_fee': 0.0,
                    'error': (
                        f"Delivery location is out of range. "
                        f"Maximum distance is {max_delivery_distance:.2f} km."
                    ),
                    'error_code': 'out_of_delivery_range',
                    'within_delivery_range': False,
                    'max_delivery_distance_km': round(max_delivery_distance, 2),
                    'max_distance_km': round(max_distance, 2),
                    'free_delivery_minimum_amount': round(free_delivery_minimum, 2) if free_delivery_minimum is not None else None,
                    'order_subtotal': round(order_subtotal, 2) if order_subtotal is not None else None,
                    'farthest_restaurant': farthest_restaurant,
                    'out_of_range_restaurants': out_of_range_restaurants
                },
                status=status.HTTP_200_OK
            )
        
        # คำนวณค่าจัดส่งแบบ Base + Additional
        # ใช้ค่าจัดส่งจริงจากร้านไกลสุดเสมอ (ไม่ให้ setting override)
        base_fee = max_fee  # ค่าจัดส่งจากร้านไกลสุด
        additional_restaurants_count = len(restaurant_ids) - 1  # ร้านเพิ่มเติม (ไม่นับร้านหลัก)
        additional_fee = additional_restaurants_count * additional_fee_per_restaurant
        total_delivery_fee = base_fee + additional_fee
        original_total_delivery_fee = float(total_delivery_fee)
        is_free_delivery = (
            order_subtotal is not None
            and free_delivery_minimum is not None
            and free_delivery_minimum > 0
            and order_subtotal >= free_delivery_minimum
        )
        if is_free_delivery:
            total_delivery_fee = 0.0
        
        # อัปเดต restaurant_details ให้แสดงข้อมูลที่ชัดเจนขึ้น
        for detail in restaurant_details:
            if detail['restaurant_id'] == base_restaurant_id:
                detail['role'] = 'base_restaurant'
                detail['fee_contribution'] = round(base_fee, 2)
            else:
                detail['role'] = 'additional_restaurant'
                detail['fee_contribution'] = additional_fee_per_restaurant

        explanation_text = (
            f'ค่าจัดส่งหลัก {base_fee:.2f} บาท + '
            f'ค่าเพิ่มร้านเพิ่มเติม {additional_restaurants_count} ร้าน '
            f'× {additional_fee_per_restaurant:.2f} บาท = {original_total_delivery_fee:.2f} บาท'
        )
        if is_free_delivery:
            explanation_text = (
                explanation_text
                + f' | ส่งฟรีเมื่อยอดสั่งซื้อ {order_subtotal:.2f} บาท '
                f'ถึงขั้นต่ำ {free_delivery_minimum:.2f} บาท'
            )
        
        return Response({
            'total_delivery_fee': round(float(total_delivery_fee), 5),
            'original_total_delivery_fee': round(original_total_delivery_fee, 5),
            'base_fee': round(float(base_fee), 2),
            'additional_fee': round(float(additional_fee), 2),
            'additional_fee_per_restaurant': additional_fee_per_restaurant,
            'base_restaurant_id': base_restaurant_id,
            'total_restaurants': len(restaurant_ids),
            'additional_restaurants': additional_restaurants_count,
            'max_distance_km': round(max_distance, 2),
            'max_delivery_distance_km': round(max_delivery_distance, 2) if max_delivery_distance is not None else None,
            'free_delivery_minimum_amount': round(free_delivery_minimum, 2) if free_delivery_minimum is not None else None,
            'order_subtotal': round(order_subtotal, 2) if order_subtotal is not None else None,
            'is_free_delivery': is_free_delivery,
            'free_delivery_discount': round(original_total_delivery_fee, 5) if is_free_delivery else 0.0,
            'within_delivery_range': True,
            'calculation_method': 'base_plus_additional',
            'actual_max_fee_from_distance': round(float(max_fee), 2),
            'explanation': explanation_text,
            'fee_breakdown': {
                'base_description': f'ค่าจัดส่งหลัก (ร้านไกลสุด: {max_fee:.2f} บาท)',
                'additional_description': f'ค่าเพิ่มร้านเพิ่มเติม ({additional_restaurants_count} ร้าน)',
                'base_amount': round(float(base_fee), 2),
                'additional_amount': round(float(additional_fee), 2),
                'original_total_amount': round(original_total_delivery_fee, 2),
                'free_delivery_applied': is_free_delivery,
                'free_delivery_discount': round(original_total_delivery_fee, 2) if is_free_delivery else 0.0,
                'total_amount': round(float(total_delivery_fee), 2)
            },
            'restaurants': restaurant_details
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ===== Dine-In QR Code System Views =====

class DineInProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับจัดการสินค้า Dine-in
    - ร้านอาหารสามารถ CRUD สินค้าของตัวเองได้
    - ไม่ต้องผ่านแอดมิน
    """
    serializer_class = DineInProductSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['restaurant', 'category', 'is_available', 'is_recommended']
    search_fields = ['product_name', 'description', 'translations__translated_name', 'translations__translated_description']
    ordering_fields = ['sort_order', 'product_name', 'price', 'created_at']
    ordering = ['sort_order', 'product_name']
    
    def get_queryset(self):
        """ร้านอาหารเห็นเฉพาะสินค้าของตัวเอง"""
        user = self.request.user
        
        # ถ้าเป็น public request (AllowAny) ให้ดูได้ทั้งหมดที่ available
        if not user.is_authenticated:
            return DineInProduct.objects.filter(is_available=True).prefetch_related('translations__language')
        
        if user.role == 'admin':
            return DineInProduct.objects.all().prefetch_related('translations__language')
        elif user.role in ['special_restaurant', 'general_restaurant']:
            if hasattr(user, 'restaurant'):
                return DineInProduct.objects.filter(restaurant=user.restaurant).prefetch_related('translations__language')
        
        # สำหรับลูกค้า - ดูเฉพาะที่ available
        return DineInProduct.objects.filter(is_available=True).prefetch_related('translations__language')
    
    def perform_create(self, serializer):
        """สร้างสินค้า - ต้องเป็นของร้านตัวเอง"""
        user = self.request.user
        if user.role in ['special_restaurant', 'general_restaurant']:
            try:
                restaurant = Restaurant.objects.get(user=user)
                serializer.save(restaurant=restaurant)
            except Restaurant.DoesNotExist:
                raise ValidationError({'error': 'Restaurant not found for this user'})
        elif user.role == 'admin':
            serializer.save()
        else:
            raise ValidationError({'error': 'Only restaurant owners can create products'})

    def perform_update(self, serializer):
        product = serializer.save()
        self._broadcast_dine_in_product_changed(
            action='updated',
            product=product,
            is_available=product.is_available
        )

    def perform_destroy(self, instance):
        restaurant_id = instance.restaurant.restaurant_id if instance.restaurant else None
        dine_in_product_id = instance.dine_in_product_id

        instance.delete()

        self._broadcast_dine_in_product_changed(
            action='deleted',
            restaurant_id=restaurant_id,
            dine_in_product_id=dine_in_product_id,
            is_available=False
        )

    def _broadcast_dine_in_product_changed(
        self,
        action,
        product=None,
        restaurant_id=None,
        dine_in_product_id=None,
        is_available=None
    ):
        try:
            if product is not None:
                restaurant_id = product.restaurant.restaurant_id if product.restaurant else restaurant_id
                dine_in_product_id = product.dine_in_product_id
                is_available = product.is_available if is_available is None else is_available

            if not restaurant_id or not dine_in_product_id:
                return

            channel_layer = get_channel_layer()
            if not channel_layer:
                return

            async_to_sync(channel_layer.group_send)(
                f"dine_in_restaurant_{restaurant_id}",
                {
                    'type': 'dine_in_product_changed',
                    'action': action,
                    'restaurant_id': restaurant_id,
                    'dine_in_product_id': dine_in_product_id,
                    'is_available': is_available,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to broadcast dine-in product change: {str(e)}")

    def get_permissions(self):
        """ถ้าเป็น list/retrieve ให้ AllowAny เพื่อลูกค้าดูได้"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]


class RestaurantTableViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับจัดการโต๊ะของร้านอาหาร
    - ร้านอาหารสามารถสร้าง/แก้ไข/ลบโต๊ะของตัวเองได้
    - สามารถสร้าง QR Code สำหรับแต่ละโต๊ะ
    """
    serializer_class = RestaurantTableSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['restaurant', 'is_active']
    search_fields = ['table_number']
    ordering_fields = ['table_number', 'created_at']
    ordering = ['table_number']
    
    def get_permissions(self):
        """ถ้าเป็น get_by_qr_code ให้ AllowAny เพราะลูกค้าไม่ได้ login"""
        if self.action == 'get_by_qr_code':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        """ร้านอาหารเห็นเฉพาะโต๊ะของตัวเอง, admin เห็นทั้งหมด"""
        user = self.request.user
        if user.role == 'admin':
            return RestaurantTable.objects.all()
        elif user.role in ['special_restaurant', 'general_restaurant']:
            if hasattr(user, 'restaurant'):
                return RestaurantTable.objects.filter(restaurant=user.restaurant)
        return RestaurantTable.objects.none()
    
    def perform_create(self, serializer):
        """สร้างโต๊ะใหม่ - ต้องเป็นของร้านตัวเอง"""
        user = self.request.user
        if user.role in ['special_restaurant', 'general_restaurant']:
            try:
                restaurant = Restaurant.objects.get(user=user)
                serializer.save(restaurant=restaurant)
            except Restaurant.DoesNotExist:
                raise ValidationError({'error': 'Restaurant not found for this user'})
        elif user.role == 'admin':
            # Admin ต้องส่ง restaurant_id มาด้วย
            serializer.save()
        else:
            raise ValidationError({'error': 'Only restaurant owners can create tables'})
    
    @action(detail=True, methods=['post'], url_path='generate-qr')
    def generate_qr(self, request, pk=None):
        """
        สร้าง QR Code image สำหรับโต๊ะ
        ใช้ library qrcode เพื่อสร้างรูป QR Code
        """
        table = self.get_object()
        
        try:
            import qrcode
            from io import BytesIO
            from django.core.files.base import ContentFile
            import os
            
            # สร้าง QR Code URL
            from django.conf import settings
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            qr_url = f"{frontend_url}/dine-in/{table.qr_code_data}"
            
            # สร้าง QR Code image
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # บันทึกเป็นไฟล์
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            file_name = f"table_{table.restaurant.restaurant_id}_{table.table_number}_qr.png"
            
            table.qr_code_image.save(
                file_name,
                ContentFile(buffer.getvalue()),
                save=True
            )
            
            serializer = self.get_serializer(table)
            return Response({
                'message': 'QR Code generated successfully',
                'table': serializer.data
            }, status=status.HTTP_200_OK)
            
        except ImportError:
            return Response({
                'error': 'QR code library not installed. Please install: pip install qrcode[pil]'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({
                'error': f'Failed to generate QR code: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='by-qr-code')
    def get_by_qr_code(self, request):
        """
        ดึงข้อมูลโต๊ะจาก QR Code data
        ใช้สำหรับลูกค้าที่สแกน QR Code
        """
        qr_code_data = request.query_params.get('qr_code_data')
        if not qr_code_data:
            return Response({
                'error': 'qr_code_data parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            table = RestaurantTable.objects.get(qr_code_data=qr_code_data, is_active=True)
            serializer = self.get_serializer(table)
            
            # ส่งข้อมูลร้านอาหารด้วย
            restaurant_serializer = RestaurantSerializer(table.restaurant, context={'request': request})
            
            return Response({
                'table': serializer.data,
                'restaurant': restaurant_serializer.data
            }, status=status.HTTP_200_OK)
        except RestaurantTable.DoesNotExist:
            return Response({
                'error': 'Invalid or inactive QR code'
            }, status=status.HTTP_404_NOT_FOUND)


class DineInCartViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับจัดการตะกร้า Dine-in
    - ใช้ session_id เพื่อแยกแต่ละการสั่ง (ไม่ต้อง login)
    - ตะกร้าจะผูกกับโต๊ะ (table)
    """
    serializer_class = DineInCartSerializer
    permission_classes = [AllowAny]  # ไม่ต้อง login
    
    def _get_session_id(self, request):
        """
        ดึง session_id สำหรับ dine-in cart
        รองรับ:
        - query param: ?session_id=...
        - header: X-Dine-In-Session-Id / X-Session-Id
        - body: { "session_id": "..." } (สำหรับ POST/PUT)
        - django session key (fallback)
        """
        session_id = request.query_params.get('session_id')
        if session_id:
            return session_id

        session_id = (
            request.headers.get('X-Dine-In-Session-Id')
            or request.headers.get('X-Session-Id')
        )
        if session_id:
            return session_id

        # request.data ใช้ได้เฉพาะบาง method และบาง parser
        try:
            if isinstance(getattr(request, 'data', None), dict):
                session_id = request.data.get('session_id')
                if session_id:
                    return session_id
        except Exception:
            pass

        return getattr(request.session, 'session_key', None)

    def get_queryset(self):
        """ดึงตะกร้าตาม session_id"""
        session_id = self._get_session_id(self.request)
        if session_id:
            return DineInCart.objects.filter(session_id=session_id, is_active=True)
        return DineInCart.objects.none()
    
    @action(detail=False, methods=['post'], url_path='get-or-create')
    def get_or_create_cart(self, request):
        """
        สร้างหรือดึงตะกร้าสำหรับโต๊ะและ session นี้
        Body: {
            "qr_code_data": "DINE-xxx-xxx-xxx",
            "session_id": "optional-session-id"
        }
        """
        qr_code_data = request.data.get('qr_code_data')
        session_id = request.data.get('session_id') or getattr(request.session, 'session_key', None)
        
        if not qr_code_data:
            return Response({
                'error': 'qr_code_data is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not session_id:
            # สร้าง session ใหม่
            request.session.create()
            session_id = request.session.session_key
        
        try:
            # หาโต๊ะจาก QR code
            table = RestaurantTable.objects.get(qr_code_data=qr_code_data, is_active=True)
            
            # หาหรือสร้างตะกร้า
            # ใช้ filter().first() แทน get_or_create() เพื่อป้องกัน MultipleObjectsReturned error
            # ถ้ามีหลาย cart ที่ตรงเงื่อนไข ใช้ตัวล่าสุด (ตาม ordering: -created_at)
            existing_carts = DineInCart.objects.filter(
                table=table,
                session_id=session_id,
                is_active=True
            )
            
            cart = existing_carts.first()
            created = False
            
            if not cart:
                # ไม่มี cart ให้สร้างใหม่
                # ตรวจสอบว่ามี cart ที่ inactive อยู่แล้วหรือไม่ (จาก checkout ครั้งก่อน)
                # ถ้ามีให้ลบ cart ที่ inactive เก่าออกก่อนเพื่อป้องกัน duplicate constraint
                existing_inactive_carts = DineInCart.objects.filter(
                    table=table,
                    session_id=session_id,
                    is_active=False
                )
                
                if existing_inactive_carts.exists():
                    # ลบ cart ที่ inactive เก่าออก (ไม่จำเป็นต้องเก็บไว้)
                    existing_inactive_carts.delete()
                
                # สร้าง cart ใหม่
                cart = DineInCart.objects.create(
                    table=table,
                    session_id=session_id,
                    is_active=True,
                    customer_name=request.data.get('customer_name', '')
                )
                created = True
            elif existing_carts.count() > 1:
                # มี cart หลายตัว (กรณีที่เกิด duplicate) ใช้ตัวล่าสุดและลบตัวเก่า
                carts_to_delete = existing_carts.exclude(cart_id=cart.cart_id)
                carts_to_delete.delete()
            
            serializer = self.get_serializer(cart, context={'request': request})
            return Response({
                'cart': serializer.data,
                'created': created,
                'session_id': session_id
            }, status=status.HTTP_200_OK)
            
        except RestaurantTable.DoesNotExist:
            return Response({
                'error': 'Invalid or inactive QR code'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            error_detail = str(e)
            traceback_str = traceback.format_exc()
            print(f"Error in get_or_create_cart: {error_detail}")
            print(traceback_str)
            return Response({
                'error': f'Failed to create or get cart: {error_detail}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='add-item')
    def add_item(self, request, pk=None):
        """
        เพิ่มสินค้าลงตะกร้า
        Body: {
            "product_id": 123,
            "quantity": 2,
            "special_instructions": "ไม่ใส่ผักชี"
        }
        """
        cart = self.get_object()
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']
        special_instructions = serializer.validated_data.get('special_instructions', '')
        
        try:
            # ใช้ DineInProduct แทน Product
            product = DineInProduct.objects.get(dine_in_product_id=product_id, is_available=True)
            
            # ตรวจสอบว่าสินค้าต้องเป็นของร้านเดียวกับโต๊ะ
            if product.restaurant != cart.table.restaurant:
                return Response({
                    'error': 'Product must be from the same restaurant as the table'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # ตรวจสอบว่ามีสินค้านี้ในตะกร้าแล้วหรือไม่
            cart_item, created = DineInCartItem.objects.get_or_create(
                cart=cart,
                dine_in_product=product,
                defaults={
                    'quantity': quantity,
                    'price_at_add': product.price,
                    'special_instructions': special_instructions
                }
            )
            
            if not created:
                # อัปเดตจำนวน
                cart_item.quantity += quantity
                cart_item.special_instructions = special_instructions
                cart_item.save()
            
            cart_serializer = self.get_serializer(cart)
            return Response({
                'message': 'Item added to cart',
                'cart': cart_serializer.data
            }, status=status.HTTP_200_OK)
            
        except DineInProduct.DoesNotExist:
            return Response({
                'error': 'Product not found or not available'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['put'], url_path='update-item/(?P<item_id>[^/.]+)')
    def update_item(self, request, pk=None, item_id=None):
        """
        อัปเดตรายการในตะกร้า
        Body: {
            "quantity": 3,
            "special_instructions": "ไม่ใส่พริก"
        }
        """
        cart = self.get_object()
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            cart_item = DineInCartItem.objects.get(cart_item_id=item_id, cart=cart)
            cart_item.quantity = serializer.validated_data['quantity']
            if 'special_instructions' in serializer.validated_data:
                cart_item.special_instructions = serializer.validated_data['special_instructions']
            cart_item.save()
            
            cart_serializer = self.get_serializer(cart)
            return Response({
                'message': 'Cart item updated',
                'cart': cart_serializer.data
            }, status=status.HTTP_200_OK)
            
        except DineInCartItem.DoesNotExist:
            return Response({
                'error': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['delete'], url_path='remove-item/(?P<item_id>[^/.]+)')
    def remove_item(self, request, pk=None, item_id=None):
        """ลบรายการออกจากตะกร้า"""
        cart = self.get_object()
        
        try:
            cart_item = DineInCartItem.objects.get(cart_item_id=item_id, cart=cart)
            cart_item.delete()
            
            cart_serializer = self.get_serializer(cart)
            return Response({
                'message': 'Item removed from cart',
                'cart': cart_serializer.data
            }, status=status.HTTP_200_OK)
            
        except DineInCartItem.DoesNotExist:
            return Response({
                'error': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'], url_path='clear')
    def clear_cart(self, request, pk=None):
        """ล้างตะกร้า"""
        cart = self.get_object()
        cart.items.all().delete()
        
        cart_serializer = self.get_serializer(cart)
        return Response({
            'message': 'Cart cleared',
            'cart': cart_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        """
        สร้างออเดอร์จากตะกร้า
        Body: {
            "customer_name": "ลูกค้า",
            "customer_count": 2,
            "special_instructions": "อาหารเผ็ดน้อย",
            "payment_method": "cash"
        }
        """
        cart = self.get_object()
        
        if not cart.items.exists():
            return Response({
                'error': 'Cart is empty'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = CreateDineInOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # สร้างออเดอร์
            total_amount = cart.get_total()

            # ปล่อยให้ Django ตั้งเวลา order_date เองด้วย auto_now_add (เวลา server)
            # หมายเหตุ: เมื่อ USE_TZ=True จะเก็บในฐานข้อมูลเป็น UTC เสมอ
            order = DineInOrder.objects.create(
                table=cart.table,
                restaurant=cart.table.restaurant,
                session_id=cart.session_id,
                total_amount=total_amount,
                customer_name=serializer.validated_data.get('customer_name', cart.customer_name),
                customer_count=serializer.validated_data.get('customer_count', 1),
                special_instructions=serializer.validated_data.get('special_instructions', ''),
                payment_method=serializer.validated_data.get('payment_method', 'cash')
            )
            
            # สร้างรายละเอียดออเดอร์จากตะกร้า
            for cart_item in cart.items.all():
                DineInOrderDetail.objects.create(
                    order=order,
                    dine_in_product=cart_item.dine_in_product,
                    quantity=cart_item.quantity,
                    price_at_order=cart_item.price_at_add,
                    special_instructions=cart_item.special_instructions
                )
            
            # สร้าง log
            DineInStatusLog.objects.create(
                order=order,
                status='pending',
                note='Order created'
            )
            
            # ปิดตะกร้า (inactive cart)
            # ตรวจสอบว่ามี cart ที่ inactive อยู่แล้วหรือไม่ (จาก checkout ครั้งก่อน)
            # ถ้ามีให้ลบ cart ที่ inactive เก่าออกก่อนเพื่อป้องกัน duplicate constraint
            existing_inactive_carts = DineInCart.objects.filter(
                table=cart.table,
                session_id=cart.session_id,
                is_active=False
            ).exclude(cart_id=cart.cart_id)
            
            if existing_inactive_carts.exists():
                # ลบ cart ที่ inactive เก่าออก (ไม่จำเป็นต้องเก็บไว้)
                existing_inactive_carts.delete()
            
            # Inactive cart ปัจจุบัน
            cart.is_active = False
            cart.save()
            
            # ส่ง notification ไปยังร้าน (WebSocket)
            try:
                channel_layer = get_channel_layer()
                restaurant_group = f"restaurant_{order.restaurant.restaurant_id}"
                
                async_to_sync(channel_layer.group_send)(
                    restaurant_group,
                    {
                        'type': 'new_dine_in_order',
                        'order_id': order.dine_in_order_id,
                        'restaurant_id': order.restaurant.restaurant_id,
                        'table_number': order.table.table_number,
                        'total_amount': float(order.total_amount),
                        'customer_count': order.customer_count,
                        'timestamp': timezone.now().isoformat()
                    }
                )
                logger.info(f"📢 New dine-in order notification sent for restaurant: {order.restaurant.restaurant_id}, table: {order.table.table_number}")
            except Exception as e:
                logger.error(f"❌ Failed to send WebSocket notification: {e}")
            
            order_serializer = DineInOrderSerializer(order, context={'request': request})
            return Response({
                'message': 'Order created successfully',
                'order': order_serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'error': f'Failed to create order: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DineInOrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับจัดการออเดอร์ Dine-in
    - ร้านอาหารเห็นออเดอร์ของตัวเอง
    - ลูกค้าสามารถดูออเดอร์ของตัวเองผ่าน session_id
    """
    serializer_class = DineInOrderSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['current_status', 'payment_status', 'table']
    ordering_fields = ['order_date', 'total_amount']
    ordering = ['-order_date']
    
    def get_permissions(self):
        """ร้านอาหารต้อง login, ลูกค้าไม่ต้อง login"""
        # ลูกค้า (ไม่ต้อง login) อ่านได้เฉพาะกรณีส่ง session_id และจะถูก filter ใน get_queryset()
        # ร้านอาหารต้อง login สำหรับการแก้ไขสถานะ/ชำระเงิน และการแก้ไขข้อมูลออเดอร์ใดๆ
        if self.action in ['update_status', 'update_payment_status', 'update', 'partial_update', 'destroy', 'create']:
            return [IsAuthenticated()]
        return [AllowAny()]
    
    def get_queryset(self):
        """
        ร้านอาหารเห็นออเดอร์ของตัวเอง
        ลูกค้าเห็นออเดอร์ของตัวเอง (ผ่าน session_id)
        """
        user = self.request.user
        
        # สำหรับร้านอาหารและ admin
        if user.is_authenticated:
            if user.role == 'admin':
                return DineInOrder.objects.all()
            elif user.role in ['special_restaurant', 'general_restaurant']:
                if hasattr(user, 'restaurant'):
                    return DineInOrder.objects.filter(restaurant=user.restaurant)
        
        # สำหรับลูกค้า (ใช้ session_id)
        session_id = self.request.query_params.get('session_id')
        if session_id:
            return DineInOrder.objects.filter(session_id=session_id)
        
        return DineInOrder.objects.none()
    
    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        """
        อัปเดตสถานะออเดอร์ (เฉพาะร้านอาหาร)
        Body: {
            "status": "served",
            "note": "Served"
        }
        """
        order = self.get_object()
        serializer = UpdateDineInOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data['status']
        note = serializer.validated_data.get('note', '')
        
        old_status = order.current_status

        # อัปเดตสถานะ
        order.current_status = new_status
        
        # ถ้า status เป็น served (สถานะสุดท้าย) ให้บันทึกเวลา
        if new_status == 'served':
            order.completed_at = timezone.now()
        
        order.save()
        
        # สร้าง log
        DineInStatusLog.objects.create(
            order=order,
            status=new_status,
            note=note,
            updated_by_user=request.user
        )
        
        # ส่ง notification ไปยังลูกค้า (WebSocket)
        try:
            channel_layer = get_channel_layer()

            # broadcast ไปที่ session group (ลูกค้าดู history/list จะ subscribe ด้วย session_id)
            session_group = f"dine_in_session_{order.session_id}"
            
            async_to_sync(channel_layer.group_send)(
                session_group,
                {
                    'type': 'dine_in_order_status_update',
                    'order_id': order.dine_in_order_id,
                    'old_status': old_status,
                    'new_status': new_status,
                    'note': note,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            print(f"Failed to send WebSocket notification: {e}")
        
        order_serializer = self.get_serializer(order)
        return Response({
            'message': 'Order status updated',
            'order': order_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='update-payment-status')
    def update_payment_status(self, request, pk=None):
        """
        อัปเดตสถานะการชำระเงิน (เฉพาะร้านอาหาร)
        Body: {
            "payment_status": "paid",
            "payment_method": "cash"
        }
        """
        order = self.get_object()
        payment_status = request.data.get('payment_status')
        payment_method = request.data.get('payment_method')
        
        if payment_status not in dict(DineInOrder.PAYMENT_STATUS_CHOICES).keys():
            return Response({
                'error': 'Invalid payment status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        order.payment_status = payment_status
        if payment_method:
            order.payment_method = payment_method
        
        if payment_status == 'paid':
            order.paid_at = timezone.now()
        
        order.save()
        
        order_serializer = self.get_serializer(order)
        return Response({
            'message': 'Payment status updated',
            'order': order_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='by-table/(?P<table_id>[^/.]+)')
    def get_by_table(self, request, table_id=None):
        """ดึงออเดอร์ทั้งหมดของโต๊ะนี้"""
        orders = self.get_queryset().filter(table_id=table_id)
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='cancel-item')
    def cancel_item(self, request):
        """
        ลูกค้ายกเลิกรายการเมนูรายชิ้นได้ก่อนร้านกดยืนยันออเดอร์
        Body: {
            "session_id": "session-id",
            "order_id": 123,
            "order_detail_id": 456
        }
        """
        session_id = request.data.get('session_id')
        order_id = request.data.get('order_id')
        order_detail_id = request.data.get('order_detail_id')

        if not session_id or not order_id or not order_detail_id:
            return Response({
                'error': 'session_id, order_id and order_detail_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        order = DineInOrder.objects.filter(
            dine_in_order_id=order_id,
            session_id=session_id,
            payment_status='unpaid'
        ).first()

        if not order:
            return Response({
                'error': 'Order not found for this session'
            }, status=status.HTTP_404_NOT_FOUND)

        if order.current_status != 'pending':
            return Response({
                'error': 'Cannot cancel item after restaurant confirmed the order',
                'message': 'ยกเลิกเมนูไม่ได้แล้ว เนื่องจากร้านยืนยันออเดอร์แล้ว'
            }, status=status.HTTP_400_BAD_REQUEST)

        order_detail = DineInOrderDetail.objects.filter(
            order=order,
            order_detail_id=order_detail_id
        ).first()

        if not order_detail:
            return Response({
                'error': 'Order item not found'
            }, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            removed_order_detail_id = order_detail.order_detail_id
            order_detail.delete()

            remaining_details = DineInOrderDetail.objects.filter(order=order)
            if remaining_details.exists():
                new_total = remaining_details.aggregate(total=Sum('subtotal'))['total'] or 0
                order.total_amount = new_total
                order.save(update_fields=['total_amount'])
                order_cancelled = False
            else:
                order.current_status = 'cancelled'
                order.total_amount = 0
                order.bill_requested = False
                order.bill_requested_at = None
                order.completed_at = timezone.now()
                order.save(update_fields=[
                    'current_status', 'total_amount',
                    'bill_requested', 'bill_requested_at', 'completed_at'
                ])
                order_cancelled = True

        serializer = self.get_serializer(order)

        # แจ้งฝั่งร้านแบบ real-time ให้รีเฟรชรายการ
        try:
            channel_layer = get_channel_layer()
            restaurant_group = f"restaurant_{order.restaurant.restaurant_id}"
            async_to_sync(channel_layer.group_send)(
                restaurant_group,
                {
                    'type': 'dine_in_item_cancelled',
                    'restaurant_id': order.restaurant.restaurant_id,
                    'table_number': order.table.table_number if order.table else None,
                    'order_id': order.dine_in_order_id,
                    'order_detail_id': removed_order_detail_id,
                    'order_cancelled': order_cancelled,
                    'timestamp': timezone.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"❌ Error sending dine_in_item_cancelled notification: {str(e)}")

        return Response({
            'message': 'Item cancelled successfully',
            'order': serializer.data,
            'removed_order_detail_id': removed_order_detail_id,
            'order_cancelled': order_cancelled
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='request-bill')
    def request_bill(self, request):
        """
        ลูกค้าร้องขอเช็กบิล (สำหรับโต๊ะ/ session นั้น)
        Body: {
            "session_id": "session-id"
        }
        """
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({
                'error': 'session_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # หาออเดอร์ของ session นี้เพื่ออ้างอิงโต๊ะ
        session_orders = DineInOrder.objects.filter(
            session_id=session_id,
            payment_status='unpaid',
            current_status__in=['pending', 'confirmed', 'served']
        ).select_related('table')
        
        if not session_orders.exists():
            return Response({
                'error': 'No unpaid orders found for this session'
            }, status=status.HTTP_404_NOT_FOUND)

        table = session_orders.first().table
        if not table:
            return Response({
                'error': 'Table not found for this session'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ต้องเช็กทั้งโต๊ะ: ถ้ายังมีออเดอร์ที่ยังไม่ชำระ/ไม่ยกเลิก และมีรายการที่ยังไม่เสิร์ฟ -> ห้ามเช็กบิล
        table_orders = DineInOrder.objects.filter(
            table=table,
            payment_status='unpaid',
            current_status__in=['pending', 'confirmed', 'served']
        )

        has_unserved_items = DineInOrderDetail.objects.filter(
            order__in=table_orders,
            is_served=False
        ).exists()

        # กรณี fallback: order ที่ไม่มี order_details ให้ยึด current_status แทน
        has_orders_without_details_not_served = table_orders.filter(
            order_details__isnull=True
        ).exclude(
            current_status='served'
        ).exists()

        if has_unserved_items or has_orders_without_details_not_served:
            return Response({
                'error': 'Cannot request bill: some items in this table are not served yet',
                'message': 'ยังไม่สามารถเช็กบิลได้ เนื่องจากในโต๊ะยังมีรายการที่ยังไม่เสิร์ฟ'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # อัปเดตสถานะการร้องขอเช็กบิล
        now = timezone.now()
        updated_count = table_orders.update(
            bill_requested=True,
            bill_requested_at=now
        )
        
        return Response({
            'message': f'Bill request sent for {updated_count} order(s)',
            'orders_count': updated_count,
            'session_id': session_id,
            'table_number': table.table_number
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='can-request-bill')
    def can_request_bill(self, request):
        """
        ตรวจสอบว่าตอนนี้สามารถร้องขอเช็กบิลได้หรือไม่ (เช็กทั้งโต๊ะ)
        Query params:
            - session_id
        """
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({
                'can_request_bill': False,
                'error': 'session_id is required',
                'message': 'ไม่พบ Session ID'
            }, status=status.HTTP_400_BAD_REQUEST)

        session_orders = DineInOrder.objects.filter(
            session_id=session_id,
            payment_status='unpaid',
            current_status__in=['pending', 'confirmed', 'served']
        ).select_related('table')

        if not session_orders.exists():
            return Response({
                'can_request_bill': False,
                'error': 'No unpaid orders found for this session',
                'message': 'ไม่พบออเดอร์ค้างชำระในเซสชันนี้'
            }, status=status.HTTP_404_NOT_FOUND)

        table = session_orders.first().table
        if not table:
            return Response({
                'can_request_bill': False,
                'error': 'Table not found for this session',
                'message': 'ไม่พบข้อมูลโต๊ะ'
            }, status=status.HTTP_400_BAD_REQUEST)

        table_orders = DineInOrder.objects.filter(
            table=table,
            payment_status='unpaid',
            current_status__in=['pending', 'confirmed', 'served']
        )

        has_unserved_items = DineInOrderDetail.objects.filter(
            order__in=table_orders,
            is_served=False
        ).exists()

        has_orders_without_details_not_served = table_orders.filter(
            order_details__isnull=True
        ).exclude(
            current_status='served'
        ).exists()

        can_request = not (has_unserved_items or has_orders_without_details_not_served)
        return Response({
            'can_request_bill': can_request,
            'table_number': table.table_number,
            'message': (
                'สามารถเช็กบิลได้'
                if can_request
                else 'ยังไม่สามารถเช็กบิลได้ เนื่องจากในโต๊ะยังมีรายการที่ยังไม่เสิร์ฟ'
            )
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='dismiss-bill-request')
    def dismiss_bill_request(self, request, pk=None):
        """
        ร้านอาหารล้างสถานะการร้องขอเช็กบิล (เฉพาะปิดคำขอ ไม่ชำระเงิน)
        ใช้เมื่อกดผิด หรือลูกค้ายังไม่พร้อมจ่าย
        """
        order = self.get_object()
        session_id = order.session_id
        
        # อัปเดตทุก order ใน session - เฉพาะล้าง bill_requested
        updated_orders = DineInOrder.objects.filter(
            session_id=session_id,
            bill_requested=True
        )
        
        updated_count = updated_orders.update(
            bill_requested=False,
            bill_requested_at=None
        )
        
        logger.info(f"🔕 Dismissed bill request for {updated_count} orders in session: {session_id}")
        
        order_serializer = self.get_serializer(order)
        return Response({
            'message': 'Bill request dismissed',
            'order': order_serializer.data,
            'orders_updated': updated_count
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='complete-bill')
    def complete_bill(self, request, pk=None):
        """
        ร้านอาหารเช็กบิลเสร็จแล้ว (ลูกค้าชำระเงินเรียบร้อย)
        - Mark orders ทั้งหมดในโต๊ะเดียวกันเป็น paid (ไม่ใช่แค่ session เดียว)
        - ล้าง bill_requested
        - ส่ง WebSocket แจ้งลูกค้า (ให้ history หาย)
        """
        order = self.get_object()
        table = order.table
        table_number = table.table_number if table else None
        
        # อัปเดตทุก order ในโต๊ะเดียวกันที่ยังไม่ชำระเงิน (ไม่ใช่แค่ session เดียว)
        updated_orders = DineInOrder.objects.filter(
            table=table,
            payment_status='unpaid',
            current_status__in=['pending', 'confirmed', 'served']
        )
        
        # เก็บ session_ids ทั้งหมดที่เกี่ยวข้องเพื่อส่ง WebSocket notification
        affected_session_ids = set()
        
        updated_count = 0
        for order_item in updated_orders:
            order_item.bill_requested = False
            order_item.bill_requested_at = None
            order_item.payment_status = 'paid'
            # อัปเดต status เป็น served ถ้ายังไม่ใช่ (served เป็นสถานะสุดท้าย)
            if order_item.current_status not in ['served', 'cancelled']:
                order_item.current_status = 'served'
            order_item.save()
            affected_session_ids.add(order_item.session_id)
            updated_count += 1
        
        logger.info(f"✅ Bill completed: Marked {updated_count} orders as paid for table {table_number} (sessions: {len(affected_session_ids)})")
        
        # ส่ง WebSocket notification ไปยังลูกค้าทุก session ที่เกี่ยวข้อง
        try:
            channel_layer = get_channel_layer()
            for session_id in affected_session_ids:
                group_name = f"dine_in_session_{session_id}"
                try:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'bill_check_completed',
                            'session_id': session_id,
                            'order_id': order.dine_in_order_id,
                            'table_number': table_number,
                            'message': 'ร้านเช็กบิลเสร็จแล้ว',
                            'orders_count': updated_count,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                    logger.info(f"📢 Bill check completed notification sent for session: {session_id}")
                except Exception as e:
                    logger.error(f"❌ Error sending notification to session {session_id}: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Error sending bill check completed notification: {str(e)}")
        
        order_serializer = self.get_serializer(order)
        return Response({
            'message': 'Bill completed and paid',
            'order': order_serializer.data,
            'orders_updated': updated_count,
            'table_number': table_number,
            'sessions_affected': len(affected_session_ids)
        }, status=status.HTTP_200_OK)


class DineInOrderDetailViewSet(viewsets.ModelViewSet):
    """
    ViewSet สำหรับจัดการรายละเอียดออเดอร์ Dine-in
    ใช้สำหรับ mark ว่าเมนูไหนเสิร์ฟแล้ว
    """
    queryset = DineInOrderDetail.objects.all()
    serializer_class = DineInOrderDetailSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        ร้านอาหารเห็น order details ของออเดอร์ของตัวเองเท่านั้น
        """
        user = self.request.user
        
        if user.role == 'admin':
            return DineInOrderDetail.objects.all()
        elif user.role in ['special_restaurant', 'general_restaurant']:
            if hasattr(user, 'restaurant'):
                return DineInOrderDetail.objects.filter(order__restaurant=user.restaurant)
        
        return DineInOrderDetail.objects.none()
    
    @action(detail=True, methods=['post'], url_path='mark-served')
    def mark_served(self, request, pk=None):
        """
        Mark order detail item ว่าเสิร์ฟแล้ว
        Body: {} (empty body ก็ได้)
        """
        order_detail = self.get_object()
        
        # ตรวจสอบว่า user มีสิทธิ์เข้าถึง order นี้
        user = request.user
        if user.role in ['special_restaurant', 'general_restaurant']:
            if hasattr(user, 'restaurant'):
                if order_detail.order.restaurant != user.restaurant:
                    return Response({
                        'error': 'You do not have permission to modify this order detail'
                    }, status=status.HTTP_403_FORBIDDEN)
        
        # อัพเดตสถานะ
        order_detail.is_served = True
        order_detail.served_at = timezone.now()
        order_detail.served_by = user
        order_detail.save()
        
        # ส่ง WebSocket notification ไปยังลูกค้า
        try:
            channel_layer = get_channel_layer()
            session_group = f"dine_in_session_{order_detail.order.session_id}"
            
            async_to_sync(channel_layer.group_send)(
                session_group,
                {
                    'type': 'order_detail_served',
                    'order_id': order_detail.order.dine_in_order_id,
                    'order_detail_id': order_detail.order_detail_id,
                    'product_name': order_detail.dine_in_product.product_name,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")
        
        serializer = self.get_serializer(order_detail)
        return Response({
            'message': 'Order detail marked as served',
            'order_detail': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='mark-unserved')
    def mark_unserved(self, request, pk=None):
        """
        Mark order detail item ว่ายังไม่เสิร์ฟ (ยกเลิกการ mark served)
        Body: {} (empty body ก็ได้)
        """
        order_detail = self.get_object()
        
        # ตรวจสอบว่า user มีสิทธิ์เข้าถึง order นี้
        user = request.user
        if user.role in ['special_restaurant', 'general_restaurant']:
            if hasattr(user, 'restaurant'):
                if order_detail.order.restaurant != user.restaurant:
                    return Response({
                        'error': 'You do not have permission to modify this order detail'
                    }, status=status.HTTP_403_FORBIDDEN)
        
        # อัพเดตสถานะ
        order_detail.is_served = False
        order_detail.served_at = None
        order_detail.served_by = None
        order_detail.save()
        
        serializer = self.get_serializer(order_detail)
        return Response({
            'message': 'Order detail marked as unserved',
            'order_detail': serializer.data
        }, status=status.HTTP_200_OK)


# ===== Entertainment Venues ViewSets =====

class VenueCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing venue categories
    """
    queryset = VenueCategory.objects.all()
    serializer_class = VenueCategorySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['category_name', 'description']
    ordering_fields = ['sort_order', 'category_name', 'created_at']
    ordering = ['sort_order', 'category_name']
    filterset_fields = ['is_active']
    
    def get_permissions(self):
        """Allow anyone to view, require authentication for create/update/delete"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_context(self):
        """Send context to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=True, methods=['post'])
    def delete_icon(self, request, pk=None):
        category = self.get_object()
        if category.icon:
            category.icon.delete(save=False)
            category.icon = None
        category.icon_url = ''
        category.save()
        serializer = self.get_serializer(category)
        return Response(serializer.data)


class CountryViewSet(viewsets.ModelViewSet):
    """ตารางอ้างอิงประเทศ — แก้ไขได้เฉพาะแอดมิน"""
    queryset = Country.objects.all().order_by('sort_order', 'name')
    serializer_class = CountrySerializer
    pagination_class = None
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_active']
    ordering_fields = ['sort_order', 'name', 'country_id']
    ordering = ['sort_order', 'name']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list' and (
            not self.request.user.is_authenticated
            or getattr(self.request.user, 'role', None) != 'admin'
        ):
            qs = qs.filter(is_active=True)
        return qs

    def _require_admin(self):
        if not self.request.user.is_authenticated or getattr(self.request.user, 'role', None) != 'admin':
            raise PermissionDenied('Admin only.')

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_flag(self, request, pk=None):
        """อัปโหลดรูปธงชาติ (เฉพาะแอดมิน) — ส่ง multipart ฟิลด์ชื่อ flag"""
        country = self.get_object()
        self._require_admin()
        if 'flag' not in request.FILES:
            return Response(
                {'error': 'Please select an image file'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image_file = request.FILES['flag']
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if image_file.content_type not in allowed_types:
            return Response(
                {'error': 'Only JPG, PNG, GIF and WebP files are supported'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if image_file.size > 2 * 1024 * 1024:
            return Response(
                {'error': 'File size must not exceed 2MB'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        country.flag = image_file
        country.save()
        serializer = CountrySerializer(country, context={'request': request})
        return Response(serializer.data)


class CityViewSet(viewsets.ModelViewSet):
    """ตารางอ้างอิงเมือง — แก้ไขได้เฉพาะแอดมิน"""
    queryset = City.objects.select_related('country').all().order_by('country', 'name')
    serializer_class = CitySerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['country']
    ordering_fields = ['name', 'city_id']
    ordering = ['country', 'name']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def _require_admin(self):
        if not self.request.user.is_authenticated or getattr(self.request.user, 'role', None) != 'admin':
            raise PermissionDenied('Admin only.')

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list' and (
            not self.request.user.is_authenticated
            or getattr(self.request.user, 'role', None) != 'admin'
        ):
            qs = qs.filter(country__is_active=True)
        return qs


class EntertainmentVenueViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing entertainment venues
    """
    queryset = EntertainmentVenue.objects.select_related('category', 'country', 'city').prefetch_related('images')
    serializer_class = EntertainmentVenueSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['venue_name', 'description', 'address', 'category__category_name', 'country__name', 'city__name']
    ordering_fields = ['average_rating', 'created_at', 'venue_name']
    ordering = ['-average_rating']
    filterset_fields = ['status', 'category', 'country', 'city']
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    def get_permissions(self):
        """Allow anyone to view, require authentication for create/update/delete"""
        if self.action in ['list', 'retrieve', 'images', 'map', 'nearby']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        """Use lightweight serializer for list view"""
        if self.action == 'list':
            return EntertainmentVenueListSerializer
        return EntertainmentVenueSerializer
    
    def get_serializer_context(self):
        """Send context to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def images(self, request, pk=None):
        """Get all images for a venue"""
        venue = self.get_object()
        images = venue.images.all().order_by('sort_order', 'created_at')
        serializer = VenueImageSerializer(images, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def map(self, request, pk=None):
        """Get venue location for map display"""
        venue = self.get_object()
        return Response({
            'venue_id': venue.venue_id,
            'venue_name': venue.venue_name,
            'address': venue.address,
            'latitude': str(venue.latitude) if venue.latitude else None,
            'longitude': str(venue.longitude) if venue.longitude else None,
        })
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def nearby(self, request):
        """
        Get venues near a location
        Query params: latitude, longitude, radius (in km, default 10)
        """
        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        radius = float(request.query_params.get('radius', 10))  # Default 10km
        
        if not latitude or not longitude:
            return Response({'error': 'latitude and longitude are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            lat = float(latitude)
            lng = float(longitude)
        except ValueError:
            return Response({'error': 'Invalid latitude or longitude'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Simple distance calculation (Haversine formula would be better for production)
        # For now, just return all open venues
        queryset = EntertainmentVenue.objects.filter(status='open')
        
        # TODO: Implement proper distance calculation using geopy or PostGIS
        # For now, filter by approximate bounding box
        # Rough approximation: 1 degree ≈ 111 km
        lat_range = radius / 111.0
        lng_range = radius / (111.0 * abs(math.cos(math.radians(lat))))
        
        queryset = queryset.filter(
            latitude__gte=lat - lat_range,
            latitude__lte=lat + lat_range,
            longitude__gte=lng - lng_range,
            longitude__lte=lng + lng_range
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_image(self, request, pk=None):
        """Upload an image for a venue"""
        venue = self.get_object()
        
        # Check permissions (admin only for now)
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can upload venue images'}, status=status.HTTP_403_FORBIDDEN)
        
        if 'image' not in request.FILES:
            return Response({'error': 'Please select an image file'}, status=status.HTTP_400_BAD_REQUEST)
        
        image_file = request.FILES['image']
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
        if image_file.content_type not in allowed_types:
            return Response({'error': 'Only JPG, PNG and GIF files are supported'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check file size (limit to 10MB)
        if image_file.size > 10 * 1024 * 1024:
            return Response({'error': 'File size must not exceed 10MB'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get sort_order and caption from request
        sort_order = int(request.data.get('sort_order', venue.images.count() + 1))
        caption = request.data.get('caption', '')
        is_primary = request.data.get('is_primary', 'false').lower() == 'true'
        
        # If this is set as primary, unset other primary images
        if is_primary:
            venue.images.filter(is_primary=True).update(is_primary=False)
        
        # Create VenueImage
        venue_image = VenueImage.objects.create(
            venue=venue,
            image=image_file,
            caption=caption,
            sort_order=sort_order,
            is_primary=is_primary
        )
        
        serializer = VenueImageSerializer(venue_image, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['patch', 'put'], url_path='images/(?P<image_id>[^/.]+)', permission_classes=[IsAuthenticated])
    def update_image(self, request, pk=None, image_id=None):
        """Update a venue image (caption, sort_order, is_primary)"""
        venue = self.get_object()
        
        # Check permissions (admin only for now)
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can update venue images'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            venue_image = venue.images.get(image_id=image_id)
            
            # Update fields
            if 'caption' in request.data:
                venue_image.caption = request.data['caption']
            if 'sort_order' in request.data:
                venue_image.sort_order = int(request.data['sort_order'])
            if 'is_primary' in request.data:
                is_primary = request.data['is_primary']
                if is_primary:
                    # Unset other primary images
                    venue.images.filter(is_primary=True).exclude(image_id=image_id).update(is_primary=False)
                venue_image.is_primary = is_primary
            
            venue_image.save()
            serializer = VenueImageSerializer(venue_image, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except VenueImage.DoesNotExist:
            return Response({'error': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['delete'], url_path='images/(?P<image_id>[^/.]+)', permission_classes=[IsAuthenticated])
    def delete_image(self, request, pk=None, image_id=None):
        """Delete a venue image"""
        venue = self.get_object()
        
        # Check permissions (admin only for now)
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can delete venue images'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            venue_image = venue.images.get(image_id=image_id)
            venue_image.delete()
            return Response({'message': 'Image deleted successfully'}, status=status.HTTP_200_OK)
        except VenueImage.DoesNotExist:
            return Response({'error': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'], url_path='bulk_create', permission_classes=[IsAuthenticated])
    def bulk_create(self, request):
        """
        Bulk-create entertainment venues from Excel import.
        Expected body: { "venues": [ { venue_name, country_name, city_name,
                                        address, latitude, longitude, phone_number,
                                        opening_hours, description, status, category_name }, ... ] }
        Returns: { success, failed, errors, new_countries, new_cities }
        """
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can bulk-import venues'}, status=status.HTTP_403_FORBIDDEN)

        venues_data = request.data.get('venues', [])
        if not isinstance(venues_data, list) or len(venues_data) == 0:
            return Response({'error': 'venues list is required'}, status=status.HTTP_400_BAD_REQUEST)

        success_count = 0
        failed_count = 0
        duplicate_count = 0
        errors = []
        duplicates = []
        new_countries = []
        new_cities = []

        existing_names = {
            name.lower()
            for name in EntertainmentVenue.objects.values_list('venue_name', flat=True)
        }

        for idx, row in enumerate(venues_data):
            row_num = idx + 2  # ตรงกับหมายเลขแถวใน Excel (header = 1)
            venue_name = (row.get('venue_name') or '').strip()
            if not venue_name:
                errors.append({'row': row_num, 'venue_name': '—', 'message': 'venue_name ว่างเปล่า'})
                failed_count += 1
                continue

            if venue_name.lower() in existing_names:
                duplicates.append({'row': row_num, 'venue_name': venue_name})
                duplicate_count += 1
                continue

            try:
                # ─── Country / City (get_or_create, normalize title-case) ───────────
                country_obj = None
                city_obj = None
                country_raw = (row.get('country_name') or '').strip().title()
                city_raw = (row.get('city_name') or '').strip().title()

                if country_raw:
                    country_obj, created_c = Country.objects.get_or_create(name=country_raw)
                    if created_c:
                        new_countries.append(country_raw)
                    if city_raw:
                        city_obj, created_ct = City.objects.get_or_create(
                            name=city_raw, country=country_obj
                        )
                        if created_ct:
                            new_cities.append(f'{city_raw} ({country_raw})')

                # ─── Category ────────────────────────────────────────────────────────
                category_obj = None
                cat_name = (row.get('category_name') or '').strip()
                if cat_name:
                    category_obj, _ = VenueCategory.objects.get_or_create(category_name=cat_name)

                # ─── Lat / Lng ────────────────────────────────────────────────────────
                def to_decimal_or_none(val):
                    try:
                        return float(str(val).replace(',', '.')) if str(val).strip() else None
                    except (ValueError, TypeError):
                        return None

                lat = to_decimal_or_none(row.get('latitude'))
                lng = to_decimal_or_none(row.get('longitude'))

                # ─── Status ───────────────────────────────────────────────────────────
                raw_status = (row.get('status') or 'open').strip().lower()
                status_val = raw_status if raw_status in ('open', 'closed') else 'open'

                # ─── Create ───────────────────────────────────────────────────────────
                EntertainmentVenue.objects.create(
                    venue_name=venue_name,
                    country=country_obj,
                    city=city_obj,
                    address=(row.get('address') or '').strip(),
                    latitude=lat,
                    longitude=lng,
                    phone_number=(row.get('phone_number') or '').strip() or None,
                    opening_hours=(row.get('opening_hours') or '').strip() or None,
                    description=(row.get('description') or '').strip() or None,
                    status=status_val,
                    category=category_obj,
                )
                existing_names.add(venue_name.lower())
                success_count += 1

            except Exception as exc:
                failed_count += 1
                errors.append({
                    'row': row_num,
                    'venue_name': venue_name,
                    'message': str(exc),
                })

        return Response({
            'success': success_count,
            'failed': failed_count,
            'duplicates': duplicate_count,
            'duplicate_list': duplicates,
            'errors': errors,
            'new_countries': list(dict.fromkeys(new_countries)),
            'new_cities': list(dict.fromkeys(new_cities)),
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='images/batch-update', permission_classes=[IsAuthenticated])
    def batch_update_images(self, request, pk=None):
        """Batch update images (caption, sort_order)"""
        venue = self.get_object()
        
        # Check permissions (admin only for now)
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can update venue images'}, status=status.HTTP_403_FORBIDDEN)
        
        images_data = request.data.get('images', [])
        updated_images = []
        
        for img_data in images_data:
            try:
                image_id = img_data.get('image_id')
                venue_image = venue.images.get(image_id=image_id)
                
                if 'caption' in img_data:
                    venue_image.caption = img_data['caption']
                if 'sort_order' in img_data:
                    venue_image.sort_order = int(img_data['sort_order'])
                if 'is_primary' in img_data:
                    is_primary = img_data['is_primary']
                    if is_primary:
                        venue.images.filter(is_primary=True).exclude(image_id=image_id).update(is_primary=False)
                    venue_image.is_primary = is_primary
                
                venue_image.save()
                serializer = VenueImageSerializer(venue_image, context={'request': request})
                updated_images.append(serializer.data)
            except VenueImage.DoesNotExist:
                continue
        
        return Response({'images': updated_images}, status=status.HTTP_200_OK)


class VenueReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing venue reviews
    """
    queryset = VenueReview.objects.select_related('venue', 'user').all()
    serializer_class = VenueReviewSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['comment', 'venue__venue_name', 'user__username']
    ordering_fields = ['review_date', 'rating', 'updated_at']
    ordering = ['-review_date']
    filterset_fields = ['venue', 'user', 'rating']
    
    def get_permissions(self):
        """Allow anyone to view, require authentication for create/update/delete"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter reviews by venue if venue_id is provided"""
        queryset = super().get_queryset()
        venue_id = self.request.query_params.get('venue_id')
        if venue_id:
            queryset = queryset.filter(venue_id=venue_id)
        return queryset
    
    def perform_create(self, serializer):
        """Set the user to the current user and check for existing review"""
        venue = serializer.validated_data['venue']
        user = self.request.user
        
        # Check if user has already reviewed this venue
        existing_review = VenueReview.objects.filter(venue=venue, user=user).first()
        if existing_review:
            raise ValidationError({'error': 'You have already reviewed this venue. You can update your existing review instead.'})
        
        serializer.save(user=user)
    
    def perform_update(self, serializer):
        """Only allow user to update their own review"""
        review = self.get_object()
        if review.user != self.request.user:
            raise ValidationError({'error': 'You can only update your own review.'})
        serializer.save()
    
    def perform_destroy(self, instance):
        """Only allow user to delete their own review"""
        if instance.user != self.request.user:
            raise ValidationError({'error': 'You can only delete your own review.'})
        instance.delete()
