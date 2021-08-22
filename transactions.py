import os
import pandas as pd
import glob
import datetime
import requests

from enum import Enum, auto

from pycoingecko import CoinGeckoAPI

# DEFINE GLOBALS

# conversion table for going from chain name to native token
NATIVE_TOKEN = {'ethereum': 'ETH', 'polygon': 'MATIC', 'bsc': 'BNB', 'fantom': 'FTM'}

# classifications for transactions
CLASSIFICATIONS = {1: 'Buy + Sell',
                   2: 'Buy',
                   3: 'Sell',
                   4: 'Staking',
                   5: 'Unstaking + Income',
                   6: 'Income',
                   7: 'Outgoing Taxable',
                   8: 'Non-taxable'}


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
        self.time =  time # datetime objet
        # type is a TransactionType: can be buy, sell, gain or loss
        self.transaction_type = transaction_type
        self.token = token
        self.volume = volume
        # fee per token
        self.fee = fee / self.volume
        # token_price is the price for a single token at that time from coingecko
        self.token_price = token_price
        self.token_fee_adjusted_price = token_fee_adjusted_price


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
    for i in range(1, len(CLASSIFICATIONS) + 1):
        print(f"{i}. {CLASSIFICATIONS[i]}")
    class_int = input(f"This looks like {class_guess}, press enter for yes, or enter the correct number:")
    if class_int:
        class_int = int(class_int)
    return class_int


def get_token_price(token, transaction_time, currency='aud'):
    """
    Get the price of a token, using either the coingecko API or if that's not available, an average of recent
    transactions (with removal of outliers).
    :param token: token ticker
    :param transaction_time: the time that the transaction occurred, a datetime object
    :param currency: a string, the currency used (usually 'aud')
    :return: token_price, a float representing the price of a single token
    """
    if token.lower() == currency.lower():
        return 1
    else:
        # convert token ticker to coingecko token ID
        token_id = COINGECKOID_LOOKUP[token.lower()]
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

        return token_price


def get_moves_and_values_by_direction(moves, transaction_time, currency='aud'):
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
        price_1token = get_token_price(move['token'], transaction_time, currency)
        price_total = price_1token * move['quantity']
        in_values.append(price_total)

    for move in out_moves:
        price_1token = get_token_price(move['token'], transaction_time, currency)
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
        print(vars(temp_transaction))
        _ = input('Adding above transaction...')
        if move['token'] in transaction_bank:
            transaction_bank[move['token']].append(temp_transaction)
        else:
            transaction_bank[move['token']] = [temp_transaction]


def add_transactions_no_opposite(transaction_bank, self_moves, self_count, gas_fee_fiat, transaction_time, transaction_type, taxable_prop):
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
    for move in self_moves:
        raw_price_1token = move['value'] / move['quantity']
        price_inc_fee_1token = (move['value'] * taxable_prop + (gas_fee_fiat / self_count)) / (move['quantity'] * taxable_prop)
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
    print(temp_moves)

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


def add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, currency):
    """
    Gets the fiat values of the tokens in the transaction and adds transaction to transaction bank, using on the
    transaction classification provided in class_int to determine that TransactionType and other details.
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
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, currency)
        # add transactions with incoming tokens (buys)
        add_transactions_w_opposite(transaction_bank, in_moves, in_prop, in_count, out_values, out_count, gas_fee_fiat, transaction_time, TransactionType.BUY)
        # then add transactions with outgoing tokens (sells)
        add_transactions_w_opposite(transaction_bank, out_moves, out_prop, out_count, in_values, in_count, gas_fee_fiat, transaction_time, TransactionType.SELL)
    elif class_int == 2:  # Buy
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, currency)
        # add transactions with incoming tokens (buys)
        add_transactions_w_opposite(transaction_bank, in_moves, in_prop, in_count, out_values, out_count, gas_fee_fiat, transaction_time, TransactionType.BUY)
    elif class_int == 3:  # Sell
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, out_moves, in_values, out_values, in_prop, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, currency)
        # then add transactions with outgoing tokens (sells)
        add_transactions_w_opposite(transaction_bank, out_moves, out_prop, out_count, in_values, in_count, gas_fee_fiat, transaction_time, TransactionType.SELL)
    elif class_int == 5:  # Unstaking + Income
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction(temp_moves, transaction_time, currency)
        # work out which tokens are unstaking (you already owned them) and which are income
        print("-------------------------------------------------------------------------------------------------")
        for move, value in zip(in_moves, in_values):
            print(f"Token: {move}")
            income = input("Are some of these tokens income (tokens that you did not stake)? (y/n)")
            if income.lower() == "y":
                all_income = input("Are all of these tokens income? (y/n)")
                if all_income.lower() == "n":
                    income_amount = int(input("How many units are income?"))
                    income_prop = income_amount / move['quantity']
                    add_transactions_no_opposite(transaction_bank, [move], in_count, gas_fee_fiat, transaction_time, TransactionType.GAIN, income_prop)
                else:
                    add_transactions_no_opposite(transaction_bank, [move], in_count, gas_fee_fiat, transaction_time, TransactionType.GAIN, 1)
            else:
                continue
    elif class_int == 6:  # income
        # get values of tokens, used to calculate buy and sell cost bases/prices
        in_moves, _, in_values, _, in_prop, _ = get_moves_and_values_by_direction(temp_moves, transaction_time, currency)
        # add transactions with incoming tokens (income)
        add_transactions_no_opposite(transaction_bank, in_moves, in_count, gas_fee_fiat, transaction_time, TransactionType.GAIN, 1)
    elif class_int == 7:  # outgoing taxable
        # get values of tokens, used to calculate buy and sell cost bases/prices
        _, out_moves, _, out_values, _, out_prop = get_moves_and_values_by_direction(temp_moves, transaction_time, currency)
        # add transactions with incoming tokens (income)
        add_transactions_no_opposite(transaction_bank, out_moves, out_count, gas_fee_fiat, transaction_time, TransactionType.LOSS, 1)
    elif class_int in [4, 8]:
        _ = input('No taxable transactions...')


def read_onchain_transactions(chain, wallet, transaction_bank, start_date, end_date, currency='aud'):
    """
    Reads in transaction data from an etherscan-based blockchain scanning website and adds transactions to the
    transaction bank.
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

    # get unique transaction hashes
    transaction_hashes = df['tx_hash'].unique()

    # iterate through transaction hashes, parsing them and adding transactions to transaction bank
    for transaction_hash in transaction_hashes:
        # setup object to store intermediate information about ingoing and outgoing tokens
        temp_moves = []

        # get token transfers associated with hash
        transaction_df = df[(df['tx_hash'] == transaction_hash)
                            & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]
        print(f"Transaction hash: {transaction_hash}")
        transaction_time = df['block_signed_at'][0]
        print(f"Time: {transaction_time}")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 500)
        print(f"Token transactions: \n {transaction_df[['from_address', 'to_address', 'log_events_sender_name', 'log_events_sender_contract_ticker_symbol', 'log_events_decoded_signature', 'log_events_decoded_params_name', 'log_events_decoded_params_value']]}")
        pd.reset_option('display.max_rows|display.max_columns|display.width')

        # get gas fee from transaction
        gas_fee_native_token = max(transaction_df['gas_spent'] * transaction_df['gas_price'] / 1e18)
        gas_fee_fiat = gas_fee_native_token * get_token_price(NATIVE_TOKEN[chain], transaction_time, currency)
        print(f"Gas fee: {gas_fee_native_token} {NATIVE_TOKEN[chain]} = {gas_fee_fiat} {currency.upper()}")

        # get incoming tokens from token transfers
        in_mask = (transaction_df['log_events_decoded_signature'] == 'Transfer(indexed address from, indexed address to, uint256 value)')\
                  & (transaction_df['log_events_decoded_params_name'] == 'to')\
                  & (transaction_df['log_events_decoded_params_value'] == wallet.lower())
        in_indicies = transaction_df.index[in_mask]

        # for each incoming token, get details
        for ind in in_indicies:
            temp_moves.append({'token': transaction_df['log_events_sender_contract_ticker_symbol'][ind],
                               'direction': 'in',
                               'quantity': int(transaction_df['log_events_decoded_params_value'][ind+1]) / 1e18})

        # get outgoing tokens from token transfers
        out_mask = (transaction_df['log_events_decoded_signature'] == 'Transfer(indexed address from, indexed address to, uint256 value)') \
                  & (transaction_df['log_events_decoded_params_name'] == 'from') \
                  & (transaction_df['log_events_decoded_params_value'] == wallet.lower())
        out_indicies = transaction_df.index[out_mask]

        # for each outgoing token, get details
        for ind in out_indicies:
            temp_moves.append({'token': transaction_df['log_events_sender_contract_ticker_symbol'][ind],
                               'direction': 'out',
                               'quantity': int(transaction_df['log_events_decoded_params_value'][ind + 2]) / 1e18})

        # get internal transactions related to hash
        response = requests.get(f"https://api.bscscan.com/api?module=account&action=txlistinternal&txhash={transaction_hash}&apikey=5PXUSYGCJ73QPUWP13BXXMNMQMSKITX2ZC")

        result = response.json()['result']
        print(f"Internal transactions: {result}")

        # use temporary dictionary to store information about transaction until more information can be gained so it can be added to transaction bank
        for internal_transaction in result:
            # get incoming tokens from internal transactions
            if internal_transaction['to'].lower() == wallet.lower():
                temp_moves.append({'token': NATIVE_TOKEN[chain], 'direction': 'in', 'quantity': int(internal_transaction['value']) / 1e18})

            # get outgoing tokens from internal transfers
            if internal_transaction['from'].lower() == wallet.lower():
                temp_moves.append({'token': NATIVE_TOKEN[chain], 'direction': 'out', 'quantity': int(internal_transaction['value']) / 1e18})

        # attempt to classify and check with user
        class_int, in_count, out_count = classify_transaction(temp_moves, currency)

        # Use classification to add to transaction bank
        add_transaction_to_transaction_bank(class_int, transaction_bank, temp_moves, in_count, out_count, gas_fee_fiat, transaction_time, currency)


def read_binance_csv(transaction_bank, start_date, end_date):
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


if __name__ == '__main__':
    read_onchain_transactions('bsc',
                              '0xc3eBf192E1AfF802217a08Fd6b2eeDbBD4D87334',
                              dict(),
                              datetime.datetime(2020, 5, 17),
                              datetime.datetime.now())
