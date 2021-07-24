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
        self.fee = fee
        self.raw_price = self.get_token_raw_price()
        self.adjusted_price = self.get_fee_adjusted_price()

    def get_fee_adjusted_price(self):
        # TODO
        adjusted_price = 0
        return adjusted_price

    def get_token_raw_price(self):
        # TODO
        raw_price = 0
        return raw_price


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
    # TODO
    transaction_bank = dict()
    return transaction_bank


def read_binance_csv(transaction_bank, start_date, end_date):
    """
    Reads in a csv file from binance and adds transactions to the transaction bank.
    :param transaction_bank: a dictionary of transactions for each token
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: transaction_bank
    """
    # TODO
    return transaction_bank


def read_onchain_config():
    """
    Read in a config files that states which blockchains to pull records from, their scanning website and the wallet
    address(es) to use.
    :return: config, a dictionary of configurations
    """
    # TODO
    config = dict()
    return config


def read_onchain_transactions(chain, wallet, transaction_bank, start_date, end_date):
    """
    Reads in transaction data from an etherscan-based blockchain scanning website and adds transactions to the
    transaction bank.
    :param chain: string of scanning website domain
    :param wallet: string of wallet address
    :param transaction_bank: a dictionary of transactions for each token
    :param start_date: datetime object of earliest date to get transactions from
    :param end_date: datetime object of latest date to get transactions from
    :return: transaction_bank
    """
    # TODO
    return transaction_bank




