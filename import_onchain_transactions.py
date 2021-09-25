""" create a csv of onchain transaction """

from utils import save_transactions, get_user_input
import yaml

if __name__ == '__main__':

    for chain in ['ethereum', 'bsc', 'polygon', 'fantom']:
        process = input(f"Would you like to process {chain} transactions? (Y/n) ")
        if process.lower() != "n":
            with open("wallets.yml") as file:
                wallets = yaml.load(file)
            for (name, wallet) in wallets.items():
                wallet_bsc = input(f"Would you like to import transactions for wallet {wallet} ({name}) on {chain}? (Y/n) ")
                if wallet_bsc.lower() != "n":
                    save_transactions(chain, wallet)
