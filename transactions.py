from utils import get_user_input, get_api_keys, get_transaction_by_hash, get_transactions_by_address

import random
import hashlib
import os
import pandas as pd
import datetime
import requests
import warnings
import pickle
import glob
import yaml
import pprint
from time import sleep
import numpy as np
from enum import Enum, auto
from pycoingecko import CoinGeckoAPI
from io import StringIO
from collections import Counter

warnings.filterwarnings("ignore")

# TODO: Fix timezones

# DEFINE GLOBALS

# conversion table for going from chain name to native token
NATIVE_TOKEN = {'ethereum': 'ETH', 'polygon': 'MATIC', 'bsc': 'BNB', 'fantom': 'FTM'}

# mapping to translate the chain name into it's value
CHAIN_IDS = {'ethereum': '1', 'polygon': '137', 'bsc': '56', 'fantom': '250'}

# classifications for transactions
CLASSIFICATIONS = {1: 'Buy + Sell',
                   2: 'Buy',
                   3: 'Sell',
                   4: 'Staking',
                   5: 'Unstaking + Income',
                   6: 'Income',
                   7: 'Taxable Loss',
                   8: 'Taxable Gift',
                   9: 'Non-taxable'}

# list of tickers not to confirm
TICKERS_NO_CONFIRM = []
COINGECKO_NO_CONFIRM = []
NOCOINGECKO_NO_CONFIRM = []

# dictionary of swap addresses for each token
SWAP_ADDRESSES = dict()

# dictionary for retrieving previously found prices in token ticker:datetime:price format
# TODO: save prices based on hash rather than name
PREVIOUS_PRICES = dict()


def create_coingecko_id_lookup():
    """
    Create a dictionary that links token tickers to coingecko IDs.
    :return: lookup, that dictionary
    """
    # TODO: save all coin names that match a ticker, and allow user to choose if there is more than 1
    cg = CoinGeckoAPI()
    coin_list = cg.get_coins_list()
    lookup = {}
    id_list = []
    for coin in coin_list:
        if coin['symbol'] not in lookup.keys():
            lookup[coin['symbol'].lower()] = [coin['id']]
        else:
            lookup[coin['symbol'].lower()].append(coin['id'])
        id_list.append(coin['id'])
    # I don't know why this isn't in there
    lookup['bnb'].append('binancecoin')
    # get rid of the SLP ones so it doesn't confuse sushiswap LPs with SLP the token
    del lookup['slp']
    return lookup, id_list


# create coingecko lookup table
COINGECKOID_LOOKUP, COINGECKOID_LIST = create_coingecko_id_lookup()
# create a dict of user selected coingeckoIDs, it is ticker: id
COINGECKOID_USER_SELECTIONS = dict()


class Transaction:
    """
    Contains the information about a single transaction (buy, sell or both).
    """

    def __init__(self, time, transaction_type, token, volume, fee, token_price, token_fee_adjusted_price):
        self.time = time  # datetime objet
        # type is a TransactionType: can be buy, sell, gain or loss
        self.transaction_type = transaction_type
        self.token = token
        self.volume = volume
        # fee per token
        self.fee = fee / self.volume
        # token_price is the price for a single token at that time from coingecko
        self.token_price = token_price
        self.token_fee_adjusted_price = token_fee_adjusted_price

    def __str__(self):
        return str(vars(self))

    def __repr__(self):
        return str(vars(self))

    def __lt__(self, other):
        return self.time < other.time

    def __eq__(self, other):
        return self.time == other.time


class TransactionType(Enum):
    BUY = auto()
    SELL = auto()
    GAIN = auto()
    LOSS = auto()


def read_transactions(start_date, end_date):
    """
    Read in transactions from different sources and sort into a transaction bank. 
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: transaction_bank, a dictionary where each entry is the name of a token and a list of transactions involving
    that token
    """
    transaction_bank = dict()

    read_binance_csv(transaction_bank, start_date, end_date)

    read_onchain_transactions(transaction_bank, start_date, end_date)

    return transaction_bank


# helper functions for `read_transactions`


def read_onchain_config():
    """
    Read in a config files that states which blockchains to pull records from, their scanning website and the wallet
    address(es) to use.
    :return: A dictionary of configurations
    """
    # TODO: read onchain config file
    config = dict()
    return config


def correct_transaction_classification(class_guess):
    """
    Print information asking the user whether the predicted classification is correct, and return class_int, which
    is the user-selected transaction classification
    :param class_guess: the guess of the system
    :return: class_int, an int represented the user-selected classification
    """
    print("Classification choices: ")
    for i in range(1, len(CLASSIFICATIONS) + 1):
        print(f"{i}. {CLASSIFICATIONS[i]}")
    class_correct = input(f"This looks like {class_guess}, is it? (y/N): ")
    if class_correct.lower() != 'y':
        class_int = get_user_input("Which is the correct classification number? (#) ", 'int')
    else:
        class_int = None
    return class_int


# Print iterations progress
def printProgressBar (iteration, total, prefix='', suffix='', decimals=1, length=100, fill='█', printEnd = ''):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end=printEnd)
    # Print New Line on Complete
    if iteration == total:
        print()


def store_token_price(token, token_hash, time, price):
    if token.lower() == 'cake-lp' or token.lower() == 'slp' or token.lower() == 'wlp':
        if token.lower() in PREVIOUS_PRICES.keys():
            PREVIOUS_PRICES[(token, token_hash)][time] = price
        else:
            PREVIOUS_PRICES[(token, token_hash)] = {time: price}
    else:
        if token.lower() in PREVIOUS_PRICES.keys():
            PREVIOUS_PRICES[token][time] = price
        else:
            PREVIOUS_PRICES[token] = {time: price}


def retrieve_token_price(token, token_hash, time, verbose=True):
    prices = []
    if token.lower() == 'cake-lp' or token.lower() == 'slp' or token.lower() == 'wlp':
        if (token, token_hash) in PREVIOUS_PRICES.keys():
            for prev_time in PREVIOUS_PRICES[(token, token_hash)].keys():
                if time-datetime.timedelta(hours=24) <= prev_time <= time+datetime.timedelta(hours=24):
                    prices.append((abs(time-prev_time), prev_time))
            if len(prices) == 0:
                return None
            else:
                (_, closest_time) = min(prices)
            if verbose:
                print(f"We previously found that the price per token for {token}({token_hash}) at {closest_time} was {PREVIOUS_PRICES[(token, token_hash)][closest_time]}.")
                assume = input(f"Would you like to assume the price at {time} was the same? (Y/n) ")
                if assume.lower() == 'n':
                    return None
            return PREVIOUS_PRICES[(token, token_hash)][prev_time]
        return None
    else:
        if token in PREVIOUS_PRICES.keys():
            for prev_time in PREVIOUS_PRICES[token].keys():
                if time-datetime.timedelta(hours=24) <= prev_time <= time+datetime.timedelta(hours=24):
                    prices.append((abs(time-prev_time), prev_time))
            if len(prices) == 0:
                return None
            else:
                (_, closest_time) = min(prices)
            if verbose:
                print(f"We previously found that the price per token for {token} at {closest_time} was {PREVIOUS_PRICES[token][closest_time]}.")
                assume = input(f"Would you like to assume the price at {time} was the same? (Y/n) ")
                if assume.lower() == 'n':
                    return None
            return PREVIOUS_PRICES[token][prev_time]
        return None


def select_cgid_from_lookup(token):
    if token.lower() in COINGECKOID_LOOKUP.keys():
        if len(COINGECKOID_LOOKUP[token.lower()]) == 1:
            token_id = COINGECKOID_LOOKUP[token.lower()][0]
            correct_token_id = input(f"\rIs {token_id} the correct token ID for {token.lower()}? (Y/n) ")
            if correct_token_id.lower() == 'n':
                token_id = input(f"\rWhat is the correct coingecko token ID? (Search token in cg and use coin name in URL) ")
            COINGECKOID_USER_SELECTIONS[token.lower()] = token_id
            again = input("Do you want to be asked this again for this ticker? (Y/n) ")
            if again.lower() == 'n':
                TICKERS_NO_CONFIRM.append(token.lower())
        else:
            print("Possible coingecko IDs:")
            for ind, id in enumerate(COINGECKOID_LOOKUP[token.lower()]):
                print(f"{ind + 1}. {id}")
            print(f"{ind + 2}. None of the above")
            correct_id = get_user_input("Which is the correct coingecko ID? (#) ", 'int')
            if correct_id >= ind + 2 or correct_id <= 0:
                token_id = None
            else:
                token_id = COINGECKOID_LOOKUP[token.lower()][correct_id - 1]
                COINGECKOID_USER_SELECTIONS[token.lower()] = token_id
                again = input("Do you want to be asked this again for this ticker? (Y/n) ")
                if again.lower() == 'n':
                    TICKERS_NO_CONFIRM.append(token.lower())
    else:
        token_id = None
    return token_id


def select_coingecko_id(token):
    # convert token ticker to coingecko token ID
    if token.lower() in TICKERS_NO_CONFIRM and token.lower() in COINGECKOID_USER_SELECTIONS.keys():
        token_id = COINGECKOID_USER_SELECTIONS[token.lower()]
    else:
        if token.lower() in COINGECKOID_USER_SELECTIONS.keys():
            token_id = COINGECKOID_USER_SELECTIONS[token.lower()]
            correct_token_id = input(f"\rIs {token_id} the correct token ID for {token.lower()}? (Y/n) ")
            if correct_token_id.lower() == 'n':
                token_id = select_cgid_from_lookup(token)
            else:
                again = input("Do you want to be asked this again for this ticker? (Y/n) ")
                if again.lower() == 'n':
                    TICKERS_NO_CONFIRM.append(token.lower())
        else:
            token_id = select_cgid_from_lookup(token)
    return token_id


def get_token_price(token, token_contract_address, transaction_time, chain, original_transaction_hash, original_moves, currency='aud'):
    """
    Get the price of a token, using either the coingecko API or if that's not available, an average of recent
    transactions (with removal of outliers).
    :param chain: chain that is being used
    :param token_contract_address: contract address of token
    :param token: token ticker
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param currency: a string, the currency used (usually 'aud')
    :return: token_price, a float representing the price of a single token
    """
    if token.lower() == currency.lower():
        return 1

    use_coingecko = 'y'
    token_id = ""

    # convert the time to unix time
    epoch_time = int(transaction_time.timestamp())

    while (token_id not in COINGECKOID_LIST) and (use_coingecko.lower() != 'n') and (token.lower() not in NOCOINGECKO_NO_CONFIRM):
        # check whether coingecko lookup or manual calculation should be used for price
        if (token.lower() not in COINGECKO_NO_CONFIRM) and (token.lower() not in NOCOINGECKO_NO_CONFIRM):
            use_coingecko = input(f"\rWould you like to use CoinGecko to determine {token}'s price? "
                                  f"If not, manual on-chain price calculation will be used, which takes longer. (Y/n) ")
            if use_coingecko.lower() != 'n':
                # check if we should assume coingecko should be used in the future
                again = input("Do you want to be asked this again for this ticker? (Y/n) ")
                if again.lower() == 'n':
                    COINGECKO_NO_CONFIRM.append(token.lower())
            else:
                # check if we should assume coingecko should not be used in the future
                again = input("Do you want to be asked this again for this ticker? (Y/n) ")
                if again.lower() == 'n':
                    NOCOINGECKO_NO_CONFIRM.append(token.lower())
                break

        if (use_coingecko.lower() != 'n') and (token.lower() not in NOCOINGECKO_NO_CONFIRM):
            token_id = select_coingecko_id(token)

            if token_id not in COINGECKOID_LIST:
                print(f'Token ID {token_id} is not a valid coingecko ID. Enter a different token ID or opt to use manual on-chain price calculation.')
                if token.lower() in COINGECKO_NO_CONFIRM:
                    COINGECKO_NO_CONFIRM.remove(token.lower())
                if token.lower() in TICKERS_NO_CONFIRM:
                    TICKERS_NO_CONFIRM.remove(token.lower())
                if token.lower() in NOCOINGECKO_NO_CONFIRM:
                    NOCOINGECKO_NO_CONFIRM.remove(token.lower())

    # if checks have passed, use coingecko to find price
    if (use_coingecko.lower() != 'n') and (token.lower() not in NOCOINGECKO_NO_CONFIRM) and (token_id in COINGECKOID_LIST):
        twelve_hours = 12 * 60 * 60
        # query the api +- 12 hours around the time of transaction, then find the closest time
        from_timestamp = epoch_time - twelve_hours
        to_timestamp = epoch_time + twelve_hours

        # query the coingecko api here and extract the relevant data
        cg = CoinGeckoAPI()
        for i in range(10):
            try:
                result = cg.get_coin_market_chart_range_by_id(
                    id=token_id,
                    vs_currency=currency,
                    from_timestamp=from_timestamp,
                    to_timestamp=to_timestamp
                )
                break
            except requests.exceptions.HTTPError as error:
                if i == 9:
                    raise error
                print("Coingecko API Request error, likely due to too many requests in a short time period.")
                print("Waiting 1 minute to try again...")
                sleep(60)

        # find the closest time to the time of transaction
        token_price = None  # just in case the is an error
        min_time_difference = float('inf')
        for time, price in result['prices']:
            time_difference = abs(epoch_time - time)
            if time_difference < min_time_difference:
                min_time_difference = time_difference
                token_price = price

        store_token_price(token, token_contract_address, transaction_time, token_price)
        return token_price

    previous_price = retrieve_token_price(token, token_contract_address, transaction_time)
    if previous_price:
        return previous_price

    # else use manual price method
    print(f"Estimating price for {token} from other tokens in transaction...")
    price_estimate = get_estimated_price_from_transaction(original_transaction_hash, token, token_contract_address, chain, original_moves, transaction_time, currency)
    if not price_estimate:
        print(f"Could not estimate price from other tokens, trying other methods...")
    else:
        print(f"Estimated price per token of {token} is {price_estimate} {currency.upper()}.")
        use_price = input(f"Are you confident this is the correct price? "
                          f"If not, further price estimation will be used and you can manually enter a price if they are not successful. (Y/n) ")
        if use_price.lower() != "n":
            store_token_price(token, token_contract_address, transaction_time, price_estimate)
            return price_estimate

    price_estimates = []
    print(f"Estimating price for {token} from other transactions...")
    method1 = input(f"Would you like to try method 1? (y/N) ")
    if method1.lower() == 'y':
        api_domains = {'ethereum': 'api.etherscan.io', 'polygon': 'api.polygonscan.com', 'bsc': 'api.bscscan.com', 'fantom': 'api.ftmscan.com'}

        # get latest block before provided time
        api_key = get_api_keys()[chain]
        block = int(requests.get(f"https://{api_domains[chain]}/api?module=block&action=getblocknobytime&timestamp={epoch_time}&closest=before&apikey={api_key}").json()['result'])

        # get transactions prior to block above
        result = requests.get(f"https://{api_domains[chain]}/api?module=account&action=txlist&address={token_contract_address}&startblock=1&endblock={block}&sort=desc&apikey={api_key}").json()['result']

        # get transaction hashes for non-approval transactions
        transaction_hashes = [transaction['hash'] for transaction in result if transaction['input'][:10] != '0x095ea7b3']

        # iterate through transaction hashes until 10 appropriate transactions are found and add values to lists
        price_estimates = []
        printProgressBar(0, 10, prefix='Price estimates found:', suffix='Complete', length=10)
        progress = 0
        for ind, transaction_hash in enumerate(transaction_hashes):
            # break once you have 10 transactions
            if len(price_estimates) >= 10:
                break

            # get price from transaction
            price_estimate = get_estimated_price_from_transaction(transaction_hash, token, token_contract_address, chain, None, None, currency)

            if price_estimate:
                price_estimates.append(price_estimate)
                progress += 1
                printProgressBar(progress, 10, prefix='Price estimates found:', suffix='Complete', length=10)

        print("")
        if len(price_estimates) >= 10:
            # get average of middle 6 price estimates
            price_estimates.sort()
            print(f"6 price estimates to average: {price_estimates[2:8]}")
            average_price = sum(price_estimates[2:8]) / 6
            print(f"Estimated price is {average_price}")
            token_price = average_price
            store_token_price(token, token_contract_address, transaction_time, token_price)
            return token_price

    method2 = input(f"Would you like to try method 2? (y/N) ")
    if method2.lower() == 'y':
        # look at recent (current day) transactions to find the addresses most commonly involved in swaps of that token
        swap_addresses = find_common_swap_addresses(token, token_contract_address, chain, currency)
        print(swap_addresses)

        for page in range(1, 11):
            if page > 1:
                keep_looking = input(f"Only {len(price_estimates)}/10 price estimates found so far, continue looking? If not you can manually enter the price. (Y/n) ")
                if keep_looking.lower() == 'n':
                    break
            for swap_address in swap_addresses:
                # get transactions prior to block above for each of the swap addresses
                # TODO: try tokentx
                result = \
                requests.get(f"https://{api_domains[chain]}/api?module=account&action=txlist&address={swap_address}&startblock=1&endblock={block}&page={page}&offset=10000&sort=desc&apikey={api_key}").json()[
                    'result']

                if not result:
                    continue

                # get transaction hashes for non-approval transactions
                print("Finding relevant transaction hashes")
                transaction_hashes = []
                for transaction in result:
                    if transaction['input'][:10] != '0x095ea7b3':
                        if token_contract_address.lower()[2:] in transaction['input'][2:]:
                            transaction_hashes.append(transaction['hash'])
                print(f"Found {len(transaction_hashes)} relevant transaction hashes out of {len(result)} total")

                if len(transaction_hashes) == 0:
                    continue

                # iterate through transaction hashes until 10 appropriate transactions are found and add values to lists
                price_estimates = []
                printProgressBar(0, 10, prefix='Price estimates found:', suffix='Complete', length=10)
                progress = 0
                for ind, transaction_hash in enumerate(transaction_hashes):
                    # break once you have 10 transactions
                    if len(price_estimates) >= 10:
                        break

                    # get price from transaction
                    price_estimate = get_estimated_price_from_transaction(transaction_hash, token, token_contract_address, chain, None, None, currency)

                    if price_estimate:
                        price_estimates.append(price_estimate)
                        progress += 1
                        printProgressBar(progress, 10, prefix='Price estimates found:', suffix='Complete', length=10)

                print("")

            if len(price_estimates) >= 10:
                # get average of middle 10 price estimates
                price_estimates.sort()
                print(f"6 price estimates to average: {price_estimates[2:8]}")
                average_price = sum(price_estimates[2:8]) / 6
                print(f"Estimated price is {average_price}")
                token_price = average_price
                store_token_price(token, token_contract_address, transaction_time, token_price)
                return token_price

    print('Could not find enough transactions to get an accurate price estimate...')
    if len(price_estimates) > 0:
        print(f"Price estimates found: {price_estimates}")
    token_price = get_user_input(f'Enter price per token at {transaction_time} in {currency} manually: ', 'float')
    save_price = input(f"Would you like to save this price of {token_price} {currency} for {token}? (y/N) ")
    if save_price.lower() == 'y':
        store_token_price(token, token_contract_address, transaction_time, token_price)
    return token_price


def get_estimated_price_from_transaction(transaction_hash, token, token_contract_address, chain, original_moves, original_time, currency='aud'):
    # if we have the original moves, no need to read in
    if not original_moves:
        # read information about transaction into df
        data_text = get_transaction_by_hash(CHAIN_IDS[chain], transaction_hash)
        try:
            df = pd.read_csv(StringIO(data_text), dtype=str)
        except pd.errors.ParserError:
            return None

        if (len(df.index) == 0) or 'log_events_decoded_signature' not in df.columns or 'log_events_decoded_signature' not in df.columns:
            return None

        # parse times
        df['block_signed_at'] = pd.to_datetime(df['block_signed_at'], format="%Y-%m-%dT%H:%M:%SZ")

        # get token transfers associated with hash
        transaction_df = df[(df['tx_hash'] == transaction_hash)
                            & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]

        if len(transaction_df.index) == 0:
            return None

        # get wallet that triggered transaction
        wallet = transaction_df['from_address'].iloc[0]

        # parse transactions into 'moves'
        transaction_time, moves, gas_fee_fiat = parse_onchain_transactions(chain, wallet, transaction_df, transaction_hash, currency, True)
    else:
        moves = original_moves
        transaction_time = original_time

    # get moves in each direction
    in_moves = [move for move in moves if move['direction'] == 'in']
    out_moves = [move for move in moves if move['direction'] == 'out']

    # only keep going if:
    # all tokens are in coingeckoid_lookup, this prevents this code from looping
    # AND there is one incoming and one outgoing token, for simplicity
    # AND one of those tokens is the token in question
    tmp = [(move['token'].lower() in COINGECKOID_LOOKUP.keys(), move['token'].lower() == token.lower(), retrieve_token_price(move['token'], move['token_contract'], transaction_time, verbose=False)) for move in moves]
    if (not all([(move['token'].lower() in COINGECKOID_LOOKUP.keys()
                  or move['token'].lower() == token.lower())
                  or retrieve_token_price(move['token'], move['token_contract'], transaction_time, verbose=False)
                 for move in moves])
            or not any([move['token'].lower() == token.lower() for move in moves])):
        return None

    # get value of opposite token, and use this to calculate price per token
    in_moves_excluding, out_moves_excluding, in_values, out_values = get_moves_and_values_by_direction_excluding(moves, transaction_time, chain, token, transaction_hash, currency)
    value_diff = abs(sum(in_values) - sum(out_values))
    quantity_diff = abs(sum([move['quantity'] for move in in_moves if move['token'].lower() == token.lower()]) - sum([move['quantity'] for move in out_moves if move['token'].lower() == token.lower()]))
    price_1token = value_diff / quantity_diff
    return price_1token


def find_common_swap_addresses(token, token_address, chain, currency):

    if token.lower() in SWAP_ADDRESSES.keys():
        return SWAP_ADDRESSES[token.lower()]

    # read information about transaction into df
    data_text = get_transactions_by_address(CHAIN_IDS[chain], token_address, page_size=2500)

    if not data_text:
        return []

    df = pd.read_csv(StringIO(data_text), dtype=str)

    if len(df.index) == 0 or 'log_events_decoded_signature' not in df.columns:
        return []

    # parse times
    df['block_signed_at'] = pd.to_datetime(df['block_signed_at'], format="%Y-%m-%dT%H:%M:%SZ")

    # get token transfers only
    transaction_df = df[(df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]

    # get only transactions that actually involve the token
    sub_df = transaction_df[(transaction_df["log_events_sender_address"].str.lower() == token_address.lower())]

    # get transactions for which the token is either going to or coming from the invoker
    sub_df = sub_df[(sub_df["from_address"].str.lower() == sub_df["log_events_decoded_params_value"].str.lower())]

    if len(transaction_df.index) == 0:
        return []

    # get unique transaction hashes from sub_df
    transaction_hashes = sub_df['tx_hash'].unique()

    swap_addresses = []

    print("Finding swap addresses...")
    for ind, transaction_hash in enumerate(transaction_hashes):
        if len(swap_addresses) > 100:
            break
        if ind % 10 == 0:
            print(f"{ind}/{min(100, len(transaction_hashes))}")

        # get wallet that triggered transaction
        wallet = transaction_df[transaction_df['tx_hash'] == transaction_hash]['from_address'].iloc[0]

        # parse transactions into 'moves'
        transaction_time, moves, gas_fee_fiat = parse_onchain_transactions(chain, wallet, transaction_df, transaction_hash, currency, True)

        # only use transactions that have at least one token going in and one token going out
        if (len([move for move in moves if move['direction'] == 'in']) > 0) and len([move for move in moves if move['direction'] == 'out']) > 0:
            # get the associated addresses
            swap_addresses.append(wallet)
            swap_addresses.append(transaction_df[transaction_df['tx_hash'] == transaction_hash]['to_address'].iloc[0])

    counter = Counter(swap_addresses)

    top = set([address for address in swap_addresses if counter[address] >= 3])

    SWAP_ADDRESSES[token.lower()] = top

    return top


def get_moves_and_values_by_direction(moves, transaction_time, chain, transaction_hash, currency='aud'):
    """
    Given a list of moves (movements of tokens in our out of wallet), splits the moves based on direction (whether they
    are incoming or outgoing) and calculates the total values of each token within the transaction, and the proportion
    of the opposite direction's tokens' value.
    What is proportion?
    The proportion of the value going in the opposite direction each different token is worth.
    This is not 1 when a more than one token is exchanged for one or more tokens.
    If token A is worth $1 and token B is worth $3 and you trade 1 token A and 3 token B for 1 token C, then the
    proportions will be [0.1, 0.9]. Then the cost basis of token A is
    0.1 * value(C) + fees and the cost basis of token B is 0.9 * value (C) + fees / 3.
    :param chain: the chain ID of the chain we are currently working with
    :param moves: a list of dictionaries, where each dictionary gives information about the movement of a token
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param currency: a string, the currency used (usually 'aud')
    :return: in_moves & out_moves, subset lists of the moves dictionaries, in_values & out_values, lists of the total
    values exchanged of each of the tokens exchanged, in_prop & out_prop, lists of the proportions of value in each
    direction that each different token represents
    """
    # split tokens into incoming and outgoing
    in_moves = [move for move in moves if move['direction'] == 'in']
    out_moves = [move for move in moves if move['direction'] == 'out']

    # calculate values
    in_values = []
    out_values = []
    for move in in_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, transaction_hash, moves, currency)
        price_total = price_1token * move['quantity']
        in_values.append(price_total)

    for move in out_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, transaction_hash, moves, currency)
        price_total = price_1token * move['quantity']
        out_values.append(price_total)

    # calculate proportional values, so that if there are multiple ingoing tokens you can work out how much of the outgoing value each is 'swapped for'
    in_prop = [val / sum(in_values) for val in in_values]
    out_prop = [val / sum(out_values) for val in out_values]

    return in_moves, out_moves, in_values, out_values, in_prop, out_prop


def get_moves_and_values_by_direction_excluding(moves, transaction_time, chain, exclude, transaction_hash, currency='aud'):
    """
    Given a list of moves (movements of tokens in our out of wallet), splits the moves based on direction (whether they
    are incoming or outgoing) and calculates the total values of each token within the transaction, and the proportion
    of the opposite direction's tokens' value.
    Does not calculate the value of the token 'exclude' - this prevents circular value lookups when using this
    function within a value lookup.
    What is proportion?
    The proportion of the value going in the opposite direction each different token is worth.
    This is not 1 when a more than one token is exchanged for one or more tokens.
    If token A is worth $1 and token B is worth $3 and you trade 1 token A and 3 token B for 1 token C, then the
    proportions will be [0.1, 0.9]. Then the cost basis of token A is
    0.1 * value(C) + fees and the cost basis of token B is 0.9 * value (C) + fees / 3.
    :param exclude: ticker of token to NOT lookup the value of
    :param chain: the chain ID of the chain we are currently working with
    :param moves: a list of dictionaries, where each dictionary gives information about the movement of a token
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param currency: a string, the currency used (usually 'aud')
    :return: in_moves & out_moves, subset lists of the moves dictionaries, in_values & out_values, lists of the total
    values exchanged of each of the tokens exchanged, in_prop & out_prop, lists of the proportions of value in each
    direction that each different token represents
    """
    # split tokens into incoming and outgoing
    in_moves = [move for move in moves if (move['direction'] == 'in' and move['token'].lower() != exclude.lower())]
    out_moves = [move for move in moves if (move['direction'] == 'out' and move['token'].lower() != exclude.lower())]

    # calculate values
    in_values = []
    out_values = []
    for move in in_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, transaction_hash, moves, currency)
        price_total = price_1token * move['quantity']
        in_values.append(price_total)

    for move in out_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, transaction_hash, moves, currency)
        price_total = price_1token * move['quantity']
        out_values.append(price_total)

    return in_moves, out_moves, in_values, out_values


def add_transactions_w_opposite(transaction_bank, self_moves, self_values, self_props, self_count, opp_values, opp_count, gas_fee_fiat, transaction_time, transaction_type):
    """

    :param transaction_bank: a dictionary that maps token tickers to a list of transactions involving that token
    :param self_moves: 'move' dictionaries associated with the token you are adding to the transaction bank
    :param self_props: the proportions of the opposite value that each transaction is worth. This is not 1 when a more than one token is exchanged for one or more tokens.
    If token A is worth $1 and token B is worth $3 and you trade 1 token A and 3 token B for 1 token C, then the proportions will be [0.1, 0.9]. Then the cost basis of token A is
    0.1 * value(C) + fees and the cost basis of token B is 0.9 * value (C) + fees / 3.
    :param self_count: number of different tokens you are adding to the transaction bank
    :param opp_values: total values of the tokens that the tokens being added are exchanged for
    :param opp_count: number of different tokens that the tokens being added are exchange for
    :param gas_fee_fiat: the price of gas in fiat currency (whichever currency is used in outer functions)
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param transaction_type: the transaction type of type TransactionType (BUY, SELL, GAIN, LOSS)
    :return: None (transactions are added to existing transaction bank dictionary)
    """
    # calculate raw price per token and tax-correct price after fees, and add transactions to transaction bank
    # use out_values to calculate buy price of in tokens and vice versa
    for move, value, prop in zip(self_moves, self_values, self_props):
        raw_price_1token = sum(opp_values) * prop / move['quantity']
        price_inc_fee_1token = (sum(opp_values) * prop + (gas_fee_fiat / (self_count + opp_count))) / move['quantity']
        temp_transaction = Transaction(transaction_time, transaction_type, move['token'], move['quantity'], (gas_fee_fiat / (self_count + opp_count)), raw_price_1token,
                                       price_inc_fee_1token)

        previously_calced_price = value / move['quantity']
        if raw_price_1token > previously_calced_price * 1.1 or raw_price_1token < previously_calced_price * 0.9:
            print(f"WARNING: expected price for {move['token']} considering other tokens is {raw_price_1token} while price calculated from coingecko or manual methods was {previously_calced_price}."
                  f"\n{raw_price_1token} will be used as the cost base if you continue, and this may be incorrect."
                  f"\nYou may want to end this program, restart from last save and edit the transaction.")
            _ = input("(Press enter to continue) ")

        print(temp_transaction)
        _ = input('Adding above transaction... (Press enter to continue)')
        if move['token'].lower() == 'cake-lp' or move['token'].lower() == 'slp' or move['token'].lower() == 'wlp':
            if move['token'] in transaction_bank:
                transaction_bank[(move['token'], move['token_contract'])].append(temp_transaction)
            else:
                transaction_bank[(move['token'], move['token_contract'])] = [temp_transaction]
        else:
            if move['token'] in transaction_bank:
                transaction_bank[move['token']].append(temp_transaction)
            else:
                transaction_bank[move['token']] = [temp_transaction]


def add_transactions_no_opposite(transaction_bank, self_moves, self_count, self_values, gas_fee_fiat, transaction_time, transaction_type, taxable_prop, silent_income=False):
    """
    Calculate the cost basis/price of a cryptocurrency token exchanged in a transaction, and add it to the transaction bank
    This function is used where you calculate the price based on the market value of the token, rather than the market value of what it is being exchanged with.
    :param transaction_bank: a dictionary that maps token tickers to a list of transactions involving that token
    :param self_moves: 'move' dictionaries associated with the token you are adding to the transaction bank
    :param self_count: number of different tokens you are adding to the transaction bank
    :param gas_fee_fiat: the price of gas in fiat currency (whichever currency is used in outer functions)
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param transaction_type: the transaction type of type TransactionType (BUY, SELL, GAIN, LOSS)
    :param taxable_prop: the proportion that is taxable. This is generally relevant where a token is unstaked and you receive both the principle and interest back in one transaction.
    Then, only the interest in taxable.
    :return: None (transactions are added to existing transaction bank dictionary)
    """
    # calculate raw price per token and tax-correct price after fees, and add transactions to transaction bank
    # use value of tokens at the time you bought them as value
    for move, value in zip(self_moves, self_values):
        raw_price_1token = value / move['quantity']
        price_inc_fee_1token = (value * taxable_prop + (gas_fee_fiat / self_count)) / (move['quantity'] * taxable_prop)
        temp_transaction = Transaction(transaction_time, transaction_type, move['token'], move['quantity'] * taxable_prop, gas_fee_fiat / self_count, raw_price_1token,
                                       price_inc_fee_1token)
        print(vars(temp_transaction))
        if not silent_income:
            _ = input('Adding above transaction... (Press enter to continue)')
        if move['token'].lower() == 'cake-lp' or move['token'].lower() == 'slp' or move['token'].lower() == 'wlp':
            if move['token'] in transaction_bank:
                transaction_bank[(move['token'], move['token_contract'])].append(temp_transaction)
            else:
                transaction_bank[(move['token'], move['token_contract'])] = [temp_transaction]
        else:
            if move['token'] in transaction_bank:
                transaction_bank[move['token']].append(temp_transaction)
            else:
                transaction_bank[move['token']] = [temp_transaction]


def classify_transaction(temp_moves, currency):
    """
    Get input from user to classify transaction type, allowing tax rules to be applied correctly
    :param temp_moves: list of dictionaries, each with information about the movement of a single cryptocurrency token within a transaction
    :param currency: string, name of currency used (usually 'aud')
    :return: class_int, the classification as an integer, in_count, the number of different incoming tokens, out_count, the number of different outgoing tokens
    """

    in_count = len([True for move in temp_moves if move['direction'] == 'in'])
    out_count = len([True for move in temp_moves if move['direction'] == 'out'])

    # classifications = {1: 'Buy + Sell',
    #                    2: 'Buy',
    #                    3: 'Sell',
    #                    4: 'Staking',
    #                    5: 'Unstaking + Income',
    #                    6: 'Income',
    #                    7: 'Taxable Loss',
    #                    8: 'Taxable Gift',
    #                    9: 'Non-taxable'}

    if in_count > 0 and out_count > 0:
        class_guess = 'Buy + Sell'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 1
    elif (in_count == 1 and out_count == 0) or (currency.lower() in [move['token'].lower() for move in temp_moves if move['direction'] == 'out']):
        class_guess = 'Buy'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 2
    elif (in_count == 0 and out_count > 0) or (currency.lower() in [move['token'].lower() for move in temp_moves if move['direction'] == 'in']):
        class_guess = 'Sell'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 3
    elif in_count > 1 and out_count == 0:
        class_guess = 'Income'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 6
    elif in_count == 0 and out_count == 0:
        class_guess = 'Non-taxable'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 9
    else:
        class_guess = 'Non-taxable'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 9

    return class_int, in_count, out_count


def add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, chain, transaction_hash, currency, silent_income=False):
    """
    Gets the fiat values of the tokens in the transaction and adds transaction to transaction bank, using on the
    transaction classification provided in class_int to determine that TransactionType and other details.
    :param chain: the chain that we are currently working on
    :param class_int: the transaction classification as an integer
    :param transaction_bank: a dictionary mapping a token to a list of transactions
    :param temp_moves: a list of token movements, each a dictionary that is temporarily holding some information about
    the movement until it can be added to the transaction bank
    :param in_count: number of different incoming tokens
    :param out_count: number of different outgoing tokens
    :param gas_fee_fiat: gas fee in fiat currency
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param currency: fiat currency, usually 'aud'
    :return: None, transaction is added to existing transaction bank dictionary
    """
    if class_int == 1:  # Buy + Sell
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, transaction_hash, currency)
        # add transactions with incoming tokens (buys)
        add_transactions_w_opposite(transaction_bank, in_moves, in_values, in_prop, in_count, out_values, out_count, gas_fee_fiat, transaction_time, TransactionType.BUY)
        # then add transactions with outgoing tokens (sells)
        add_transactions_w_opposite(transaction_bank, out_moves, out_values, out_prop, out_count, in_values, in_count, gas_fee_fiat, transaction_time, TransactionType.SELL)
    elif class_int == 2:  # Buy
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, transaction_hash, currency)
        # add transactions with incoming tokens (buys)
        add_transactions_w_opposite(transaction_bank, in_moves, in_values, in_prop, in_count, out_values, out_count, gas_fee_fiat, transaction_time, TransactionType.BUY)
    elif class_int == 3:  # Sell
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, transaction_hash, currency)
        # then add transactions with outgoing tokens (sells)
        add_transactions_w_opposite(transaction_bank, out_moves, out_values, out_prop, out_count, in_values, in_count, gas_fee_fiat, transaction_time, TransactionType.SELL)
    elif class_int == 5:  # Unstaking + Income
        for move in temp_moves:
            print(f"Token: {move}")
            income = input("Are some of these tokens income (tokens that you did not stake)? (y/N) ")
            if income.lower() == "y":
                all_income = input("Are ALL of these tokens income? (Y/n) ")
                if all_income.lower() == "n":
                    income_amount = get_user_input("How many units are income?", 'float')
                    income_prop = income_amount / move['quantity']
                    # get values of tokens, used to calculate buy and sell cost bases/prices
                    in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction([move], transaction_time, chain, transaction_hash, currency)
                    # add transactions
                    add_transactions_no_opposite(transaction_bank, in_moves, in_count, in_values, gas_fee_fiat, transaction_time, TransactionType.GAIN, income_prop)
                else:
                    # get values of tokens, used to calculate buy and sell cost bases/prices
                    in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction([move], transaction_time, chain, transaction_hash, currency)
                    # add transactions
                    add_transactions_no_opposite(transaction_bank, in_moves, in_count, in_values, gas_fee_fiat, transaction_time, TransactionType.GAIN, 1)
            else:
                continue

    elif class_int == 6:  # income
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, transaction_hash, currency)
        # add transactions with incoming tokens (income)
        add_transactions_no_opposite(transaction_bank, in_moves, in_count, in_values, gas_fee_fiat, transaction_time, TransactionType.GAIN, 1, silent_income)
    elif class_int == 7:  # taxable loss
        # get values of tokens, used to calculate buy and sell cost bases/prices
        _, out_moves, _, out_values, _, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, transaction_hash, currency)
        # add transactions with outgoing tokens (losses)
        add_transactions_no_opposite(transaction_bank, out_moves, out_count, out_values, gas_fee_fiat, transaction_time, TransactionType.LOSS, 1)
    elif class_int == 8:  # taxable gift
        # get values of tokens, used to calculate buy and sell cost bases/prices
        _, out_moves, _, out_values, _, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain,transaction_hash,  currency)
        # add transactions with outgoing tokens (gifts
        add_transactions_no_opposite(transaction_bank, out_moves, out_count, out_values, gas_fee_fiat, transaction_time, TransactionType.SELL, 1)
    elif class_int in [4, 9]:
        _ = input('No taxable transactions... (Press enter to continue)')


def parse_onchain_transactions(chain, wallet, df, transaction_hash, currency='aud', checking_price=False):
    # setup object to store intermediate information about ingoing and outgoing tokens
    temp_moves = []

    # get token transfers associated with hash
    transaction_df = df[(df['tx_hash'] == transaction_hash)
                        & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]
    transaction_time = transaction_df['block_signed_at'].iloc[0]

    # get gas fee from transaction
    transaction_df['gas_spent'] = pd.to_numeric(transaction_df['gas_spent'], errors='coerce')
    transaction_df['gas_price'] = pd.to_numeric(transaction_df['gas_price'], errors='coerce')
    gas_fee_native_token = max(transaction_df['gas_spent'] * transaction_df['gas_price'] / 1e18)
    gas_fee_fiat = gas_fee_native_token * get_token_price(NATIVE_TOKEN[chain], None, transaction_time, chain, transaction_hash, None, currency)

    # get incoming tokens from token transfers
    in_mask = (transaction_df['log_events_decoded_signature'] == 'Transfer(indexed address from, indexed address to, uint256 value)') \
              & (transaction_df['log_events_decoded_params_name'] == 'to') \
              & (transaction_df['log_events_decoded_params_value'] == wallet.lower())
    in_indicies = transaction_df.index[in_mask]

    # for each incoming token, get details
    for ind in in_indicies:
        quantity = int(transaction_df['log_events_decoded_params_value'][ind + 1]) / 1e18
        if quantity > 0:
            temp_moves.append({'token': transaction_df['log_events_sender_contract_ticker_symbol'][ind],
                               'token_contract': transaction_df['log_events_sender_address'][ind],
                               'direction': 'in',
                               'quantity': quantity})

    # get outgoing tokens from token transfers
    out_mask = ((transaction_df['log_events_decoded_signature'] == 'Transfer(indexed address from, indexed address to, uint256 value)')
                & (transaction_df['log_events_decoded_params_name'] == 'from')
                & (transaction_df['log_events_decoded_params_value'] == wallet.lower())
                )
    out_indicies = transaction_df.index[out_mask]

    # for each outgoing token, get details
    for ind in out_indicies:
        quantity = int(transaction_df['log_events_decoded_params_value'][ind + 2]) / 1e18
        if quantity > 0:
            temp_moves.append({'token': transaction_df['log_events_sender_contract_ticker_symbol'][ind],
                               'token_contract': transaction_df['log_events_sender_address'][ind],
                               'direction': 'out',
                               'quantity': quantity})

    # get internal transactions related to hash
    api_domains = {'ethereum': 'api.etherscan.io', 'polygon': 'api.polygonscan.com', 'bsc': 'api.bscscan.com', 'fantom': 'api.ftmscan.com'}
    api_key = get_api_keys()[chain]
    response = requests.get(f"https://{api_domains[chain]}/api?module=account&action=txlistinternal&txhash={transaction_hash}&apikey={api_key}")

    result = response.json()['result']
    # print(f"Internal transactions: {result}")

    # use temporary dictionary to store information about transaction until more information can be gained so it can be added to transaction bankfixed
    for internal_transaction in result:
        # get incoming tokens from internal transactions
        if internal_transaction['to'].lower() == wallet.lower():
            temp_moves.append({'token': NATIVE_TOKEN[chain],
                               'token_contract': None,
                               'direction': 'in',
                               'quantity': int(internal_transaction['value']) / 1e18})

        # get outgoing tokens from internal transfers
        if internal_transaction['from'].lower() == wallet.lower():
            temp_moves.append({'token': NATIVE_TOKEN[chain],
                               'token_contract': None,
                               'direction': 'out',
                               'quantity': int(internal_transaction['value']) / 1e18})

    # for some reason pancakeswap or similar swaps of a token for the native token don't show the native token movement as a normal transaction OR an internal transaction :(
    # catch these here

    # get swaps associated with hash
    swap_df = df[(df['tx_hash'] == transaction_hash)
                        & (df["log_events_decoded_signature"] ==
                           "Swap(indexed address sender, uint256 amount0In, uint256 amount1In, uint256 amount0Out, uint256 amount1Out, indexed address to)")]

    # get moves in each direction
    in_moves = [move for move in temp_moves if move['direction'] == 'in']
    out_moves = [move for move in temp_moves if move['direction'] == 'out']

    # check where wallet is
    # check whether wallet is giver of native token (recipient of normal token)
    mask = (swap_df['log_events_decoded_params_name'] == 'to')
    is_native_sender = (swap_df['log_events_decoded_params_value'][mask].str.lower() == wallet.lower()).all()
    mask = (swap_df['log_events_decoded_params_name'] == 'sender')
    is_native_recipient = (swap_df['log_events_decoded_params_value'][mask].str.lower() == wallet.lower()).all()

    # catch those where native token out, something else in
    if len(swap_df) > 0 and 1 <= len(in_moves) <= 2 and len(out_moves) == 0 and is_native_sender:
        mask = (swap_df['log_events_decoded_params_name'] == 'amount1In')
        volume = swap_df['log_events_decoded_params_value'][mask]
        temp_moves.append({'token': NATIVE_TOKEN[chain],
                           'token_contract': None,
                           'direction': 'out',
                           'quantity': int(volume) / 1e18})

    # catch those where something else out, native token in
    if len(swap_df) > 0 and len(in_moves) == 0 and 1 <= len(out_moves) <= 2 and is_native_recipient:
        mask = (swap_df['log_events_decoded_params_name'] == 'amount0Out')
        volume = swap_df['log_events_decoded_params_value'][mask]
        temp_moves.append({'token': NATIVE_TOKEN[chain],
                           'token_contract': None,
                           'direction': 'in',
                           'quantity': int(volume) / 1e18})

    changes = 'y'
    while changes.lower() == 'y' and not checking_price:
        print("Token movements: ")
        for n, move in enumerate(temp_moves):
            print(f"{n + 1}. {move}")
        changes = input("Would you like to make any changes? (y/N) ")
        if changes.lower() == 'y':
            print("Options: \n1. Remove a transaction \n2. Add a transaction")
            option = input(f"Select an option: (#/N) ")
            if option.strip() == '1':
                remove = input("Which transaction would you like to remove? (#/N) ")
                if remove in [str(m) for m in range(1, len(temp_moves)+1)]:
                    del temp_moves[int(remove)-1]
            elif option.strip() == '2':
                ticker = input("Enter token ticker: ")
                token_contract = input("Enter token contract address: ")
                direction = get_user_input("Enter token movement direction: (in/out) ", 'direction')
                quantity = get_user_input("Enter quantity: (#) ", 'float')
                temp_moves.append({'token': ticker,
                                   'token_contract': token_contract,
                                   'direction': direction,
                                   'quantity': quantity})
    return transaction_time, temp_moves, gas_fee_fiat


def read_onchain_transactions(chain, wallet, transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date, currency='aud'):
    """
    Reads in transaction data from an etherscan-based blockchain scanning website and adds transactions to the
    transaction bank.
    :param pickle_file_name: name of the file used when pickling this session (string)
    :param processed_transaction_hashes: list of hashes that have already been processed
    :param chain: string of scanning website domain
    :param wallet: string of wallet address
    :param transaction_bank: a dictionary mapping a token to a list of transactions
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :param currency: currency to calculate price in, should be a coingecko option
    :return: The updated transaction_bank dictionary, mapping tokens to a list of transactions
    """
    # TODO: check for value way off market value

    # read all files for a given chain into single data frame
    path = os.path.join('transaction-files', chain)
    all_files = glob.glob(path + "/*.csv")

    df_list = []

    for filename in all_files:
        df = pd.read_csv(filename, index_col=None, header=0)
        df_list.append(df)

    df = pd.concat(df_list, axis=0, ignore_index=True)

    # get only transactions within date range
    df['block_signed_at'] = pd.to_datetime(df['block_signed_at'], format="%Y-%m-%dT%H:%M:%SZ")
    df = df[(df['block_signed_at'] >= start_date) & (df['block_signed_at'] < end_date)]
    df.sort_values(by='block_signed_at', inplace=True)

    # fix types
    df['gas_spent'] = pd.to_numeric(df['gas_spent'], errors='coerce')
    df['gas_price'] = pd.to_numeric(df['gas_price'], errors='coerce')

    # get unique transaction hashes, removing those that have been previously processed
    transaction_hashes = list(dict.fromkeys(df['tx_hash']))

    # iterate through transaction hashes, parsing them and adding transactions to transaction bank
    while len(transaction_hashes) > 0:
        transaction_hash = transaction_hashes.pop(0)
        if transaction_hash in processed_transaction_hashes:
            continue
        transaction_df = df[(df['tx_hash'] == transaction_hash)
                            & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]
        if len(transaction_df) == 0:
            continue
        # parse transaction token movements into a dictionary 'temp_moves'
        print("-------------------------------------------------------------------------------------------------")
        print(f"Transaction hash: {transaction_hash}")
        transaction_time = transaction_df['block_signed_at'].iloc[0]
        print(f"Transaction time: {transaction_time}")
        transaction_time, temp_moves, gas_fee_fiat = parse_onchain_transactions(chain, wallet, df, transaction_hash, currency)

        # you may not want to process now if the prices will be easier to find after processing future transactions
        # only ask if more than one of the tokens are not in the coingecko lookup dict and not in the previous prices dict
        if len([True for move in temp_moves if (move['token'].lower() not in COINGECKOID_LOOKUP.keys() and
                                                not retrieve_token_price(move['token'], move['token_contract'], transaction_time, verbose=False))]) > 1:
            process_now = input(f"Would you like to process this transaction now? If not, this transaction will be processed later. "
                                f"(Prices may be easier to determine after processing future transactions) (y/N) ")
            if process_now.lower() != 'y':
                transaction_hashes.append(transaction_hash)
                continue

        # attempt to classify and check with user
        class_int, in_count, out_count = classify_transaction(temp_moves, currency)

        # Use classification to add to transaction bank
        add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, chain, transaction_hash, currency)

        # mark transaction hash as processed
        processed_transaction_hashes.append(transaction_hash)

        # pickle progress so far
        filename = os.path.join(os.path.dirname(__file__), "results", "transactions", f"{pickle_file_name}.p")
        with open(filename, "wb") as pickle_file:
            pickle.dump((transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES), pickle_file)
        print(f"Progress saved to {filename}")


def parse_and_classify_binance_transaction(transaction, transaction_time, transaction_hash, currency='aud', silent_income=False):
    in_count = 0
    out_count = 0
    gas_fee_fiat = 0
    temp_moves = []
    class_int = 1
    for op, row, index in transaction:
        if op.lower() in ['pos savings interest', 'rewards distribution', 'savings interest']:
            temp_moves.append({'token': row['Coin'],
                               'token_contract': None,
                               'direction': 'in',
                               'quantity': row['Change']})
            in_count += 1
            class_int = 6
        elif op.lower() in ['fee', 'commission fee shared with you']:
            gas_fee_fiat += -1 * row['Change'] * get_token_price(row['Coin'], None, transaction_time, 'binance', transaction_hash, None, currency)
        elif row['Change'] > 0:
            temp_moves.append({'token': row['Coin'],
                               'token_contract': None,
                               'direction': 'in',
                               'quantity': row['Change']})
            in_count += 1
        elif row['Change'] < 0:
            temp_moves.append({'token': row['Coin'],
                               'token_contract': None,
                               'direction': 'out',
                               'quantity': -1 * row['Change']})
            out_count += 1
        else:
            raise Exception(f"Unsure how to handle binance csv row {row}")

    # if gas fee is negative, treat positive fees as income
    if gas_fee_fiat < 0:
        gas_fee_fiat = 0
        for op, row, index in transaction:
            if op.lower() in ['fee', 'commission fee shared with you'] and row['Change'] > 0:
                temp_moves.append({'token': row['Coin'],
                                   'token_contract': None,
                                   'direction': 'in',
                                   'quantity': row['Change']})
            elif op.lower() in ['fee', 'commission fee shared with you'] and row['Change'] < 0:
                gas_fee_fiat += -1 * row['Change'] * get_token_price(row['Coin'], None, transaction_time, 'binance', transaction_hash, None, currency)

    changes = 'y'
    while changes.lower() == 'y':
        print("Token movements: ")
        for n, move in enumerate(temp_moves):
            print(f"{n + 1}. {move}")
        if not (len([True for m in temp_moves if m['direction'] == 'in']) == 1 and len([True for m in temp_moves if m['direction'] == 'out']) == 0 and silent_income):
            changes = input("Would you like to make any changes? (y/N) ")
            if changes.lower() == 'y':
                print("Options: \n1. Remove a transaction \n2. Add a transaction")
                option = input(f"Select an option: (#/N) ")
                if option.strip() == '1':
                    remove = input("Which transaction would you like to remove? (#/N) ")
                    if remove in [str(m) for m in range(1, len(temp_moves)+1)]:
                        del temp_moves[int(remove)-1]
                elif option.strip() == '2':
                    ticker = input("Enter token ticker: ")
                    token_contract = input("Enter token contract address: ")
                    direction = get_user_input("Enter token movement direction: (in/out) ", 'direction')
                    quantity = get_user_input("Enter quantity: (#) ", 'float')
                    temp_moves.append({'token': ticker,
                                       'token_contract': token_contract,
                                       'direction': direction,
                                       'quantity': quantity})
        else:
            changes = 'n'
            break

    return temp_moves, gas_fee_fiat, class_int, in_count, out_count


def read_binance_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date, currency='aud'):
    """
    Reads in a csv file from binance and adds transactions to the transaction bank.
    :param transaction_bank: a dictionary mapping each token to a list of transactions
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: The updated transaction_bank dictionary
    """
    # read all files for a given chain into single data frame
    path = os.path.join('transaction-files', 'binance')
    all_files = glob.glob(path + "/*.csv")

    df_list = []

    for filename in all_files:
        df = pd.read_csv(filename, index_col=None, header=0)
        df_list.append(df)

    df = pd.concat(df_list, axis=0, ignore_index=True)
    df['UTC_Time'] = pd.to_datetime(df['UTC_Time'], format="%Y-%m-%d %H:%M:%S")
    transaction_list = []

    # iterate through each row and group all transactions that happened at the same time
    # this will make it possible to make the corresponding buy/sell transactions
    # binance CSVs only go down to the second, so we need to ensure that we are not putting multiple transactions together
    temp_transaction = []
    for index, row in df.iterrows():
        if start_date <= row['UTC_Time'] < end_date:
            # check whether we've had this time already - if not this is a new transaction
            if row['UTC_Time'] not in [r['UTC_Time'] for _, r, _ in temp_transaction] and len(temp_transaction) > 0:
                transaction_list.append(temp_transaction)
                temp_transaction = []

            # skip any that are not tax relevant
            if row['Operation'].lower() in ['deposit', 'withdraw', 'pos savings purchase', 'pos savings redemption', 'savings purchase', 'liquid swap add', 'savings principal redemption']:
                continue
            # if tax relevant, add to transaction
            elif row['Operation'].lower() in ['pos savings interest', 'rewards distribution', 'savings interest',
                                              'fee', 'transaction related', 'buy', 'sell',
                                              'commission fee shared with you']:
                temp_transaction.append((row['Operation'], row, index))
            else:
                raise Exception(f"Function read_binance_csv cannot handle the operation {row['Operation']}, code changes will need to be made to handle this.")
    else:
        transaction_list.append(temp_transaction)

    skip = input(f"Would you like to skip confirmation for income transactions? (y/N) ")
    if skip.lower() == 'y':
        silent_income = True
    else:
        silent_income = False

    for transaction in transaction_list:
        transaction_time = transaction[0][1]['UTC_Time']
        hash_string = str(transaction_time) + '-' + '-'.join([op+row['Coin']+str(row['Change']) for op, row, index in transaction])
        transaction_hash = hashlib.md5(hash_string.encode('utf-8')).hexdigest()

        if transaction_hash in processed_transaction_hashes:
            continue
        print("-------------------------------------------------------------------------------------------------")

        print(f"Transaction hash: {transaction_hash}")
        print(f"Transaction time: {transaction_time}")

        temp_moves, gas_fee_fiat, class_int, in_count, out_count = parse_and_classify_binance_transaction(transaction, transaction_time, transaction_hash, currency, silent_income)

        # Use classification to add to transaction bank
        add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, 'binance', transaction_hash, currency, silent_income)

        # mark transaction hash as processed
        processed_transaction_hashes.append(transaction_hash)

        # pickle progress so far
        filename = os.path.join(os.path.dirname(__file__), "results", "transactions", f"{pickle_file_name}.p")
        with open(filename, "wb") as pickle_file:
            pickle.dump((transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES), pickle_file)
        print(f"Progress saved to {filename}")


def parse_and_classify_btcmarkets_transaction(row):
    in_count = 1
    out_count = 1
    temp_moves = []
    class_int = 1

    if row['side'].lower() == 'bid':
        temp_moves.append({'token': row['instrument'],
                           'token_contract': None,
                           'direction': 'in',
                           'quantity': row['volume']})
        temp_moves.append({'token': row['currency'],
                           'token_contract': None,
                           'direction': 'out',
                           'quantity': row['price'] * row['volume']})
    elif row['side'].lower() == 'ask':
        temp_moves.append({'token': row['instrument'],
                           'token_contract': None,
                           'direction': 'out',
                           'quantity': row['volume']})
        temp_moves.append({'token': row['currency'],
                           'token_contract': None,
                           'direction': 'in',
                           'quantity': row['price'] * row['volume']})

    # get fee as gas fee
    gas_fee_fiat = int(row['feeInBaseCurrency(Inc tax)'])

    changes = 'y'
    while changes.lower() == 'y':
        print("Token movements: ")
        for n, move in enumerate(temp_moves):
            print(f"{n + 1}. {move}")
            changes = input("Would you like to make any changes? (y/N) ")
        if changes.lower() == 'y':
            print("Options: \n1. Remove a transaction \n2. Add a transaction")
            option = input(f"Select an option: (#/N) ")
            if option.strip() == '1':
                remove = input("Which transaction would you like to remove? (#/N) ")
                if remove in [str(m) for m in range(1, len(temp_moves)+1)]:
                    del temp_moves[int(remove)-1]
            elif option.strip() == '2':
                ticker = input("Enter token ticker: ")
                token_contract = input("Enter token contract address: ")
                direction = get_user_input("Enter token movement direction: (in/out) ", 'direction')
                quantity = get_user_input("Enter quantity: (#) ", 'float')
                temp_moves.append({'token': ticker,
                                   'token_contract': token_contract,
                                   'direction': direction,
                                   'quantity': quantity})

    return temp_moves, gas_fee_fiat, class_int, in_count, out_count


def read_btcmarkets_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date, currency='aud'):
    """
    Reads in a csv file from btcmarkets and adds transactions to the transaction bank.
    :param transaction_bank: a dictionary mapping each token to a list of transactions
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: The updated transaction_bank dictionary
    """
    # read all files for a given chain into single data frame
    path = os.path.join('transaction-files', 'btcmarkets')
    all_files = glob.glob(path + "/*.csv")

    df_list = []

    for filename in all_files:
        df = pd.read_csv(filename, index_col=None, header=0)
        df_list.append(df)

    df = pd.concat(df_list, axis=0, ignore_index=True)
    df.rename(columns=lambda x: x.strip(), inplace=True)
    df['creationTime'] = pd.to_datetime(df['creationTime'], format="%Y-%m-%dT%H:%M:%SZ")

    # Iterate through each row

    for index, row in df.iterrows():
        transaction_time = row['creationTime']
        transaction_hash = str(row['id']) + '-' + str(row['orderId'])

        if transaction_hash in processed_transaction_hashes:
            continue
        print("-------------------------------------------------------------------------------------------------")

        print(f"Transaction hash: {transaction_hash}")
        print(f"Transaction time: {transaction_time}")

        temp_moves, gas_fee_fiat, class_int, in_count, out_count = parse_and_classify_btcmarkets_transaction(row)

        # Use classification to add to transaction bank
        add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, 'btcmarkets', transaction_hash, currency)

        # mark transaction hash as processed
        processed_transaction_hashes.append(transaction_hash)

        # pickle progress so far
        filename = os.path.join(os.path.dirname(__file__), "results", "transactions", f"{pickle_file_name}.p")
        with open(filename, "wb") as pickle_file:
            pickle.dump((transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES), pickle_file)
        print(f"Progress saved to {filename}")


def parse_and_classify_coinspot_transaction(row, transaction_time, transaction_hash, currency='aud'):
    in_count = 1
    out_count = 1
    temp_moves = []
    class_int = 1

    first, second = row['Market'].split("/")

    if row['Type'].lower() == 'buy':
        temp_moves.append({'token': first,
                           'token_contract': None,
                           'direction': 'in',
                           'quantity': row['Amount']})
        temp_moves.append({'token': second,
                           'token_contract': None,
                           'direction': 'out',
                           'quantity': row['Amount'] * row['Rate ex. fee']})
    elif row['Type'].lower() == 'sell':
        temp_moves.append({'token': first,
                           'token_contract': None,
                           'direction': 'out',
                           'quantity': row['Amount']})
        temp_moves.append({'token': second,
                           'token_contract': None,
                           'direction': 'in',
                           'quantity': row['Amount'] * row['Rate ex. fee']})

    # get fee as gas fee
    gas_fee_fiat = float(row['Fee'].split()[0]) * get_token_price(row['Fee'].split()[1], None, transaction_time, 'binance', transaction_hash, None, currency)

    changes = 'y'
    while changes.lower() == 'y':
        print("Token movements: ")
        for n, move in enumerate(temp_moves):
            print(f"{n + 1}. {move}")
        changes = input("Would you like to make any changes? (y/N) ")
        if changes.lower() == 'y':
            print("Options: \n1. Remove a transaction \n2. Add a transaction")
            option = input(f"Select an option: (#/N) ")
            if option.strip() == '1':
                remove = input("Which transaction would you like to remove? (#/N) ")
                if remove in [str(m) for m in range(1, len(temp_moves)+1)]:
                    del temp_moves[int(remove)-1]
            elif option.strip() == '2':
                ticker = input("Enter token ticker: ")
                token_contract = input("Enter token contract address: ")
                direction = get_user_input("Enter token movement direction: (in/out) ", 'direction')
                quantity = get_user_input("Enter quantity: (#) ", 'float')
                temp_moves.append({'token': ticker,
                                   'token_contract': token_contract,
                                   'direction': direction,
                                   'quantity': quantity})

    return temp_moves, gas_fee_fiat, class_int, in_count, out_count


def read_coinspot_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date, currency='aud'):
    """
    Reads in a csv file from coinspot and adds transactions to the transaction bank.
    :param transaction_bank: a dictionary mapping each token to a list of transactions
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: The updated transaction_bank dictionary
    """
    # read all files for a given chain into single data frame
    path = os.path.join('transaction-files', 'coinspot')
    all_files = glob.glob(path + "/*.csv")

    df_list = []

    for filename in all_files:
        df = pd.read_csv(filename, index_col=None, header=0)
        df_list.append(df)

    df = pd.concat(df_list, axis=0, ignore_index=True)
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], format="%d/%m/%Y %I:%M %p")

    # Iterate through each row

    for index, row in df.iterrows():
        transaction_time = row['Transaction Date']
        hash_string = str(row['Transaction Date']) + '-' + row['Type'] + '-' + row['Market'] + '-' + str(['Amount'])
        transaction_hash = hashlib.md5(hash_string.encode('utf-8')).hexdigest()

        if transaction_hash in processed_transaction_hashes:
            continue
        print("-------------------------------------------------------------------------------------------------")

        print(f"Transaction hash: {transaction_hash}")
        print(f"Transaction time: {transaction_time}")

        temp_moves, gas_fee_fiat, class_int, in_count, out_count = parse_and_classify_coinspot_transaction(row, transaction_time, transaction_hash, currency)

        # Use classification to add to transaction bank
        add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, 'coinspot', transaction_hash, currency)

        # mark transaction hash as processed
        processed_transaction_hashes.append(transaction_hash)

        # pickle progress so far
        filename = os.path.join(os.path.dirname(__file__), "results", "transactions", f"{pickle_file_name}.p")
        with open(filename, "wb") as pickle_file:
            pickle.dump((transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES), pickle_file)
        print(f"Progress saved to {filename}")


def read_all_transactions():
    # set up pickling so we can save our progress as we go
    # look for existing files
    previous = input(f"Would you like to load in classifications from a previous session? (Y/n) ")
    if previous.lower() != "n":
        file_list = glob.glob(os.path.join(os.path.dirname(__file__), "results", "transactions", "*.p"))
        if file_list:
            print("Existing files:")
            for n, f in enumerate(file_list):
                print(f"{n+1}. {os.path.basename(f)}")
            while True:
                file_num = input(f"Which existing file would you like to load? (#/n) ")
                if file_num in [str(m) for m in range(1, len(file_list)+1)]:
                    with open(file_list[int(file_num)-1], "rb") as pickle_file:
                        global PREVIOUS_PRICES
                        (transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES) = pickle.load(pickle_file)
                    print(f"Loaded transaction hashes: {processed_transaction_hashes}")
                    pp = pprint.PrettyPrinter()
                    print("Loaded transactions:")
                    pp.pprint(transaction_bank)
                    print(f"Loaded previous prices:")
                    pp.pprint(PREVIOUS_PRICES)
                    break
                elif file_num.lower() == 'n':
                    print('No file selected, starting from scratch.')
                    transaction_bank = dict()
                    processed_transaction_hashes = []
                    break
        else:
            print("No existing files found, starting from scratch.")
            transaction_bank = dict()
            processed_transaction_hashes = []
    else:
        transaction_bank = dict()
        processed_transaction_hashes = []

    pickle_file_name = input(f"What would you like to call this session's save file? ")

    print("What time period would you like to process transactions for?")
    start_date = get_user_input(f"Enter the start date: (YYYY-MM-DD) ", 'date')
    start_tz = get_user_input(f"What timezone is this date in, as an offset from UTC? (eg. +10, -9 etc.) ", 'int')
    start_date -= datetime.timedelta(hours=start_tz)
    end_date = get_user_input(f"Enter the end date (inclusive): (YYYY-MM-DD) ", 'date')
    end_tz = get_user_input(f"What timezone is this date in, as an offset from UTC? (eg. +10, -9 etc.) ", 'int')
    end_date -= datetime.timedelta(hours=end_tz)
    end_date += datetime.timedelta(days=1)

    process = input(f"Would you like to process Binance transactions? (Y/n) ")
    if process.lower() != "n":
        read_binance_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date)

    process = input(f"Would you like to process BTCMarkets transactions? (Y/n) ")
    if process.lower() != "n":
        read_btcmarkets_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date)

    process = input(f"Would you like to process CoinSpot transactions? (Y/n) ")
    if process.lower() != "n":
        read_coinspot_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date)

    for chain in ['ethereum', 'bsc', 'polygon', 'fantom']:
        process = input(f"Would you like to process {chain} transactions? (Y/n) ")
        if process.lower() != "n":
            with open("wallets.yml") as file:
                wallets = yaml.load(file)
            for (name, wallet) in wallets.items():
                wallet_choice = input(f"Would you like to import transactions for wallet {wallet} ({name}) on {chain}? (Y/n) ")
                if wallet_choice.lower() != "n":
                    read_onchain_transactions(chain,
                                              wallet,
                                              transaction_bank,
                                              processed_transaction_hashes,
                                              pickle_file_name,
                                              start_date,
                                              end_date)


if __name__ == '__main__':
    read_all_transactions()
