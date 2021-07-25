import os
import pandas as pd

from enum import Enum, auto


class Transaction:
    """
    Contains the information about a single transaction (buy, sell or both).
    """
    def __init__(self, time, transaction_type, token, volume, fee):
        self.time = time
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
        if self.transaction_type == BUY:
            return self.token_price + self.fee
        elif self.transaction_type == SELL:
            return self.token_price - self.fee

    def get_token_price(self):
        # query the coingecko api here and extract the relevant data
        token_price = 0
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
    # TODO
    return transaction_bank
