import os
import pandas as pd
import glob
import datetime
import requests

from enum import Enum, auto

from pycoingecko import CoinGeckoAPI


class Transaction:
    """
    Contains the information about a single transaction (buy, sell or both).
    """
    def __init__(self, time, transaction_type, token, volume, fee):
        self.time =  time # datetime objet
        # type is a TransactionType: can be buy, sell, gain or loss
        self.transaction_type = transaction_type
        self.token = token
        self.volume = volume
        # fee per token
        self.fee = fee / self.volume
        # token_price is the price for a single token at that time from coingecko
        self.token_price = self.get_token_price()
        self.adjusted_price_per_token = self.get_fee_adjusted_price()

    def get_fee_adjusted_price(self):
        if self.transaction_type == TransactionType.BUY:
            return self.token_price + self.fee
        elif self.transaction_type == TransactionType.SELL:
            return self.token_price - self.fee
        elif self.transaction_type == TransactionType.GAIN:
            return self.token_price
        elif self.transaction_type == TransactionType.LOSS:
            return 0

    def get_token_price(self, currency='aud'):
        # convert the time to unix time
        epoch_time = int(self.time.timestamp())
        twelve_hours = 12 * 60 * 60
        # query the api +- 12 hours around the time of transaction, then find the closest time
        from_timestamp = epoch_time - twelve_hours
        to_timestamp = epoch_time + twelve_hours

        # query the coingecko api here and extract the relevant data
        cg = CoinGeckoAPI()
        result = cg.get_coin_market_chart_range_by_id(
            id=self.token,
            vs_currency=currency,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp
        )
        # find the closest time to the time of transaction
        token_price = None # just in case the is an error
        min_time_difference = float('inf')
        for time, price in result['prices']:
            time_difference = abs(epoch_time - time)
            if  time_difference < min_time_difference:
                min_time_difference = time_difference
                token_price = price
        
        return token_price


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
        full_csv.append(df)

    # iterate through each row and group all transactions that happened at the same time
    # this will make it possible to make the corresponding buy/sell transactions
    
    
    # make the transactions for each group
    # need to figure out how much the tokens are worth here too


    return transaction_bank


def read_onchain_config():
    """
    Read in a config files that states which blockchains to pull records from, their scanning website and the wallet
    address(es) to use.
    :return: A dictionary of configurations
    """
    # not sure if this is needed anymore??
    config = dict()
    return config


def read_onchain_transactions(chain, wallet, transaction_bank, start_date, end_date):
    """
    Reads in transaction data from an etherscan-based blockchain scanning website and adds transactions to the
    transaction bank.
    :param chain: string of scanning website domain
    :param wallet: string of wallet address
    :param transaction_bank: a dictionary mapping a token to a list of transactions
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: The updated transaction_bank dictionary, mapping tokens to a list of transactions
    """
    # conversion table for going from chain name to native token
    native_token = {'ethereum': 'ETH', 'polygon': 'MATIC', 'bsc': 'BNB', 'fantom': 'FTM'}

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

    # iterate through transaction hashes, adding transactions to transaction bank
    for transaction_hash in transaction_hashes:
        # setup object to store intermediate information about ingoing and outgoing tokens
        temp_moves = []

        # get token transfers associated with hash
        transaction_df = df[(df['tx_hash'] == transaction_hash)
                            & (df["log_events_decoded_signature"] == "Transfer(indexed address from, indexed address to, uint256 value)")]
        print(transaction_hash)
        print(df['block_signed_at'][0])
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 500)
        print(transaction_df[['from_address',
                              'to_address',
                              'log_events_sender_name',
                              'log_events_sender_contract_ticker_symbol',
                              'log_events_decoded_signature',
                              'log_events_decoded_params_name',
                              'log_events_decoded_params_value']])
        pd.reset_option('display.max_rows|display.max_columns|display.width')

        # get incoming tokens from token transfers
        in_mask = (transaction_df['log_events_decoded_signature'] == 'Transfer(indexed address from, indexed address to, uint256 value)')\
                  & (transaction_df['log_events_decoded_params_name'] == 'to')\
                  & (transaction_df['log_events_decoded_params_value'] == wallet.lower())
        in_indicies = transaction_df.index[in_mask]

        # for each incoming token, get details
        for ind in in_indicies:

            print(int(transaction_df['log_events_decoded_params_value'][ind+1]) / 1000000000000000000)
            temp_moves.append({'token': transaction_df['log_events_sender_contract_ticker_symbol'][ind],
                               'direction': 'in',
                               'quantity': int(transaction_df['log_events_decoded_params_value'][ind+1]) / 1000000000000000000})

        # get outgoing tokens from token transfers
        out_mask = (transaction_df['log_events_decoded_signature'] == 'Transfer(indexed address from, indexed address to, uint256 value)') \
                  & (transaction_df['log_events_decoded_params_name'] == 'from') \
                  & (transaction_df['log_events_decoded_params_value'] == wallet.lower())
        out_indicies = transaction_df.index[out_mask]

        # for each outgoing token, get details
        for ind in out_indicies:
            temp_moves.append({'token': transaction_df['log_events_sender_contract_ticker_symbol'][ind],
                               'direction': 'out',
                               'quantity': int(transaction_df['log_events_decoded_params_value'][ind + 2]) / 1000000000000000000})

        # get internal transactions related to hash
        response = requests.get(f"https://api.bscscan.com/api?module=account&action=txlistinternal&txhash={transaction_hash}&apikey=5PXUSYGCJ73QPUWP13BXXMNMQMSKITX2ZC")

        result = response.json()['result']
        print(result)

        for internal_transaction in result:
            # get incoming tokens from internal transactions
            if internal_transaction['to'].lower() == wallet.lower():
                temp_moves.append({'token': native_token[chain], 'direction': 'in', 'quantity': int(internal_transaction['value']) / 1000000000000000000})

            # get outgoing tokens from internal transfers
            if internal_transaction['from'].lower() == wallet.lower():
                temp_moves.append({'token': native_token[chain], 'direction': 'out', 'quantity': int(internal_transaction['value']) / 1000000000000000000})

        print(temp_moves)

        hello = input("Next: ")

        # work out transaction type

        # add to transaction bank

    return transaction_bank


if __name__ == '__main__':
    read_onchain_transactions('bsc',
                              '0xc3eBf192E1AfF802217a08Fd6b2eeDbBD4D87334',
                              dict(),
                              datetime.datetime(2020, 5, 17),
                              datetime.datetime.now())
