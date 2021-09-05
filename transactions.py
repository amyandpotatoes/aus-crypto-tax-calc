# TODO: fix price of 0
# Estimated price is 1352.3663415203996
# {'time': Timestamp('2021-07-31 04:26:44'), 'transaction_type': <TransactionType.SELL: 2>, 'token': 'mooBIFI', 'volume': 0.7175910762107052, 'fee': 0.2395296114445323, 'token_price': 0.0, 'token_fee_adjusted_price': 0.2395296114445323}
# Adding above transaction...

import onchain_transactions

import os
import pandas as pd
import glob
import datetime
import requests
import warnings
import pickle
import glob
import yaml
import pprint
from enum import Enum, auto
from pycoingecko import CoinGeckoAPI
from io import StringIO

warnings.filterwarnings("ignore")

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
                   7: 'Outgoing Taxable',
                   8: 'Non-taxable'}

# customised token ticker to coingecko ID lookup dictionary
# used for when the main dictionary doesn't find the correct token, usually due to ticker collisions
CUSTOM_COINGECKOID_LOOKUP = dict()

# list of tickers not to confirm
TICKERS_NO_CONFIRM = []


def create_coingecko_id_lookup():
    """
    Create a dictionary that links token tickers to coingecko IDs.
    :return: lookup, that dictionary
    """
    cg = CoinGeckoAPI()
    coin_list = cg.get_coins_list()
    lookup = {}
    for coin in coin_list:
        lookup[coin['symbol'].lower()] = coin['id']
    return lookup


# create coingecko lookup table
COINGECKOID_LOOKUP = create_coingecko_id_lookup()


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

    # read_binance_csv(transaction_bank, start_date, end_date)

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
    class_correct = input(f"This looks like {class_guess}, is it? (Y/n): ")
    if class_correct.lower() == 'n':
        class_int = input("Which is the correct classification number? (#) ")
        class_int = int(class_int)
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


def get_token_price(token, token_contract_address, transaction_time, chain, currency='aud'):
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
    else:
        # convert token ticker to coingecko token ID
        if token.lower() in CUSTOM_COINGECKOID_LOOKUP.keys():
            token_id = CUSTOM_COINGECKOID_LOOKUP.get(token.lower())
        else:
            token_id = COINGECKOID_LOOKUP.get(token.lower())

        # convert the time to unix time
        epoch_time = int(transaction_time.timestamp())

        if token_id is not None:  # if token ID is found
            # check if correct token was found
            if token.lower() not in TICKERS_NO_CONFIRM:
                correct_token_id = input(f"\rIs {token_id} the correct token ID for {token.lower()}? (Y/n) ")
                if correct_token_id.lower() == 'n':
                    token_id = input(f"\rWhat is the correct coingecko token ID? (Search token in cg and use coin name in URL) ")
                    CUSTOM_COINGECKOID_LOOKUP[token.lower()] = token_id
                else:
                    again = input("Do you want to be asked this again for this ticker? (Y/n) ")
                    if again.lower() == 'n':
                        TICKERS_NO_CONFIRM.append(token.lower())

            # convert the time to unix time
            epoch_time = int(transaction_time.timestamp())
            twelve_hours = 12 * 60 * 60
            # query the api +- 12 hours around the time of transaction, then find the closest time
            from_timestamp = epoch_time - twelve_hours
            to_timestamp = epoch_time + twelve_hours

            # query the coingecko api here and extract the relevant data
            cg = CoinGeckoAPI()
            result = cg.get_coin_market_chart_range_by_id(
                id=token_id,
                vs_currency=currency,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp
            )

            # find the closest time to the time of transaction
            token_price = None  # just in case the is an error
            min_time_difference = float('inf')
            for time, price in result['prices']:
                time_difference = abs(epoch_time - time)
                if time_difference < min_time_difference:
                    min_time_difference = time_difference
                    token_price = price
        else:  # if token ID is not found
            print(f"Token price for {token} was not found using CoinGecko API, estimating from preceding transactions")

            # get latest block before provided time
            api_key = onchain_transactions.get_api_keys()['bsc']
            block = int(requests.get(f"https://api.bscscan.com/api?module=block&action=getblocknobytime&timestamp={epoch_time}&closest=before&apikey={api_key}").json()['result'])

            # get transactions prior to block above
            result = requests.get(f"https://api.bscscan.com/api?module=account&action=txlist&address={token_contract_address}&startblock=1&endblock={block}&sort=desc&apikey={api_key}").json()['result']

            # get transaction hashes
            transaction_hashes = [transaction['hash'] for transaction in result]

            # # pull all most recent 20 transactions involving this token
            # data_text = onchain_transactions.get_transactions(CHAIN_IDS[chain], token_contract_address)
            #
            # # filter transaction data to only get necessary lines
            # df = onchain_transactions.filter_transactions(data_text)
            #
            # # get unique transaction hashes
            # transaction_hashes = df['tx_hash'].unique()

            # iterate through transaction hashes until 20 appropriate transactions are found and add values to lists
            price_estimates = []
            printProgressBar(0, 20, prefix='Progress:', suffix='Complete', length=20)
            progress = 0
            for ind, transaction_hash in enumerate(transaction_hashes):
                # break once you have 20 transactions
                if len(price_estimates) >= 20:
                    break

                # read information about transaction into df
                data_text = onchain_transactions.get_transaction_by_hash(CHAIN_IDS[chain], transaction_hash)
                df = pd.read_csv(StringIO(data_text), dtype=str)

                # parse times
                df['block_signed_at'] = pd.to_datetime(df['block_signed_at'], format="%Y-%m-%dT%H:%M:%SZ")

                if len(df.index) == 0 or 'log_events_decoded_signature' not in df.columns:
                    continue

                # get token transfers associated with hash
                transaction_df = df[(df['tx_hash'] == transaction_hash)
                                    & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]

                if len(transaction_df.index) == 0:
                    continue

                # get wallet that triggered transaction
                wallet = transaction_df['from_address'].iloc[0]

                # parse transactions into 'moves'
                transaction_time, moves, gas_fee_fiat = parse_onchain_transactions(chain, wallet, transaction_df, transaction_hash, currency)

                # get moves in each direction
                in_moves = [move for move in moves if move['direction'] == 'in']
                out_moves = [move for move in moves if move['direction'] == 'out']

                # only keep going if:
                # all tokens are in coingeckoid_lookup, this prevents this code from looping
                # AND there is one incoming and one outgoing token, for simplicity
                # AND one of those tokens is the token in question
                if (not all([(move['token'].lower() in COINGECKOID_LOOKUP.keys() or move['token'] == token) for move in moves])
                        or not (len(in_moves) == 1 and len(out_moves) == 1)
                        or not any([move['token'] == token for move in moves])):
                    continue

                # if token is incoming, get value of outoging token
                if any([move['token'] == token for move in in_moves]):
                    # get value of opposite token, and use this to calculate price per token
                    _, _, _, out_values, _, _ = get_moves_and_values_by_direction_excluding(out_moves, transaction_time, chain, currency)
                    price_1token = sum(out_values) / in_moves[0]['quantity']
                    price_estimates.append(price_1token)
                    progress += 1
                    printProgressBar(progress, 20, prefix='Progress:', suffix='Complete', length=20)

                # if token is outgoing, get value of incoming token
                elif any([move['token'] == token for move in out_moves]):
                    # get value of opposite token, and use this to calculate price per token
                    _, _, in_values, _, _, _ = get_moves_and_values_by_direction_excluding(in_moves, transaction_time, chain, currency)
                    price_1token = sum(in_values) / out_moves[0]['quantity']
                    price_estimates.append(price_1token)
                    progress += 1
                    printProgressBar(progress, 20, prefix='Progress:', suffix='Complete', length=20)

            print("")
            if len(price_estimates) < 20:
                print('Could not find enough transactions to get a price estimate...')
                token_price = input(f'Enter price per token at {transaction_time} in {currency}manually')
            else:
                # get average of middle 10 price estimates
                price_estimates.sort()
                print(f"10 price estimates to average: {price_estimates[6:16]}")
                average_price = sum(price_estimates[6:16]) / 10
                print(f"Estimated price is {average_price}")
                token_price = average_price

        return token_price


def get_moves_and_values_by_direction(moves, transaction_time, chain, currency='aud'):
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
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, currency)
        price_total = price_1token * move['quantity']
        in_values.append(price_total)

    for move in out_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, currency)
        price_total = price_1token * move['quantity']
        out_values.append(price_total)

    # calculate proportional values, so that if there are multiple ingoing tokens you can work out how much of the outgoing value each is 'swapped for'
    in_prop = [val / sum(in_values) for val in in_values]
    out_prop = [val / sum(out_values) for val in out_values]

    return in_moves, out_moves, in_values, out_values, in_prop, out_prop


def get_moves_and_values_by_direction_excluding(moves, transaction_time, chain, exclude, currency='aud'):
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
    in_moves = [move for move in moves if move['direction'] == 'in']
    out_moves = [move for move in moves if move['direction'] == 'out']

    # calculate values
    in_values = []
    out_values = []
    for move in in_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, currency)
        price_total = price_1token * move['quantity']
        in_values.append(price_total)

    for move in out_moves:
        price_1token = get_token_price(move['token'], move['token_contract'], transaction_time, chain, currency)
        price_total = price_1token * move['quantity']
        out_values.append(price_total)

    # calculate proportional values, so that if there are multiple ingoing tokens you can work out how much of the outgoing value each is 'swapped for'
    in_prop = [val / sum(in_values) for val in in_values]
    out_prop = [val / sum(out_values) for val in out_values]

    return in_moves, out_moves, in_values, out_values, in_prop, out_prop


def add_transactions_w_opposite(transaction_bank, self_moves, self_props, self_count, opp_values, opp_count, gas_fee_fiat, transaction_time, transaction_type):
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
    for move, prop in zip(self_moves, self_props):
        raw_price_1token = sum(opp_values) * prop / move['quantity']
        price_inc_fee_1token = (sum(opp_values) * prop + (gas_fee_fiat / (self_count + opp_count))) / move['quantity']
        temp_transaction = Transaction(transaction_time, transaction_type, move['token'], move['quantity'], (gas_fee_fiat / (self_count + opp_count)), raw_price_1token,
                                       price_inc_fee_1token)
        print(temp_transaction)
        _ = input('Adding above transaction...')
        if move['token'] in transaction_bank:
            transaction_bank[move['token']].append(temp_transaction)
        else:
            transaction_bank[move['token']] = [temp_transaction]


def add_transactions_no_opposite(transaction_bank, self_moves, self_count, self_values, gas_fee_fiat, transaction_time, transaction_type, taxable_prop):
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
        _ = input('Adding above transaction...')
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
    print("Token movements: ")
    for move in temp_moves:
        print(move)

    in_count = len([True for move in temp_moves if move['direction'] == 'in'])
    out_count = len([True for move in temp_moves if move['direction'] == 'out'])

    # classifications = {1: 'Buy + Sell',
    #                    2: 'Buy',
    #                    3: 'Sell',
    #                    4: 'Staking',
    #                    5: 'Unstaking + Income',
    #                    6: 'Income',
    #                    7: 'Outgoing Taxable',
    #                    8: 'Non-taxable'}

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
            class_int = 5
    elif in_count == 0 and out_count == 0:
        class_guess = 'Non-taxable'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 8
    else:
        class_guess = 'Non-taxable'
        class_int = correct_transaction_classification(class_guess)
        if not class_int:
            class_int = 8

    return class_int, in_count, out_count


def add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, chain, currency):
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
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, currency)
        # add transactions with incoming tokens (buys)
        add_transactions_w_opposite(transaction_bank, in_moves, in_prop, in_count, out_values, out_count, gas_fee_fiat, transaction_time, TransactionType.BUY)
        # then add transactions with outgoing tokens (sells)
        add_transactions_w_opposite(transaction_bank, out_moves, out_prop, out_count, in_values, in_count, gas_fee_fiat, transaction_time, TransactionType.SELL)
    elif class_int == 2:  # Buy
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, currency)
        # add transactions with incoming tokens (buys)
        add_transactions_w_opposite(transaction_bank, in_moves, in_prop, in_count, out_values, out_count, gas_fee_fiat, transaction_time, TransactionType.BUY)
    elif class_int == 3:  # Sell
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, currency)
        # then add transactions with outgoing tokens (sells)
        add_transactions_w_opposite(transaction_bank, out_moves, out_prop, out_count, in_values, in_count, gas_fee_fiat, transaction_time, TransactionType.SELL)
    elif class_int == 5:  # Unstaking + Income
        for move in temp_moves:
            print(f"Token: {move}")
            income = input("Are some of these tokens income (tokens that you did not stake)? (y/N) ")
            if income.lower() == "y":
                all_income = input("Are ALL of these tokens income? (Y/n) ")
                if all_income.lower() == "n":
                    income_amount = int(input("How many units are income?"))
                    income_prop = income_amount / move['quantity']
                    # get values of tokens, used to calculate buy and sell cost bases/prices
                    in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction([move], transaction_time, chain, currency)
                    # add transactions
                    add_transactions_no_opposite(transaction_bank, in_moves, in_count, in_values, gas_fee_fiat, transaction_time, TransactionType.GAIN, income_prop)
                else:
                    # get values of tokens, used to calculate buy and sell cost bases/prices
                    in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction([move], transaction_time, chain, currency)
                    # add transactions
                    add_transactions_no_opposite(transaction_bank, in_moves, in_count, in_values, gas_fee_fiat, transaction_time, TransactionType.GAIN, 1)
            else:
                continue

    elif class_int == 6:  # income
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, currency)
        # add transactions with incoming tokens (income)
        add_transactions_no_opposite(transaction_bank, in_moves, in_count, in_values, gas_fee_fiat, transaction_time, TransactionType.GAIN, 1)
    elif class_int == 7:  # outgoing taxable
        # get values of tokens, used to calculate buy and sell cost bases/prices
        _, out_moves, _, out_values, _, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, chain, currency)
        # add transactions with incoming tokens (income)
        add_transactions_no_opposite(transaction_bank, out_moves, out_count, out_values, gas_fee_fiat, transaction_time, TransactionType.LOSS, 1)
    elif class_int in [4, 8]:
        _ = input('No taxable transactions...')


def parse_onchain_transactions(chain, wallet, df, transaction_hash, currency='aud'):
    # setup object to store intermediate information about ingoing and outgoing tokens
    temp_moves = []

    # get token transfers associated with hash
    transaction_df = df[(df['tx_hash'] == transaction_hash)
                        & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]
    transaction_time = df['block_signed_at'].iloc[0]
    pd.set_option('display.max_columns', None)
    transaction_df['gas_spent'] = pd.to_numeric(transaction_df['gas_spent'], errors='coerce')
    transaction_df['gas_price'] = pd.to_numeric(transaction_df['gas_price'], errors='coerce')

    # get gas fee from transaction
    gas_fee_native_token = max(transaction_df['gas_spent'] * transaction_df['gas_price'] / 1e18)
    gas_fee_fiat = gas_fee_native_token * get_token_price(NATIVE_TOKEN[chain], None, transaction_time, chain, currency)
    # print(f"Gas fee: {gas_fee_native_token} {NATIVE_TOKEN[chain]} = {gas_fee_fiat} {currency.upper()}")

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
    api_key = onchain_transactions.get_api_keys()['bsc']
    response = requests.get(f"https://api.bscscan.com/api?module=account&action=txlistinternal&txhash={transaction_hash}&apikey={api_key}")

    result = response.json()['result']
    # print(f"Internal transactions: {result}")

    # use temporary dictionary to store information about transaction until more information can be gained so it can be added to transaction bank
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
    df = df[(df['block_signed_at'] >= start_date) & (df['block_signed_at'] <= end_date)]

    # get unique transaction hashes, removing those that have been previously processed
    transaction_hashes = df['tx_hash'].unique()

    # iterate through transaction hashes, parsing them and adding transactions to transaction bank
    for transaction_hash in transaction_hashes:
        if transaction_hash in processed_transaction_hashes:
            print(f"Skipping transaction {transaction_hash} as it has already been processed...")
            continue
        # parse transaction token movements into a dictionary 'temp_moves'
        print("-------------------------------------------------------------------------------------------------")
        print(f"Transaction hash: {transaction_hash}")
        transaction_time = df['block_signed_at'].iloc[0]
        print(f"Time: {transaction_time}")
        transaction_time, temp_moves, gas_fee_fiat = parse_onchain_transactions(chain, wallet, df, transaction_hash, currency)

        # attempt to classify and check with user
        class_int, in_count, out_count = classify_transaction(temp_moves, currency)

        # Use classification to add to transaction bank
        add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, chain, currency)

        # mark transaction hash as processed
        processed_transaction_hashes.append(transaction_hash)

        # pickle progress so far
        filename = os.path.join(os.path.dirname(__file__), "saved-files", f"{pickle_file_name}.p")
        with open(filename, "wb") as pickle_file:
            pickle.dump((transaction_bank, processed_transaction_hashes), pickle_file)


def read_binance_csv(transaction_bank, processed_transaction_hashes, pickle_file_name, start_date, end_date):
    """
    Reads in a csv file from binance and adds transactions to the transaction bank.
    :param transaction_bank: a dictionary mapping each token to a list of transactions
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: The updated transaction_bank dictionary
    """
    # read the csvs into a data frame
    project_dir = os.path.dirname('__file__')
    binance_dir = os.path.join(project_dir, 'transaction-files', 'binance')
    full_df = pd.DataFrame()
    for file in os.listdir(binance_dir):
        df = pd.read_csv(file)
        full_df.append(df)

    # iterate through each row and group all transactions that happened at the same time
    # this will make it possible to make the corresponding buy/sell transactions

    # TODO: parse binance transactions and add to transaction bank
    # base this off the on-chain read function, many of the helper functions can be reused


def read_all_transactions():
    # set up pickling so we can save our progress as we go
    # look for existing files
    previous = input(f"Would you like to load in classifications from a previous session? (Y/n) ")
    if previous.lower() != "n":
        file_list = glob.glob(os.path.join(os.path.dirname(__file__), "saved-files", "*.p"))
        if file_list:
            print("Existing files:")
            for n, f in enumerate(file_list):
                print(f"{n+1}. {os.path.basename(f)}")
            while True:
                file_num = input(f"Which existing file would you like to load? (#/N) ")
                if file_num in [str(m) for m in range(1, len(file_list)+1)]:
                    with open(file_list[int(file_num)-1], "rb") as pickle_file:
                        (transaction_bank, processed_transaction_hashes) = pickle.load(pickle_file)
                    print(f"Loaded transaction hashes: {processed_transaction_hashes}")
                    pp = pprint.PrettyPrinter()
                    print("Loaded transactions:")
                    pp.pprint(transaction_bank)
                    break


        else:
            print("No existing files found, starting from scratch.")
            transaction_bank = dict()
            processed_transaction_hashes = []
    else:
        transaction_bank = dict()
        processed_transaction_hashes = []

    pickle_file_name = input(f"What would you like to call this session's save file? ")

    start_date = datetime.datetime.strptime(input(f"Enter the start date: (YYYY-MM-DD) "), "%Y-%m-%d")
    end_date = datetime.datetime.strptime(input(f"Enter the end date: (YYYY-MM-DD) "), "%Y-%m-%d")

    process_bsc = input(f"Would you like to process Binance Smart Chain transactions? (Y/n) ")
    if process_bsc.lower() != "n":
        with open("wallets.yml") as file:
            wallets = yaml.load(file)
        for (name, wallet) in wallets.items():
            wallet_bsc = input(f"Would you like to process transactions for wallet {wallet} ({name}) on BSC? (Y/n) ")
            if wallet_bsc.lower() != "n":
                read_onchain_transactions('bsc',
                                          '0xc3eBf192E1AfF802217a08Fd6b2eeDbBD4D87334',
                                          transaction_bank,
                                          processed_transaction_hashes,
                                          pickle_file_name,
                                          start_date,
                                          end_date)

if __name__ == '__main__':
    read_all_transactions()
