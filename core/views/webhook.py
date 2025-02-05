from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
import requests
from decouple import config
from django.db.models import Q

from core.models import Token, Wallet, WalletToken
from core.services import (
    check_coingecko_by_contract,
    get_transaction_history_etherscan,
    get_eth_balance_etherscan,
    get_token_balance_alchemy,
    get_token_metadata_alchemy,
    get_token_price_alchemy,
)


@csrf_exempt
def webhook(request):
    # 0. Webhook event from Alchemy
    print("Processing webhook event id: {}".format(request.alchemy_webhook_event.id))

    event = request.alchemy_webhook_event.event
    print("event: {}".format(event))

    network = event.get("network")
    print("network: {}".format(network))

    contracts = []
    activities = event.get("activity")
    for activity in activities:
        if activity.get("category") != "token":
            continue
        from_address = activity.get("fromAddress")
        to_address = activity.get("toAddress")
        asset = activity.get("asset")
        value = activity.get("value")
        raw_contract = activity.get("rawContract")
        contract_address = raw_contract.get("address")
        decimals = raw_contract.get("decimals")
        raw_value = raw_contract.get("rawValue")
        contracts.append(
            {
                "from_address": from_address,
                "to_address": to_address,
                "asset": asset,
                "contract_address": contract_address,
                "decimals": decimals,
                "value": value,
                "raw_value": raw_value,
            }
        )

    print("contracts: {}".format(contracts))

    if len(contracts) == 0:
        return HttpResponse("Ignored", status=200)

    # Captura o estado anterior da carteira
    try:
        normalized_from = from_address.lower()
        normalized_to = to_address.lower()
        wallet = Wallet.objects.get(
            Q(address__iexact=normalized_from) | 
            Q(address__iexact=normalized_to)
        )
        previous_wallet_tokens = list(WalletToken.objects.filter(
            wallet=wallet,
            balance__gt=0
        ).select_related('token').values(
            'token__address',
            'token__symbol',
            'balance',
            'balance_usd'
        ))
        print("Estado anterior da carteira:", previous_wallet_tokens)
    except Wallet.DoesNotExist:
        print("Wallet not found for addresses {} and {}".format(from_address, to_address))
        return HttpResponse("Wallet not found", status=200)

    # Sincroniza a carteira para obter o novo estado
    wallet.sync_wallet()

    # Obtém o novo estado da carteira
    current_wallet_tokens = list(WalletToken.objects.filter(
        wallet=wallet,
        balance__gt=0
    ).select_related('token').values(
        'token__address',
        'token__symbol',
        'balance',
        'balance_usd'
    ))

    # Analisa as mudanças
    previous_tokens = {t['token__address']: t for t in previous_wallet_tokens}
    current_tokens = {t['token__address']: t for t in current_wallet_tokens}

    # Identifica tokens comprados (novos ou aumentou balance)
    tokens_bought = []
    for addr, current in current_tokens.items():
        if addr not in previous_tokens:
            tokens_bought.append({
                'symbol': current['token__symbol'],
                'amount': current['balance'],
                'usd_value': current['balance_usd'],
                'type': 'new_position'
            })
        elif current['balance'] > previous_tokens[addr]['balance']:
            tokens_bought.append({
                'symbol': current['token__symbol'],
                'amount': current['balance'] - previous_tokens[addr]['balance'],
                'usd_value': current['balance_usd'] - previous_tokens[addr]['balance_usd'],
                'type': 'increased_position'
            })

    # Identifica tokens vendidos (removidos ou diminuiu balance)
    tokens_sold = []
    for addr, previous in previous_tokens.items():
        if addr not in current_tokens:
            tokens_sold.append({
                'symbol': previous['token__symbol'],
                'amount': previous['balance'],
                'usd_value': previous['balance_usd'],
                'type': 'closed_position'
            })
        elif current_tokens[addr]['balance'] < previous['balance']:
            tokens_sold.append({
                'symbol': previous['token__symbol'],
                'amount': previous['balance'] - current_tokens[addr]['balance'],
                'usd_value': previous['balance_usd'] - current_tokens[addr]['balance_usd'],
                'type': 'decreased_position'
            })

    print("Tokens comprados:", tokens_bought)
    print("Tokens vendidos:", tokens_sold)

    # Be sure to respond with 200 when you successfully process the event
    return HttpResponse("DONE", status=200)
