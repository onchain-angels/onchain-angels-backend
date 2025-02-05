import requests
from decouple import config
from openai import OpenAI
from core.models.token import Token

def extract_token_category(token_description):
    client = OpenAI(api_key=config("OPENAI_API_KEY"))
    system_prompt = f"""
You are a crypto analyst. You will be given a token description and set of categories from CoinGecko.
You will need to categorize this token according to a new set of categories: {', '.join([choice[0] for choice in Token.CATEGORY_CHOICES])}.
Be extremely concise and do not include explanations, reasoning, or any additional commentary.
You should respond with only the category name exactly as it is in the list."""
    print("system_prompt: {}".format(system_prompt))
    response = client.chat.completions.create(
        max_tokens=1024,
        model=config("OPENAI_MODEL"),
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": token_description,
            },
        ],
    )
    content = response.choices[0].message.content
    return content


def check_coingecko_by_contract(network, contract_address):
    url = "{coingecko_endpoint}/coins/{network}/contract/{contract_address}".format(
        coingecko_endpoint=config("COINGECKO_API_URL"),
        network=network,
        contract_address=contract_address,
    )
    print(
        "Checking CoinGecko for network `{}` token `{}` ({})...".format(
            network, contract_address, url
        )
    )
    headers = {
        "accept": "application/json",
    }
    token_info = requests.get(url, headers=headers)
    print("check_coingecko_by_contract status: {}".format(token_info.status_code))
    if(token_info.status_code != 200):
        return None
    return parse_coingecko_token_info(token_info.json(), network)


def check_coingecko_by_coin(symbol):
    url = "{coingecko_endpoint}/coins/{symbol}/".format(
        coingecko_endpoint=config("COINGECKO_API_URL"),
        symbol=symbol,
    )
    print(
        "Checking CoinGecko for token `{}` ({})...".format(symbol, url)
    )
    headers = {
        "accept": "application/json",
    }
    token_info = requests.get(url, headers=headers)
    print("check_coingecko_by_coin status: {}".format(token_info.status_code))
    if(token_info.status_code != 200):
        return None
    return parse_coingecko_token_info(token_info.json())


def parse_coingecko_token_info(token_info, network=None):
    token_id = token_info.get("id")
    token_name = token_info.get("name")
    token_symbol = token_info.get("symbol")
    token_description = token_info.get("description", {}).get("en")
    token_categories = token_info.get("categories", [])
    token_description = token_description + "\n" + "Coingecko categories: " + ";".join(token_categories)

    try:
        token_category = extract_token_category(token_description)
        print("token_category: {}".format(token_category))
    except Exception as e:
        print("Error extracting token category: {}".format(e))
        token_category = None

    images = token_info.get("image", {})
    logo_url = images.get("small")
    
    if network:
        platform_details = token_info.get("detail_platforms", {}).get(network, {})
        token_decimals =int(platform_details.get("decimal_place"))
    else:
        token_decimals = 18

    market_data = token_info.get("market_data", {})
    token_price_usd = market_data.get("current_price", {}).get("usd")
    market_data_json = {
        "current_price_usd": token_price_usd,
        "market_cap_usd": market_data.get("market_cap", {}).get("usd"),
        "total_supply": market_data.get("total_supply"),
        "circulating_supply": market_data.get("circulating_supply"),
        "market_cap_rank": market_data.get("market_cap_rank"),
        "fully_diluted_valuation_usd": market_data.get("fully_diluted_valuation", {}).get("usd"),
        "market_cap_fdv_ratio": market_data.get("market_cap_fdv_ratio"),
        "total_volume_usd": market_data.get("total_volume", {}).get("usd"),
        "high_24h_usd": market_data.get("high_24h", {}).get("usd"),
        "low_24h_usd": market_data.get("low_24h", {}).get("usd"),
        "price_change_24h": market_data.get("price_change_24h"),
        "price_change_percentage_24h": market_data.get("price_change_percentage_24h"),
        "price_change_percentage_7d": market_data.get("price_change_percentage_7d"),
        "price_change_percentage_14d": market_data.get("price_change_percentage_14d"),
        "price_change_percentage_30d": market_data.get("price_change_percentage_30d"),
        "price_change_percentage_60d": market_data.get("price_change_percentage_60d"),
        "price_change_percentage_200d": market_data.get("price_change_percentage_200d"),
        "price_change_percentage_1y": market_data.get("price_change_percentage_1y")
    }

    return {
        "token_id": token_id,
        "token_name": token_name,
        "token_symbol": token_symbol,
        "token_description": token_description,
        "token_category": token_category,
        "logo_url": logo_url,
        "token_decimals": token_decimals,
        "token_price_usd": token_price_usd,
        "market_data": market_data_json,
    }


def get_transaction_history_etherscan(chain_id, address):
    print(
        "Getting transaction history for address `{}` on chain `{}`...".format(
            address, chain_id
        )
    )
    url = "{etherscan_endpoint}?chainid={chain_id}&module=account&action={action}&address={address}&startblock=0&endblock=99999999&page={page}&offset={offset}&sort={sort}&apikey={api_key}".format(
        etherscan_endpoint=config("ETHERSCAN_API_URL"),
        chain_id=chain_id,
        action="txlist",  # Normal Transactions
        # action="txlistinternal",  # Internal Transactions
        # action="tokentx",  # ERC20 Token Transfer Events
        # action="tokennfttx",  # ERC721 Token Transfer Events
        address=address,
        page=1,
        offset=1000,
        sort="desc",
        api_key=config("ETHERSCAN_API_KEY"),
    )
    transaction_history = requests.get(url)
    # print("transaction_history: {}".format(transaction_history.json()))
    return transaction_history


def get_eth_balance_etherscan(chain_id, address):
    print(
        "Getting ETH balance for address `{}` on chain `{}`...".format(
            address, chain_id
        )
    )
    url = "{etherscan_endpoint}?chainid={chain_id}&module=account&action=balance&address={address}&tag=latest&apikey={api_key}".format(
        etherscan_endpoint=config("ETHERSCAN_API_URL"),
        chain_id=chain_id,
        address=address,
        api_key=config("ETHERSCAN_API_KEY"),
    )
    response = requests.get(url)
    eth_balance = int(response.json().get("result"))
    # eth_balance_float = float(eth_balance) / 10**18
    print("eth_balance: {} ".format(eth_balance))
    return eth_balance


def get_token_balance_alchemy(network, address):
    print(
        "Getting token balance for address `{}` on network `{}`...".format(
            address, network
        )
    )
    url = "https://{network}.g.alchemy.com/v2/{alchemy_api_key}".format(
        network=network, alchemy_api_key=config("ALCHEMY_API_KEY")
    )
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getTokenBalances",
        "params": [address],
    }
    headers = {"accept": "application/json", "content-type": "application/json"}
    token_balances_response = requests.post(url, json=payload, headers=headers)
    tokens = token_balances_response.json().get("result").get("tokenBalances")
    print("tokens: {}".format(tokens))
    return tokens


def get_token_metadata_alchemy(network, token_contract_address):
    print(
        "Getting token metadata for address `{}` on network `{}`...".format(
            token_contract_address, network
        )
    )

    url = "https://{network}.g.alchemy.com/v2/{alchemy_api_key}".format(
        network=network, alchemy_api_key=config("ALCHEMY_API_KEY")
    )
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getTokenMetadata",
        "params": [token_contract_address],
    }
    headers = {"accept": "application/json", "content-type": "application/json"}
    response_token_metadata = requests.post(url, json=payload, headers=headers)
    token_metadata = response_token_metadata.json()
    print("token_metadata: {}".format(token_metadata))
    return token_metadata


def get_token_price_alchemy(network, token_contract_address):
    print(
        "Getting token price for address `{}` on network `{}`...".format(
            token_contract_address, network
        )
    )
    try:
        url = "https://api.g.alchemy.com/prices/v1/{apiKey}/tokens/by-address".format(
            apiKey=config("ALCHEMY_API_KEY")
        )
        payload = {
            "addresses": [{"network": network, "address": token_contract_address}]
        }
        headers = {"accept": "application/json", "content-type": "application/json"}
        response_token_price = requests.post(url, json=payload, headers=headers)

        token_price = response_token_price.json()
        if token_price.get("error") is not None:
            print("token_price: {}".format(token_price))
            return {"data": []}

        print("token_price: {}".format(token_price))
        return token_price

    except Exception as e:
        print("Error getting token price: {}".format(e))
        return {"data": []}
