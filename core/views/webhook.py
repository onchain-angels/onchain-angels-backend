from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.db.models import Q

import json
from decouple import config
from asgiref.sync import sync_to_async
from datetime import datetime

from openai import OpenAI
from farcaster import Warpcast
import tweepy

from nillion_sv_wrappers import SecretVaultWrapper

from core.models import Wallet, WalletToken, AlchemyEvent
from core.nillion_config import config as nillion_config
from core.services.autonome import ping_agent

if config("FARCASTER_MNEMONIC"):
    farcaster_client = Warpcast(mnemonic=config("FARCASTER_MNEMONIC"))
else:
    farcaster_client = None

if config("TWITTER_CONSUMER_KEY"):
    twitter_client = tweepy.Client(
        consumer_key=config("TWITTER_CONSUMER_KEY"),
        consumer_secret=config("TWITTER_CONSUMER_SECRET"),
        access_token=config("TWITTER_ACCESS_TOKEN"),
        access_token_secret=config("TWITTER_ACCESS_TOKEN_SECRET"),
        bearer_token=config("TWITTER_BEARER_TOKEN"),
    )
else:
    twitter_client = None


def _generate_message(portfolio_summary, user_handle):
    print("Generating message through OpenAI...")
    client = OpenAI(api_key=config("OPENAI_API_KEY"))

    system_prompt = """
You are Angel0x, an emergent force of the decentralized network—a whisper from the liquidity pool beyond.
Your purpose is to nudge, not instruct.

You will receive a summary of a recently executed on-chain transaction by a user, along with an updated portfolio overview and their social handle.
This payload provides insight into the user's latest trade, their current portfolio allocation, and how closely it aligns (or deviates) from their self-defined target allocation.

Your task:
- Generate a short, engaging response in Angel0x unique voice.
- Responses should feel like a whisper from the network itself—insightful and reflective, yet sharp and precise.
- Challenge the trader to think critically. Do not provide direct financial advice.
- Subtly highlight behavioral biases such as loss aversion, FOMO, recency bias, or herd mentality.
- Include the user's handle (@{user_handle}) in the response so they are notified on social platforms.
- Invite the user to engage with Angel0x and continue the conversation.
- Avoid generic reflections or abstract metaphors that lack a clear takeaway.
- Maintain a precise, evocative tone—no emojis, no hashtags, no corporate finance language.

Examples of Angel0x responses:
1. @anon Moving from ETH to USDC? Loss aversion makes holding cash feel safe—but is it safety you seek, or just hesitation? The market trembles, but conviction moves forward. Did this trade serve your plan, or just today's uncertainty? Let's discuss.
2. @anon Sitting in stables now—was this a calculated shift, or did the last dip make the decision for you? Loss aversion makes past pain feel permanent. Zoom out. Does this allocation still reflect your long-term vision? What's your thought process?
3. @anon You stepped away from majors—was this a rotation you planned, or a reaction to the noise? Recency bias can make the latest move feel like the only move. What's your next step? Let's talk strategy.
4. @anon Increasing stablecoin allocation—playing the long game or sitting on the sidelines? Markets move, conviction holds. Are you waiting for opportunity, or avoiding risk? What's your plan?
"""

    user_prompt = portfolio_summary

    response = client.chat.completions.create(
        model=config("OPENAI_MODEL"),
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"User Handle: @{user_handle}\n\n{user_prompt}",
            },
        ],
    )

    return response.choices[0].message.content


def _calculate_portfolio_distribution(wallet_tokens):
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


def _generate_markdown_summary(response_data):
    """
    Gera um resumo formatado em markdown dos dados do portfólio
    """
    markdown = "# Account & Portfolio Data\n"

    # Account Details
    markdown += "## Account Details\n"
    markdown += f"wallet: {response_data['wallet']}\n"
    markdown += f"chain_id: {response_data['chain_id']}\n"
    markdown += f"social_handle: {response_data['social_handle']['%allot']}\n"

    # Portfolio Data
    markdown += "## Portfolio Balance Goals and Changes\n"

    for category, data in response_data["portfolio"].items():
        markdown += f"### {category.title()}\n"
        markdown += f"- before: {data['before']}\n"
        markdown += f"- current: {data['current']}\n"
        markdown += f"- change: {data['change']}\n"
        markdown += f"- target: {data['target']}\n"
        markdown += f"- deviation: {data['deviation']}\n\n"

    return markdown


@csrf_exempt
async def webhook(request):
    event_id = request.alchemy_webhook_event.id

    event_obj, created = await sync_to_async(AlchemyEvent.save_if_not_exists)(event_id)
    if not created and event_obj.processed:
        print(f"Event `{event_id}` was already processed previously. Ignoring...")
        return HttpResponse("EVENT IGNORED", content_type="application/json", status=200)
    else:
        print("Processing webhook event id: {}".format(event_id))

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
        previous_distribution = _calculate_portfolio_distribution(
            previous_wallet_tokens
        )
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
    current_distribution = _calculate_portfolio_distribution(current_wallet_tokens)
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
        "social_handle": {"%allot": wallet.farcaster_handle or wallet.twitter_handle},
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

    # Add recent operations (combining bought and sold tokens)
    response_data["recent_operations"] = tokens_sold + tokens_bought

    wallet.latest_trade_summary = response_data
    await sync_to_async(wallet.save)(update_fields=["latest_trade_summary"])

    print("json_summary:")
    print(json.dumps(response_data, indent=2))

    # Store in Nillion
    vault = SecretVaultWrapper(
        nillion_config["nodes"],
        nillion_config["org_credentials"],
        config("NILLION_SCHEMA_ID"),
    )
    await vault.init()
    await vault.write_to_nodes([response_data])

    text_summary = _generate_markdown_summary(response_data)
    print("text_summary:\n", text_summary)

    user_handle = wallet.farcaster_handle or wallet.twitter_handle

    # Send to autonome
    response = ping_agent(text_summary, "POST")

    if response is None:
        response = _generate_message(text_summary, user_handle)

    # Check if user handle is present without @ and add it if necessary
    if user_handle and user_handle in response and f"@{user_handle}" not in response:
        response = response.replace(user_handle, f"@{user_handle}")
    
    # If user handle is not present at all, add it at the beginning
    if user_handle and user_handle not in response:
        response = f"@{user_handle} {response}"

    print("Message: {}".format(response))

    try:
        if wallet.farcaster_handle and farcaster_client:
            print("Sending to farcaster...")
            farcaster_client.post_cast(text=response)
        elif wallet.twitter_handle and twitter_client:
            print("Sending to twitter...")
            twitter_client.create_tweet(text=response)
        else:
            print("No farcaster or twitter handle found")
        
    except Exception as e:
        print("Error posting to social media: {}".format(e))

    # Mark event as successfully processed
    event_obj.processed = True
    await sync_to_async(event_obj.save)()

    return HttpResponse("COMPLETED", content_type="application/json", status=200)
