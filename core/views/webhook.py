from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
import requests
from decouple import config

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
    wallet_tokens = []

    activities = event.get("activity")
    for activity in activities:
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

    try:
        wallet = Wallet.objects.get(address=to_address)
        print("Wallet: {}".format(wallet))
    except Wallet.DoesNotExist:
        print("Wallet {} not found".format(to_address))
        return HttpResponse("Wallet not found", status=200)

    # alchemy: https://docs.alchemy.com/reference/supported-chains
    # etherscan: https://api.etherscan.io/v2/chainlist
    if network == "BASE_SEPOLIA":
        cg_network = None
        alchemy_network = "base-sepolia"
        etherscan_chain_id = 84532
    elif network == "BASE":
        cg_network = "base"
        alchemy_network = "base-mainnet"
        etherscan_chain_id = 8453
    elif network == "ETH_SEPOLIA":
        cg_network = None
        alchemy_network = "eth-sepolia"
        etherscan_chain_id = 11155111
    elif network == "ETH_MAINNET":
        cg_network = "ethereum"
        alchemy_network = "eth-mainnet"
        etherscan_chain_id = 1
    else:
        print("Unsupported network: {}".format(network))
        raise Exception("Unsupported network: {}".format(network))

    # 1. Get token info from CoinGecko
    if cg_network is not None:
        cg_token_info = check_coingecko_by_contract(cg_network, contract_address)

    # 2. Get a list of Transactions By Address from Basescan
    transaction_history = get_transaction_history_etherscan(
        etherscan_chain_id, to_address
    )

    # 3. ETH balance
    eth_balance = get_eth_balance_etherscan(etherscan_chain_id, to_address)

    if eth_balance > 0:
        try:
            eth_obj, _ = Token.objects.get_or_create(
                address="0x0000000000000000000000000000000000000001",
                category="MAJORS",
                # coingecko_id=xxx,
                # alchemy_id=token_id,
                chain_id=etherscan_chain_id,
                alchemy_chain_id=alchemy_network,
                coingecko_chain_id=cg_network,
                decimals=18,
                symbol="ETH",
                name="ETH",
                # description=xxxx, #coingecko
                # logo_url=xxxx,
            )
            WalletToken.objects.update_or_create(
                wallet=wallet,
                token=eth_obj,
                defaults={
                    "balance": eth_balance,
                },
            )
            wallet_tokens.append(eth_obj.id)

        except Exception as e:
            print(
                "Error creating or updating Token or WalletToken object: {}".format(e)
            )

    # # DEBUG
    # alchemy_network = "eth-mainnet"
    # to_address = ""
    # # DEBUG

    # 4. Get token balances from Alchemy
    tokens = get_token_balance_alchemy(alchemy_network, to_address)

    count = 0
    for token in tokens:

        token_contract_address = token.get("contractAddress")

        count += 1

        print("-------------------------")
        print("token: {}".format(token))

        # 5. Get token metadata from Alchemy
        token_metadata = get_token_metadata_alchemy(
            alchemy_network, token_contract_address
        )
        token_decimals = int(token_metadata.get("result").get("decimals"))
        token_symbol = token_metadata.get("result").get("symbol")
        token_logo = token_metadata.get("result").get("logo")

        token_balance_hex = token.get("tokenBalance")
        print("token_balance_hex: {}".format(token_balance_hex))

        token_balance = int(token_balance_hex, 16)
        print("token_balance: {}".format(token_balance))

        if token_balance > 0:
            try:
                token_obj, _ = Token.objects.get_or_create(
                    address=token_contract_address,
                    # category=xxxx,  #coingecko
                    # coingecko_id=xxx,
                    # alchemy_id=xxx,
                    chain_id=etherscan_chain_id,
                    alchemy_chain_id=alchemy_network,
                    coingecko_chain_id=cg_network,
                    decimals=token_decimals,
                    symbol=token_symbol,
                    name=token_symbol,
                    # description=xxxx, #coingecko
                    logo_url=token_logo,
                )
                WalletToken.objects.update_or_create(
                    wallet=wallet,
                    token=token_obj,
                    defaults={
                        "balance": token_balance_hex,
                    },
                )
                wallet_tokens.append(token_obj.id)

            except Exception as e:
                print(
                    "Error creating or updating Token or WalletToken object: {}".format(
                        e
                    )
                )

        token_amount = token_balance / (10**token_decimals)
        print("token_amount: {}".format(token_amount))

        # 6. Get token price from Alchemy
        token_price_json = get_token_price_alchemy(
            alchemy_network, token_contract_address
        )

        token_price = 0
        for item in token_price_json.get("data"):
            prices = item.get("prices")
            for price in prices:
                price_currency = price.get("currency")
                price_value = price.get("value")
                price_last_updated_at = price.get("lastUpdatedAt")
                if price_currency == "usd":
                    token_price = float(price_value)
                    break

        print("token_price: {}".format(token_price))

        token_amount_usd = token_price * token_amount
        print("token_amount_usd: {}".format(token_amount_usd))

        if count > 10:
            break

    WalletToken.objects.filter(wallet=wallet).exclude(
        token__id__in=wallet_tokens
    ).update(balance=0)

    # Be sure to respond with 200 when you successfully process the event
    return HttpResponse("DONE", status=200)
