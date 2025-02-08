import requests
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decouple import config
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db.models import JSONField

from core.services import (
    check_coingecko_by_contract,
    check_coingecko_by_coin,
    get_eth_balance_etherscan,
    get_token_balance_alchemy,
)
from core.models.token import Token, WalletToken


def _add_token_to_wallet(
    wallet, token_contract_address, token_info, token_balance_decimal
):
    token_obj, _ = Token.objects.update_or_create(
        address=token_contract_address,
        chain_id=wallet.chain_id,
        coingecko_chain_id=wallet.coingecko_network,
        defaults={
            "coingecko_id": token_info.get("token_id"),
            "decimals": token_info.get("token_decimals"),
            "symbol": token_info.get("token_symbol"),
            "name": token_info.get("token_name"),
            "description": token_info.get("token_description"),
            "logo_url": token_info.get("logo_url"),
            "category": token_info.get("token_category"),
            "market_data": token_info.get("market_data"),
        },
    )

    token_price_usd = token_info.get("token_price_usd")
    print("token_price: {}".format(token_price_usd))
    token_balance = token_balance_decimal / 10**token_obj.decimals
    print("token_balance: {}".format(token_balance))
    token_balance_usd = token_price_usd * token_balance
    print("token_amount_usd: {}".format(token_balance_usd))

    WalletToken.objects.update_or_create(
        wallet=wallet,
        token=token_obj,
        defaults={
            "balance": token_balance,
            "balance_usd": token_balance_usd,
        },
    )
    return token_obj


def sync_wallet(wallet):
    try:
        # 1. Get token balances from Alchemy
        tokens = get_token_balance_alchemy(wallet.alchemy_network, wallet.address)
    except Exception as e:
        print("Error getting token balances from Alchemy: {}".format(e))
        return

    wallet_tokens = []

    try:
        # 2. Get ETH balance
        eth_balance = get_eth_balance_etherscan(wallet.chain_id, wallet.address)

        if eth_balance > 0:
            try:
                # 3. Get ETH info from CoinGecko
                token_info = check_coingecko_by_coin("ethereum")

            except Exception as e:
                print("Error getting token info from CoinGecko: {}".format(e))

            try:
                eth_obj = _add_token_to_wallet(
                    wallet,
                    "0x0000000000000000000000000000000000000001",
                    token_info,
                    eth_balance,
                )
                wallet_tokens.append(eth_obj.id)

            except Exception as e:
                print(
                    "Error creating or updating Token or WalletToken object: {}".format(
                        e
                    )
                )

    except Exception as e:
        print("Error getting ETH balance from Etherscan: {}".format(e))

    for token in tokens:
        token_contract_address = token.get("contractAddress")
        token_balance_hex = token.get("tokenBalance")
        token_balance_decimal = int(token_balance_hex, 16)

        if token_balance_decimal > 0:
            try:
                # 4. Get token info from CoinGecko
                token_info = check_coingecko_by_contract(
                    wallet.coingecko_network, token_contract_address
                )

            except Exception as e:
                print("Error getting token info from CoinGecko: {}".format(e))
                continue

            try:
                token_obj = _add_token_to_wallet(
                    wallet, token_contract_address, token_info, token_balance_decimal
                )
                wallet_tokens.append(token_obj.id)

            except Exception as e:
                print(
                    "Error creating or updating Token or WalletToken object: {}".format(
                        e
                    )
                )

    WalletToken.objects.filter(wallet=wallet).exclude(
        token__id__in=wallet_tokens
    ).update(balance=0)


def validate_portfolio_sum(value):
    """
    Validates if the sum of portfolio values equals exactly 100
    """
    if not isinstance(value, dict):
        raise ValidationError("Portfolio must be a dictionary")

    total = sum(float(v) for v in value.values())
    if (
        abs(total - 100) > 0.01
    ):  # Allow small margin of error for floating point numbers
        raise ValidationError("Portfolio values must sum exactly to 100%")


class Wallet(models.Model):
    address = models.CharField(max_length=50, unique=True)
    chain_id = models.IntegerField(default=8453)  # etherscan chain id for Base
    farcaster_handle = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    twitter_handle = models.CharField(max_length=50, unique=True, null=True, blank=True)
    portfolio = JSONField(
        default=dict(majors=25, stables=25, alts=25, memes=25),
        validators=[validate_portfolio_sum],
    )
    latest_trade_summary = JSONField(
        null=True,
        blank=True,
        help_text="Armazena o resumo do trade mais recente desta carteira",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.address

    def sync_wallet(self):
        sync_wallet(self)

    @property
    def alchemy_network(self):
        if self.chain_id == 1:
            return "eth-mainnet"
        elif self.chain_id == 8453:
            return "base-mainnet"
        elif self.chain_id == 11155111:
            return "eth-sepolia"
        else:
            raise Exception("Unsupported network: {}".format(self.chain_id))

    @property
    def coingecko_network(self):
        if self.chain_id == 1:
            return "ethereum"
        elif self.chain_id == 8453:
            return "base"
        else:
            raise Exception("Unsupported network: {}".format(self.chain_id))

    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"


# https://docs.alchemy.com/reference/webhook-addresses
def _get_webhook_addresses():
    url = "https://dashboard.alchemy.com/api/webhook-addresses?webhook_id={}&limit=100".format(
        config("ALCHEMY_WEBHOOK_ID")
    )
    headers = {"X-Alchemy-Token": config("ALCHEMY_WEBHOOK_AUTH_TOKEN")}
    response = requests.get(url, headers=headers)
    print(response.text)


# https://docs.alchemy.com/reference/update-webhook-addresses
def _update_webhook_addresses(addresses_to_add, addresses_to_remove):
    url = "https://dashboard.alchemy.com/api/update-webhook-addresses"
    payload = {
        "addresses_to_add": addresses_to_add,
        "addresses_to_remove": addresses_to_remove,
        "webhook_id": config("ALCHEMY_WEBHOOK_ID"),
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-Alchemy-Token": config("ALCHEMY_WEBHOOK_AUTH_TOKEN"),
    }
    response = requests.patch(url, json=payload, headers=headers)
    print(response.text)


@receiver(post_save, sender=Wallet)
def post_save_signal(sender, instance, created, **kwargs):
    if created:
        print("updating webhook addresses")
        _update_webhook_addresses([instance.address], [])
        print("getting webhook addresses")
        _get_webhook_addresses()
        instance.sync_wallet()


@receiver(post_delete, sender=Wallet)
def post_delete_signal(sender, instance, **kwargs):
    print("updating webhook addresses")
    _update_webhook_addresses([], [instance.address])
    print("getting webhook addresses")
    _get_webhook_addresses()
