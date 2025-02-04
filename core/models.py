import requests
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decouple import config
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db.models import JSONField


def validate_portfolio_sum(value):
    """
    Validates if the sum of portfolio values equals exactly 100
    """
    if not isinstance(value, dict):
        raise ValidationError('Portfolio must be a dictionary')
    
    total = sum(float(v) for v in value.values())
    if abs(total - 100) > 0.01:  # Allow small margin of error for floating point numbers
        raise ValidationError('Portfolio values must sum exactly to 100%')


class Wallet(models.Model):
    address = models.CharField(max_length=50, unique=True)
    farcaster_handle = models.CharField(max_length=50, null=True, blank=True)
    twitter_handle = models.CharField(max_length=50, null=True, blank=True)
    portfolio = JSONField(
        default=dict(
            majors=25,
            stables=25,
            alts=25,
            memes=25
        ),
        validators=[
            validate_portfolio_sum
        ]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.address

    class Meta:
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'


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
def register_alchemy_webhook(sender, instance, **kwargs):
    print("updating webhook addresses")
    _update_webhook_addresses([instance.address], [])
    print("getting webhook addresses")
    _get_webhook_addresses()


@receiver(post_delete, sender=Wallet)
def unregister_alchemy_webhook(sender, instance, **kwargs):
    print("updating webhook addresses")
    _update_webhook_addresses([], [instance.address])
    print("getting webhook addresses")
    _get_webhook_addresses()
