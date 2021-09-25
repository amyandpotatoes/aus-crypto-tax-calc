from argparse import ArgumentParser
from tax import TaxState


def main():
    # TODO: get this working as a combination of all the other modules

    parser = ArgumentParser()
    parser.add_argument('--tax', '-t', action='store_true')
    parser.add_argument('--importchain', '-i', action='store_true')

    args = parser.parse_args()

    features = []
    if args.tax:
        features.append(TaxState)

    if args.importchain:
        pass


if __name__ == '__main__':
    main()
