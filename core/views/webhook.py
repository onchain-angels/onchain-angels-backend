from django.views.decorators.csrf import csrf_exempt

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
import requests
from decouple import config

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
        from_address = activity.get("fromAddress")
        to_address = activity.get("toAddress")
        asset = activity.get("asset")
        value = activity.get("value")
        raw_contract = activity.get("rawContract")
        contract_address = raw_contract.get("address")
        decimals = raw_contract.get("decimals")
        raw_value = raw_contract.get("rawValue")
        contracts.append({
            "from_address": from_address,
            "to_address": to_address,
            "asset": asset,
            "contract_address": contract_address,
            "decimals": decimals,
            "value": value,
            "raw_value": raw_value
        })

    print("contracts: {}".format(contracts))

    # alchemy: https://docs.alchemy.com/reference/supported-chains
    # etherscan: https://api.etherscan.io/v2/chainlist
    if(network == "BASE_SEPOLIA"):
        cg_network_id = None
        alchemy_network = "base-sepolia"
        etherscan_chain_id = 84532
    elif(network == "BASE"):
        cg_network_id = "base"
        alchemy_network = "base-mainnet"
        etherscan_chain_id = 8453
    elif(network == "ETH_SEPOLIA"):
        cg_network_id = None
        alchemy_network = "eth-sepolia"
        etherscan_chain_id = 11155111
    elif(network == "ETH_MAINNET"):
        cg_network_id = "ethereum"
        alchemy_network = "eth-mainnet"
        etherscan_chain_id = 1
    else:
        print("Unsupported network: {}".format(network))
        raise Exception("Unsupported network: {}".format(network))

    # 1. Get token info from CoinGecko
    if cg_network_id is not None:
        url = "{coingecko_endpoint}/coins/{id}/contract/{contract_address}".format(
            coingecko_endpoint=config("COINMARKETCAP_API_URL"),
            id=cg_network_id,
            contract_address=contract_address
        )
        headers = {
            "accept": "application/json",
            "x-cg-pro-api-key": config("COINGECKO_API_KEY")
        }
        token_info = requests.get(url, headers=headers)

        print("token_info: {}".format(token_info))

    # 2. Get a list of Transactions By Address from Basescan
    url = "{etherscan_endpoint}?chainid={chain_id}&module=account&action={action}&address={address}&startblock=0&endblock=99999999&page={page}&offset={offset}&sort={sort}&apikey={api_key}".format(
        etherscan_endpoint=config("ETHERSCAN_API_URL"),
        chain_id=etherscan_chain_id,
        action="txlist",  # Normal Transactions
        # action="txlistinternal",  # Internal Transactions
        # action="tokentx",  # ERC20 Token Transfer Events
        # action="tokennfttx",  # ERC721 Token Transfer Events
        address=to_address,
        page=1,
        offset=1000,
        sort="desc",
        api_key=config("ETHERSCAN_API_KEY")
    )
    transaction_history = requests.get(url)
    # print("transaction_history: {}".format(transaction_history.json()))

    # 3. ETH balance
    url = "{etherscan_endpoint}?chainid={chain_id}&module=account&action=balance&address={address}&tag=latest&apikey={api_key}".format(
        etherscan_endpoint=config("ETHERSCAN_API_URL"),
        chain_id=etherscan_chain_id,
        address=to_address,
        api_key=config("ETHERSCAN_API_KEY")
    )
    eth_balance = requests.get(url)
    print("eth_balance: {}".format(eth_balance.json()))

    # # DEBUG
    # alchemy_network = "eth-mainnet"
    # to_address = ""
    # # DEBUG

    # 4. Get the token balance from Alchemy
    url = "https://{network}.g.alchemy.com/v2/{alchemy_api_key}".format(
        network=alchemy_network,
        alchemy_api_key=config("ALCHEMY_API_KEY")
    )

    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getTokenBalances",
        "params": [to_address]
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json"
    }
    token_balances_response = requests.post(url, json=payload, headers=headers)
    print("token_balances_response: {}".format(token_balances_response.json()))

    tokens = token_balances_response.json().get("result").get("tokenBalances")

    print("tokens: {}".format(tokens))

    count = 0

    for token in tokens:
        count += 1
        print("-------------------------")
        print("token: {}".format(token))

        # 5. Get the token metadata from Alchemy
        url_token_metadata = "https://{network}.g.alchemy.com/v2/{apiKey}".format(
            network=alchemy_network,
            apiKey=config("ALCHEMY_API_KEY")
        )
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getTokenMetadata",
            "params": [token.get("contractAddress")]
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json"
        }
        response_token_metadata = requests.post(url_token_metadata, json=payload, headers=headers)
        print("response_token_metadata: {}".format(response_token_metadata.json()))

        token_decimals = int(response_token_metadata.json().get("result").get("decimals"))
        print("token_decimals: {}".format(token_decimals))

        token_balance_hex = token.get("tokenBalance") #0x000000000000000000000000000000000000000000000000000000005907c51d
        print("token_balance_hex: {}".format(token_balance_hex))

        token_balance = int(token_balance_hex, 16)
        print("token_balance: {}".format(token_balance))

        token_contract_address = token.get("contractAddress")
        
        token_amount = token_balance / (10 ** token_decimals)
        print("token_amount: {}".format(token_amount))

        # 6. Get the token price from Alchemy
        url_token_price = "https://api.g.alchemy.com/prices/v1/{apiKey}/tokens/by-address".format(
            apiKey=config("ALCHEMY_API_KEY")
        )
        payload = { "addresses": [
                {
                    "network": alchemy_network,
                    "address": token_contract_address
                }
            ] }
        headers = {
            "accept": "application/json",
            "content-type": "application/json"
        }
        response_token_price = requests.post(url_token_price, json=payload, headers=headers)
        print("response_token_price: {}".format(response_token_price.json()))

        data = response_token_price.json().get("data")
        token_price = 0
        for item in data:
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
            return HttpResponse("ENDOFPROCESSING", status=200)

    # Be sure to respond with 200 when you successfully process the event
    return HttpResponse("Done!", status=200)

