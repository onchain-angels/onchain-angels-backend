from django.db import models
from django.db.models import JSONField


class Token(models.Model):

    CATEGORY_CHOICES = [
        ("MAJORS", "Major currencies"),
        ("STABLES", "Stablecoins"),
        ("ALTS", "Altcoins"),
        ("MEMES", "Memecoins"),
    ]

    address = models.CharField(max_length=255, unique=True)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, blank=True, null=True
    )

    coingecko_id = models.CharField(max_length=50, blank=True, null=True)
    alchemy_id = models.CharField(max_length=50, blank=True, null=True)

    chain_id = models.IntegerField()  # etherscan
    alchemy_chain_id = models.CharField(max_length=50, blank=True, null=True)
    coingecko_chain_id = models.CharField(max_length=50, blank=True, null=True)

    decimals = models.IntegerField()
    symbol = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    logo_url = models.CharField(max_length=255, blank=True, null=True)
    wallets = models.ManyToManyField(
        "Wallet", through="WalletToken", related_name="tokens"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    market_data = JSONField(default=dict, null=True, blank=True)

    def __str__(self):
        return f"{self.symbol} @ {self.chain_id} ({self.address})"

    class Meta:
        db_table = "tokens"
        ordering = ["name"]


class WalletToken(models.Model):
    wallet = models.ForeignKey("Wallet", on_delete=models.CASCADE)
    token = models.ForeignKey(Token, on_delete=models.CASCADE)
    balance = models.FloatField(default=0)
    balance_usd = models.FloatField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wallet_tokens"
        unique_together = ("wallet", "token")
