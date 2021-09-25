from typing import List
from abc import ABC, abstractmethod

import heapq
import datetime
import requests
import yaml
import os

import pandas as pd
from io import StringIO


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


def get_user_input(string, dtype):
    while True:
        a = input(string)
        try:
            if dtype == 'float':
                rtn = float(a)
            elif dtype == 'int':
                rtn = int(a)
            elif dtype == 'datetime':
                format_string = "%Y-%m-%d %H:%M:%S"
                rtn = datetime.datetime.strptime(a, format_string)
            elif dtype == 'date':
                format_string = "%Y-%m-%d"
                rtn = datetime.datetime.strptime(a, format_string)
            elif dtype == 'direction':
                assert (a == 'in' or a == 'out')
                rtn = a
            return rtn
        except (ValueError, AssertionError):
            # parsing failed, ask for input again
            print("Invalid input, please make sure it matches the type required.")
            pass


def get_api_keys():
    with open('api_keys.yml', 'r') as stream:
        keys = yaml.safe_load(stream)
    return keys


def get_transactions_by_address(chain_id, address, block_signed_at_asc=False, no_logs=False, page_size=500):
    '''
    Retrieve all transactions for address including their decoded log events.
    This endpoint does a deep-crawl of the blockchain to retrieve all kinds
    of transactions that references the address.
    '''

    method_url = f'/v1/{chain_id}/address/{address}/transactions_v2/'

    api_key = get_api_keys()['covalent']

    params = {
        'block-signed-at-asc': block_signed_at_asc,
        'no-logs': no_logs,
        'format': 'json',
        'key': api_key,
        'page-size': page_size,
    }

    result = query(method_url, params)

    return result


def get_transaction_by_hash(chain_id, tx_hash):
    '''
    Retrieve all transactions for address including their decoded log events.
    This endpoint does a deep-crawl of the blockchain to retrieve all kinds
    of transactions that references the address.
    '''

    method_url = f'/v1/{chain_id}/transaction_v2/{tx_hash}/'

    api_key = get_api_keys()['covalent']

    params = {
        'block-signed-at-asc': False,
        'no-logs': False,
        'format': 'json',
        'key': api_key,
        'page-size': 500,
    }

    result = query(method_url, params)

    return result


def query(url, params=None):
    '''
    Query the *url* request with the given *params*

    :param url: path url to query.
    :param params: Dictionary with url parameters
    :param decode: Json decode the returned response from the server.
    '''
    url = "{}{}".format('https://api.covalenthq.com', url)

    response = requests.get(url, params=params)

    if response:
        data = response.json()['data']

        if data and 'pagination' in data.keys():
            if data['pagination'] is not None and 'has_more' in data['pagination'].keys():
                if data['pagination']['has_more']:
                    print("NOTE: not all transactions that meet the criteria have been able to be retrieved. Increase page size if more are needed.")

    params['format'] = 'csv'

    response_csv = requests.get(url, params=params)

    result = response_csv.text

    return result


def filter_transactions(result):

    # read in transactions to pandas dataframe
    df = pd.read_csv(StringIO(result), dtype=str)

    df["from_address"] = df["from_address"].str.lower()
    df["to_address"] = df["to_address"].str.lower()
    df["log_events_decoded_params_value"] = df["log_events_decoded_params_value"].str.lower()

    # only get lines which are not approvals
    filtered_df = df[(df["log_events_decoded_signature"] != "Approval(indexed address owner, indexed address spender, uint256 value)")]

    # convert pandas df into csv string
    filtered_result = filtered_df.to_csv()

    return filtered_result


def save_transactions(chain, address):

    # mapping to translate the chain name into it's value
    chain_ids = {'ethereum': '1', 'polygon': '137', 'bsc': '56', 'fantom': '250'}

    # pull all transaction data
    data_text = get_transactions_by_address(chain_ids[chain], address)

    # filter transaction data to only get necessary lines
    data_csv = filter_transactions(data_text)

    # save the filtered data in the correct transaction-files subdirectory
    filename = os.path.join('transaction-files', chain, 'transactions.csv')

    with open(filename, 'w') as file:
        file.write(data_csv)

    # save all transactions
    filename = os.path.join('transaction-files', chain, 'transactions-all.csv')

    with open(filename, 'w') as file:
        file.write(data_text)
