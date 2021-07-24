from transactions import read_transactions
from engine import run_engine
from argparse import ArgumentParser
from datetime import date
from tax import TaxState


def main():
    transaction_bank = read_transactions()

    parser = ArgumentParser()
    parser.add_argument('start_date', type=date)
    parser.add_argument('end_date', type=date)
    parser.add_argument('--tax', '-t', action='store_true')
    args = parser.parse_args()
    start_date = args.start_date
    end_date = args.end_date
    features = []
    if args.tax():
        features.append(TaxState)
    run_engine(start_date, end_date, features, transaction_bank)
