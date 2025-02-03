from rest_framework import viewsets, permissions, serializers
from django.utils.translation import gettext as _

from core.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    address = serializers.CharField(max_length=50, required=True)

    class Meta:
        model = Wallet
        fields = ["id", "address"]


class WalletViewSet(viewsets.ModelViewSet):
    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    #http_method_names = ["post", "put", "patch", "delete", "head", "options"]