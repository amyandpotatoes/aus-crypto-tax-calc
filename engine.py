from typing import List
from abc import ABC, abstractmethod

import heapq


class FeatureState:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.finished_processing = False

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
    NOTE: currently not in use

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


class TokenState(ABC):
    """
    Contains the current holdings of a single token, represented as a list of events where a token was aquired.
    """
    def __init__(self, name):
        self.name = name
        self.holdings = list()

    def add_holding(self, holding):
        heapq.heappush(self.holdings, holding)

    @abstractmethod
    def subtract_holding(self, volume):
        """May involve subtracting from an existing holding or removing a completely used-up holding. Returns the
        prices of the tokens when they were originally bought/received as list of tuples of (date, volume, price)."""
        holding_info = []
        return holding_info


class Holding(ABC):
    """
    An object containing a holding of a single token that was bought or gained in a single transaction.
    """
    def __init__(self, name, time, price, volume):
        self.name = name
        self.time = time
        self.price = price
        self.volume = volume

    def __lt__(self, other):
        return self.time < other.time

    def __eq__(self, other):
        return self.time == other.time


def run_engine(start_date, end_date, additional_features, transaction_bank):
    """
    Processes transactions throughout the specified time period, matching sell or loss transactions with the appropriate
    features.
    """
    # TODO
    pass
