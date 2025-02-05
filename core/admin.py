from django.contrib import admin
from core.models import Wallet, Token, WalletToken


class WalletTokenInline(admin.TabularInline):
    model = WalletToken
    extra = 1
    fields = ("token", "balance", "balance_usd", "last_updated")
    readonly_fields = ("last_updated",)
    autocomplete_fields = ("token",)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("address", "twitter_handle", "farcaster_handle", "get_token_count")
    search_fields = ("address",)
    inlines = [WalletTokenInline]

    def get_token_count(self, obj):
        return obj.tokens.count()

    get_token_count.short_description = "Tokens"


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "chain_id", "address", "category")
    list_filter = ("chain_id", "category")
    search_fields = ("symbol", "name", "address")
    readonly_fields = ("created_at", "updated_at")
