from typing import List


class FeatureState:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date

    def process_buy(self, transaction):
        pass

    def process_sell(self, transaction):
        pass

    def process_gain(self, transaction):
        pass

    def process_loss(self, transaction):
        pass


class WalletState:
    """"
    Contains the state of the wallet at given time, including bought tokens that have not been sold and their cost
    bases, tax information for each financial year since the start date.
    """
    def __init__(self, start_date, end_date, additional_features: List[FeatureState] = None):
        self.current_time = start_date
        self.start_date = start_date
        self.end_date = end_date
        self.tokens = dict()
        self.finished_processing = False
        self.features = [feature(start_date, end_date) for feature in additional_features]

    def add_token(self, token_name):
        # TODO
        pass

    def process_buy(self, transaction):
        # TODO
        pass

    def process_sell(self, transaction):
        # TODO
        pass

    def process_gain(self, transaction):
        # TODO
        pass

    def process_loss(self, transaction):
        # TODO
        pass


class TokenState:
    """
    Contains the current holdings of a single token, represented as a list of buys.
    """
    def __init__(self, name):
        self.name = name
        self.buys = list()

    def add_holding(self, time, tax_price, raw_price, volume):
        # TODO
        pass

    def subtract_holding(self, time, volume):
        "May involve subtracting from an existing holding or removing a completely used-up holding."
        # TODO
        pass


class Holding:
    """
    An object containing a holding of a single token that was bought or gained in a single transaction.
    """
    def __init__(self, name, time, tax_price, raw_price, volume):
        self.name = name
        self.time = time
        self.tax_price = tax_price
        self.raw_price = raw_price
        self.volume = volume


def run_engine(start_date, end_date, additional_features, transaction_bank):
    """
    Processes transactions throughout the specified time period, matching sell or loss transactions with the appropriate
    features.
    """
    # TODO
    pass
