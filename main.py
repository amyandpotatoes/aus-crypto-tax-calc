from argparse import ArgumentParser
from datetime import date

from engine import run_engine
from onchain_transactions import save_transactions
from tax import TaxState
from transactions import read_transactions


def main():

    parser = ArgumentParser()
    parser.add_argument('start_date', type=date)
    parser.add_argument('end_date', type=date)
    parser.add_argument('--tax', '-t', action='store_true')
    parser.add_argument('--importchain', '-i', action='store_true')

    args = parser.parse_args()
    start_date = args.start_date
    end_date = args.end_date

    features = []
    if args.tax:
        features.append(TaxState)

    if args.importchain:
        # read in onchain transaction data and save as csv
        address = input("Enter you wallet address")
        api_key = input("Enter your covalent api key")
        chains = ['ethereum', 'polygon', 'bsc', 'fantom']
        for chain in chains:
            save_transactions(address, chain, api_key)

    transaction_bank = read_transactions(start_date, end_date)

    run_engine(start_date, end_date, features, transaction_bank)
