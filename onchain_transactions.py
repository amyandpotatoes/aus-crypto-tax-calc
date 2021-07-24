""" create a csv of onchain transaction """

import os

from argparse import ArgumentParser

from covalent_api.class_a import ClassA
from covalent_api.session import Session

def save_transactions(chain, address, api_key):

    # make a Session with our api key
    session = Session(api_key=api_key)

    print(session.api_key)

    # make the class with our session in order to query the api
    A = ClassA(session)

    # mapping to translate the chain name into it's value
    chain_ids = {'ethereum': '1', 'polygon': '137', 'bsc': '56', 'fantom': '250'}
    print(chain_ids[chain])

    data_csv = A.get_transactions(
        chain_ids[chain],
        address,
        block_signed_at_asc=True, # True to get results in ascending order
        no_logs=False,
        page_number=None,
        page_size=None,
        format='csv' # json is the other option
    )

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
