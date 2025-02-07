from rest_framework import viewsets, permissions, serializers, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.db.models import Q

from core.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    address = serializers.CharField(max_length=50, required=True)
    target_portfolio = serializers.JSONField(source="portfolio", required=False)
    farcaster_handle = serializers.CharField(
        max_length=50, required=False, allow_null=True
    )
    twitter_handle = serializers.CharField(
        max_length=50, required=False, allow_null=True
    )
    chain_id = serializers.IntegerField(required=False)
    latest_trade_summary = serializers.JSONField(required=False)

    class Meta:
        model = Wallet
        fields = [
            "id",
            "address",
            "farcaster_handle",
            "twitter_handle",
            "target_portfolio",
            "chain_id",
            "latest_trade_summary",
        ]

    def validate(self, data):
        """
        Check if at least one handle (farcaster or twitter) is provided
        """
        if not data.get("farcaster_handle") and not data.get("twitter_handle"):
            raise serializers.ValidationError(
                "At least one of 'farcaster_handle' or 'twitter_handle' must be provided"
            )
        return data

    def validate_portfolio(self, value):
        required_keys = ["majors", "stables", "alts", "memes"]

        # Check if all required keys are present
        if not all(key in value for key in required_keys):
            raise serializers.ValidationError(
                f"Portfolio must contain all keys: {', '.join(required_keys)}"
            )

        # Check if all values are non-negative numbers
        for key, val in value.items():
            if not isinstance(val, (int, float)) or val < 0:
                raise serializers.ValidationError(
                    f"The value for {key} must be a non-negative number"
                )

        # Check if sum equals 100
        total = sum(float(v) for v in value.values())
        if abs(total - 100) > 0.01:
            raise serializers.ValidationError(
                "Portfolio values must sum exactly to 100%"
            )

        return value


# class WalletViewSet(viewsets.ModelViewSet):
class WalletViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    A viewset that provides default `create()`, `update()`, `partial_update()`,
    and `destroy()` actions, but no `list()` or `retrieve()`
    """

    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="address/(?P<address>[^/.]+)")
    def get_by_address(self, request, address=None):
        wallet = get_object_or_404(Wallet, address=address)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="handle/(?P<handle>[^/.]+)")
    def get_by_handle(self, request, handle=None):
        """
        Busca carteira por Farcaster handle ou Twitter handle
        """
        wallet = Wallet.objects.filter(
            Q(farcaster_handle=handle) | Q(twitter_handle=handle)
        ).first()

        if not wallet:
            return Response(
                {"detail": _("Wallet não encontrada para este handle")}, status=404
            )

        serializer = self.get_serializer(wallet)
        return Response(serializer.data)
