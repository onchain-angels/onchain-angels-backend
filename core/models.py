import requests
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decouple import config


class Wallet(models.Model):
    address = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.address

# https://docs.alchemy.com/reference/webhook-addresses
def _get_webhook_addresses():
    url = "https://dashboard.alchemy.com/api/webhook-addresses?webhook_id={}&limit=100".format(config("ALCHEMY_WEBHOOK_ID"))
    headers = {
        "X-Alchemy-Token": config("ALCHEMY_WEBHOOK_AUTH_TOKEN")
    }
    response = requests.get(url, headers=headers)
    print(response.text)


# https://docs.alchemy.com/reference/update-webhook-addresses
def _update_webhook_addresses(addresses_to_add, addresses_to_remove):
    url = "https://dashboard.alchemy.com/api/update-webhook-addresses"
    payload = {
        "addresses_to_add": addresses_to_add,
        "addresses_to_remove": addresses_to_remove,
        "webhook_id": config("ALCHEMY_WEBHOOK_ID")
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-Alchemy-Token": config("ALCHEMY_WEBHOOK_AUTH_TOKEN")
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