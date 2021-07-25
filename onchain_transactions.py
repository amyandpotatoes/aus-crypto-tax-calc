""" create a csv of onchain transaction """

import requests
import os

from argparse import ArgumentParser


# since the covalent api python bindings weren't authenticating properly,
# here we just copy the relevant api calls, and edit them slightly to have key in the
# request's parameters to try to get it to work

def get_transactions(chain_id, address, api_key, block_signed_at_asc=True, no_logs=False):
    '''
    Retrieve all transactions for address including their decoded log events.
    This endpoint does a deep-crawl of the blockchain to retrieve all kinds
    of transactions that references the address.
    '''

    method_url = f'/v1/{chain_id}/address/{address}/transactions_v2/'

    params = {
        'block-signed-at-asc': block_signed_at_asc,
        'no-logs': no_logs,
        'format': 'csv',
        'key': api_key
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

    result = response.text
    if not result:
        return result

    return result

def save_transactions(chain, address, api_key):

    # mapping to translate the chain name into it's value
    chain_ids = {'ethereum': '1', 'polygon': '137', 'bsc': '56', 'fantom': '250'}

    data_csv = get_transactions(chain_ids[chain], address, api_key)

    # save the data in the correct transaction-files subdirectory
    filename = os.path.join('transaction-files', chain, 'transactions.csv')

    with open(filename, 'w') as file:
        file.write(data_csv)

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('chain', choices=['etherium', 'polygon', 'bsc', 'fantom'],
        help='The chain on which to get all ')
    parser.add_argument('address', help='Your wallet address')
    parser.add_argument('api_key', help='Your covalent api key')

    args = parser.parse_args()

    save_transactions(args.chain, args.address, args.api_key)
