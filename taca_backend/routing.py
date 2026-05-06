from django.urls import path
from api.consumers import OrderConsumer, GuestOrderConsumer, DineInOrderConsumer

websocket_urlpatterns = [
    path('ws/orders/', OrderConsumer.as_asgi()),
    path('ws/guest-orders/', GuestOrderConsumer.as_asgi()),
    path('ws/dine-in-orders/', DineInOrderConsumer.as_asgi()),
] 