""" create a csv of onchain transaction """

import requests
import os

import pandas as pd

from argparse import ArgumentParser
from io import StringIO


# since the covalent api python bindings weren't authenticating properly,
# here we just copy the relevant api calls, and edit them slightly to have key in the
# request's parameters to try to get it to work

def get_transactions(chain_id, address, api_key, block_signed_at_asc=False, no_logs=False):
    '''
    Retrieve all transactions for address including their decoded log events.
    This endpoint does a deep-crawl of the blockchain to retrieve all kinds
    of transactions that references the address.
    '''

    method_url = f'/v1/{chain_id}/address/{address}/transactions_v2/'

    params = {
        'block-signed-at-asc': block_signed_at_asc,
        'no-logs': no_logs,
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

    if response.json()['data']['pagination']['has_more']:
        raise(Exception('Too many transactions, increase page size.'))

    params['format'] = 'csv'

    response_csv = requests.get(url, params=params)

    result = response_csv.text

    return result


def filter_transactions(result, address):

    # read in transactions to pandas dataframe
    df = pd.read_csv(StringIO(result), dtype=str)

    df["from_address"] = df["from_address"].str.lower()
    df["to_address"] = df["to_address"].str.lower()
    df["log_events_decoded_params_value"] = df["log_events_decoded_params_value"].str.lower()

    # only get lines which involve your wallet address and are not approvals
    filtered_df = df[((df["from_address"] == address.lower())
                      | (df["to_address"] == address.lower())
                      | (df["log_events_decoded_params_value"] == address.lower()))
                     & (df["log_events_decoded_signature"] != "Approval(indexed address owner, indexed address spender, uint256 value)")]

    # convert pandas df into csv string
    filtered_result = filtered_df.to_csv()

    return filtered_result


def save_transactions(chain, address, api_key):

    # mapping to translate the chain name into it's value
    chain_ids = {'ethereum': '1', 'polygon': '137', 'bsc': '56', 'fantom': '250'}

    # pull all transaction data
    data_text = get_transactions(chain_ids[chain], address, api_key)

    # filter transaction data to only get necessary lines
    data_csv = filter_transactions(data_text, address)

    # save the data in the correct transaction-files subdirectory
    filename = os.path.join('transaction-files', chain, 'transactions.csv')

    with open(filename, 'w') as file:
        file.write(data_csv)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('chain', choices=['ethereum', 'polygon', 'bsc', 'fantom'],
        help='The chain on which to get all ')
    parser.add_argument('address', help='Your wallet address')
    parser.add_argument('api_key', help='Your covalent api key')

    args = parser.parse_args()

    save_transactions(args.chain, args.address, args.api_key)
