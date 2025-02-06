from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.db.models import Q

import json
from decouple import config
from asgiref.sync import sync_to_async
from datetime import datetime
from nillion_sv_wrappers import SecretVaultWrapper

from core.models import Wallet, WalletToken
from core.nillion_config import config as nillion_config


def calculate_portfolio_distribution(wallet_tokens):
    """
    Calculates the percentage distribution by category
    """
    total_value_usd = sum(token["balance_usd"] for token in wallet_tokens)
    if total_value_usd == 0:
        return {}

    distribution = {}
    for token in wallet_tokens:
        category = token.get("token__category", "unknown")
        if category not in distribution:
            distribution[category.lower()] = 0
        distribution[category.lower()] += (token["balance_usd"] / total_value_usd) * 100

    return {k: round(v, 2) for k, v in distribution.items()}


def _create_token_movement(token_data, amount, usd_value, movement_type):
    """
    Função auxiliar para criar uma entrada padronizada de movimentação de token
    """
    return {
        "symbol": token_data["token__symbol"],
        "name": token_data["token__name"],
        "category": token_data["token__category"].lower(),
        "coingecko_id": token_data["token__coingecko_id"],
        "chain_id": token_data["token__chain_id"],
        "coingecko_chain_id": token_data["token__coingecko_chain_id"],
        "description": token_data["token__description"],
        "logo_url": token_data["token__logo_url"],
        "amount": str(amount),
        "usd_value": str(usd_value),
        "type": movement_type,
    }


@csrf_exempt
async def webhook(request):
    print("Processing webhook event id: {}".format(request.alchemy_webhook_event.id))
    event = request.alchemy_webhook_event.event

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

    # Capture the previous wallet state
    try:
        normalized_from = from_address.lower()
        normalized_to = to_address.lower()

        # Converting synchronous operations to asynchronous
        wallet = await sync_to_async(Wallet.objects.get)(
            Q(address__iexact=normalized_from) | Q(address__iexact=normalized_to)
        )

        previous_wallet_tokens = await sync_to_async(list)(
            WalletToken.objects.filter(wallet=wallet, balance__gt=0)
            .select_related("token")
            .values(
                "token__address",
                "token__symbol",
                "token__category",
                "token__name",
                "token__coingecko_id",
                "token__chain_id",
                "token__coingecko_chain_id",
                "token__description",
                "token__logo_url",
                "balance",
                "balance_usd",
            )
        )

        # Calculate previous distribution
        previous_distribution = calculate_portfolio_distribution(previous_wallet_tokens)
        print("Previous category distribution:", previous_distribution)

    except Wallet.DoesNotExist:
        print(
            "Wallet not found for addresses {} and {}".format(from_address, to_address)
        )
        return HttpResponse("Wallet not found", status=200)

    # Sync wallet
    await sync_to_async(wallet.sync_wallet)()

    # Get current wallet state
    current_wallet_tokens = await sync_to_async(list)(
        WalletToken.objects.filter(wallet=wallet, balance__gt=0)
        .select_related("token")
        .values(
            "token__address",
            "token__symbol",
            "token__category",
            "token__name",
            "token__coingecko_id",
            "token__chain_id",
            "token__coingecko_chain_id",
            "token__description",
            "token__logo_url",
            "balance",
            "balance_usd",
        )
    )

    # Calculate new distribution
    current_distribution = calculate_portfolio_distribution(current_wallet_tokens)
    # print("Current category distribution:", json.dumps(current_distribution, indent=2))

    # Compare with target portfolio
    target_portfolio = wallet.portfolio
    portfolio_comparison = {}

    for category in set(
        list(current_distribution.keys()) + list(target_portfolio.keys())
    ):
        current_value = current_distribution.get(category, 0)
        target_value = target_portfolio.get(category, 0)
        if abs(current_value - target_value) > 0.01:
            portfolio_comparison[category.lower()] = {
                "current": current_value,
                "target": target_value,
                "deviation": round(current_value - target_value, 2),
            }

    # Calculate distribution changes
    category_changes = {}
    all_categories = set(
        list(previous_distribution.keys()) + list(current_distribution.keys())
    )

    for category in all_categories:
        prev_value = previous_distribution.get(category, 0)
        curr_value = current_distribution.get(category, 0)
        if abs(prev_value - curr_value) > 0.01:  # Mudança maior que 0.01%
            category_changes[category.lower()] = {
                "before": prev_value,
                "after": curr_value,
                "change": round(curr_value - prev_value, 2),
            }

    # Analyze changes
    previous_tokens = {t["token__address"]: t for t in previous_wallet_tokens}
    current_tokens = {t["token__address"]: t for t in current_wallet_tokens}

    # Identify bought tokens (new or increased balance)
    tokens_bought = []
    for addr, current in current_tokens.items():
        if addr not in previous_tokens:
            tokens_bought.append(
                _create_token_movement(
                    current, current["balance"], current["balance_usd"], "new_position"
                )
            )
        elif current["balance"] > previous_tokens[addr]["balance"]:
            tokens_bought.append(
                _create_token_movement(
                    current,
                    current["balance"] - previous_tokens[addr]["balance"],
                    current["balance_usd"] - previous_tokens[addr]["balance_usd"],
                    "increased_position",
                )
            )

    # Identify sold tokens (removed or decreased balance)
    tokens_sold = []
    for addr, previous in previous_tokens.items():
        if addr not in current_tokens:
            tokens_sold.append(
                _create_token_movement(
                    previous,
                    previous["balance"],
                    previous["balance_usd"],
                    "closed_position",
                )
            )
        elif current_tokens[addr]["balance"] < previous["balance"]:
            tokens_sold.append(
                _create_token_movement(
                    previous,
                    previous["balance"] - current_tokens[addr]["balance"],
                    previous["balance_usd"] - current_tokens[addr]["balance_usd"],
                    "decreased_position",
                )
            )

    # Prepare integrated response
    response_data = {
        "wallet": str(wallet.address),
        "chain_id": int(wallet.chain_id),
        "farcaster_handle": {
            "$allot": str(wallet.farcaster_handle) if wallet.farcaster_handle else None
        },
        "twitter_handle": {
            "$allot": str(wallet.twitter_handle) if wallet.twitter_handle else None
        },
        "portfolio": {},
        "recent_operations": [],
        "timestamp": int(datetime.now().timestamp()),
    }

    # Build portfolio data
    all_categories = set(
        list(previous_distribution.keys())
        + list(current_distribution.keys())
        + list(wallet.portfolio.keys())
    )

    for category in all_categories:
        prev_value = previous_distribution.get(category, 0)
        curr_value = current_distribution.get(category, 0)
        target_value = wallet.portfolio.get(category, 0)

        response_data["portfolio"][category] = {
            "before": str(round(prev_value, 2)),
            "current": str(round(curr_value, 2)),
            "change": str(round(curr_value - prev_value, 2)),
            "target": str(target_value),
            "deviation": str(round(curr_value - target_value, 2)),
        }

    # Adiciona operações recentes (combinando tokens comprados e vendidos)
    response_data["recent_operations"] = tokens_sold + tokens_bought

    print("Summary:", json.dumps(response_data, indent=2))

    # Store in Nillion
    vault = SecretVaultWrapper(
        nillion_config["nodes"],
        nillion_config["org_credentials"],
        config("NILLION_SCHEMA_ID"),
    )
    await vault.init()
    await vault.write_to_nodes([response_data])

    return HttpResponse("COMPLETED", content_type="application/json", status=200)
