# use this module to delete transactions that have been accidentally saved
# TODO: add further editing capability

import glob
import os
import pprint
import pickle
from utils import get_user_input
from transactions import Transaction, TransactionType


def delete_transaction():
    # look for existing files
    file_list = glob.glob(os.path.join(os.path.dirname(__file__), "results", "transactions", "*.p"))
    if file_list:
        print("Existing files:")
        for n, f in enumerate(file_list):
            print(f"{n+1}. {os.path.basename(f)}")
        while True:
            file_num = input(f"Which existing file would you like to load? (#/n) ")
            if file_num in [str(m) for m in range(1, len(file_list)+1)]:
                with open(file_list[int(file_num)-1], "rb") as pickle_file:
                    global PREVIOUS_PRICES
                    (transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES) = pickle.load(pickle_file)
                print(f"Loaded transaction hashes: {processed_transaction_hashes}")
                pp = pprint.PrettyPrinter()
                print("Loaded transactions:")
                pp.pprint(transaction_bank)
                print(f"Loaded previous prices:")
                pp.pprint(PREVIOUS_PRICES)
                break

    hash = input(f"Enter the transaction hash you would like to delete: ")
    timestamp = get_user_input(f"Enter the timestamp of the transaction you would like to delete: (YYYY-MM-DD HH:MM:SS) ", 'datetime')

    involved_tokens = []
    transactions_to_remove = []

    try:
        if hash not in processed_transaction_hashes:
            raise KeyError("Transaction hash not found")
        processed_transaction_hashes.remove(hash)
        print(f"Successfully removed hash {hash}.")

        for token, transactions in transaction_bank.items():
            for transaction in transactions:
                if transaction.time == timestamp:
                    transactions_to_remove.append((token, transaction))
                    involved_tokens.append(token)

        for token, transaction in transactions_to_remove:
            transaction_bank[token].remove(transaction)
            print(f"Successfully removed transaction {transaction}")

        print(f"Remaining transactions for those tokens: ")
        for token, transactions in transaction_bank.items():
            if token in involved_tokens:
                print(token)
                pp.pprint(transactions)
                _ = input("(Press enter to continue) ")

    except Exception as e:
        print("Failed to Successfully delete")
        raise e
    else:
        print("All deleted successfully, saving this as a new file...")
        # pickle progress so far
        pickle_file_name = input("What would you like to call this new save file? ")
        filename = os.path.join(os.path.dirname(__file__), "results", "transactions", f"{pickle_file_name}.p")
        with open(filename, "wb") as pickle_file:
            pickle.dump((transaction_bank, processed_transaction_hashes, PREVIOUS_PRICES), pickle_file)
        print(f"Progress saved to {filename}")



if __name__ == '__main__':

    delete_transaction()