from django.urls import path, include
from rest_framework import routers

from . import views


router = routers.DefaultRouter()

router.register(r"wallets", views.WalletViewSet)

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    # path("test-nillion/", views.test_nillion, name="test-nillion"),
    path("", include(router.urls)),
]
