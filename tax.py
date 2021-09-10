from engine import FeatureState, Holding, TokenState
from transactions import TransactionType, Transaction

from sys import exit
from enum import Enum, auto
from dateutil.relativedelta import relativedelta
import pandas as pd
import pickle
import glob
import yaml
import pprint
import os
import heapq
import datetime


class TaxType(Enum):
    INCOME = auto()
    CAPGAINS = auto()


class TaxState(FeatureState):
    """
    Contains the tax information for each of the financial years between the start and end dates.
    """
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date)
        self.tax_years = self.setup_tax_years()
        self.token_states = dict()

    def setup_tax_years(self):
        tax_years = dict()
        date = self.start_date
        while date <= self.end_date:
            print(f"Date: {date}, Year: {date.year}")
            year_string, second_year = calculate_tax_year(date)
            tax_years[year_string] = []
            date = datetime.datetime(second_year, 7, 1)
        return tax_years

    def process_buy(self, transaction):
        # add bought tokens to holdings, so that cost basis is tracked
        # check if token is already in token states, if not then add
        if transaction.token.lower() not in self.token_states:
            self.token_states[transaction.token.lower()] = TaxTokenState(transaction.token.lower())
        # create a new holding representing the tokens that were bought and their cost basis
        holding = TaxHolding(transaction.token.lower(), transaction.time, transaction.token_price, transaction.token_fee_adjusted_price, transaction.volume)
        self.token_states[transaction.token.lower()].add_holding(holding)

    def process_sell(self, transaction):
        # check if token is already in token states, if not then add
        if transaction.token.lower() not in self.token_states:
            self.token_states[transaction.token.lower()] = TaxTokenState(transaction.token.lower())
        # get cost basis of token from holdings, and process the difference in value as capital gains
        holding_info = self.token_states[transaction.token.lower()].subtract_holding(transaction.volume)

        # process the tax, calculating whether 50% CG discount applies
        for start_time, start_price, start_volume in holding_info:
            capgains = (transaction.token_fee_adjusted_price - start_price) * start_volume
            self.adjust_tax(start_time, transaction.time, transaction.token, TaxType.CAPGAINS, start_price, transaction.token_fee_adjusted_price, start_volume, capgains)

    def process_gain(self, transaction):
        # process the value of the tokens as income
        # because the fee is already being used to reduce the cost basis, we don't use the fee-reduced price for this
        self.adjust_tax(None, transaction.time, transaction.token, TaxType.INCOME, 0, transaction.token_price, transaction.volume, transaction.token_price * transaction.volume)

        # add gained tokens to holdings, so that cost basis is tracked
        # check if token is already in token states, if not then add
        if transaction.token.lower() not in self.token_states:
            self.token_states[transaction.token.lower()] = TaxTokenState(transaction.token.lower())
        # create a new holding representing the tokens that were gained and their cost basis
        holding = TaxHolding(transaction.token.lower(), transaction.time, transaction.token_price, transaction.token_fee_adjusted_price, transaction.volume)
        self.token_states[transaction.token.lower()].add_holding(holding)

    def process_loss(self, transaction):
        # used when there is a genuine loss
        # if crypto is gifted or otherwise disposed of at market price, this should have been considered a sell at market price
        # check if token is already in token states, if not then add
        if transaction.token.lower() not in self.token_states:
            self.token_states[transaction.token.lower()] = TaxTokenState(transaction.token.lower())
        # get cost basis of token from holdings, and process the difference in value as capital loss
        holding_info = self.token_states[transaction.token.lower()].subtract_holding(transaction.volume)

        # process the tax, calculating whether 50% CG discount applies
        for start_time, start_price, start_volume in holding_info:
            capgains = (-1) * start_price * start_volume
            self.adjust_tax(start_time, transaction.time, transaction.token, TaxType.CAPGAINS, start_price, 0, start_volume, capgains)

    def adjust_tax(self, start_time, end_time, token, tax_type, start_price, end_price, volume, amount):
        tax_year, _ = calculate_tax_year(end_time)
        # note down transactions eligible for 50% discount
        discount = (end_time > start_time + relativedelta(months=+12))
        self.tax_years[tax_year].append([end_time, token, tax_type, start_price, end_price, volume, discount, amount])

    def finish_processing(self, file_name):
        # process all the lists of lists for each year into dataframes
        # add total lines for each of income and capgains, then save to file
        for tax_year in self.tax_years.keys():
            # convert into dataframe
            self.tax_years[tax_year] = pd.DataFrame(self.tax_years[tax_year], columns=['Time',
                                                                                       'Token',
                                                                                       'Tax Type',
                                                                                       'Cost Basis',
                                                                                       'Disposal Price',
                                                                                       'Volume',
                                                                                       'CG Discount Eligible',
                                                                                       'Value'])
            # calculate totals
            values = self.tax_years[tax_year].loc[:, 'Value']
            # calculate income
            income = values[self.tax_years[tax_year]['Tax Type'] == TaxType.INCOME].sum()

            # calculate CG-discount-eligible capital gains
            discount_eligible_cap_gains = values[(self.tax_years[tax_year]['Tax Type'] == TaxType.CAPGAINS) &
                                                 (self.tax_years[tax_year]['CG Discount Eligible']) &
                                                 (self.tax_years[tax_year]['Value'] >= 0)].sum()

            # calculate CG-discount-ineligible capital gains
            discount_ineligible_cap_gains = values[(self.tax_years[tax_year]['Tax Type'] == TaxType.CAPGAINS) &
                                                   (~self.tax_years[tax_year]['CG Discount Eligible']) &
                                                   (self.tax_years[tax_year]['Value'] >= 0)].sum()

            # calculate capital losses
            cap_losses = values[(self.tax_years[tax_year]['Tax Type'] == TaxType.CAPGAINS) &
                                (self.tax_years[tax_year]['Value'] < 0)].sum()

            # calculate total capital gains as 'discount-ineligible CG - capital losses + 0.5 * (discount-eligible CG - remaining capital losses)
            if cap_losses > discount_ineligible_cap_gains:
                cap_gains = 0.5 * (discount_ineligible_cap_gains + discount_eligible_cap_gains - cap_losses)
            else:
                cap_gains = (discount_ineligible_cap_gains - cap_losses) + (0.5 * discount_eligible_cap_gains)

            # add total rows
            self.tax_years[tax_year].loc[len(self.tax_years[tax_year])] = (
                ['FY', 'Total Income', TaxType.INCOME, None, None, None, None, income]
            )
            self.tax_years[tax_year].loc[len(self.tax_years[tax_year])] = (
                ['FY', 'Discount-Eligible CG', TaxType.CAPGAINS, None, None, None, None, discount_eligible_cap_gains]
            )
            self.tax_years[tax_year].loc[len(self.tax_years[tax_year])] = (
                ['FY', 'Discount-Ineligible CG', TaxType.CAPGAINS, None, None, None, None, discount_ineligible_cap_gains]
            )
            self.tax_years[tax_year].loc[len(self.tax_years[tax_year])] = (
                ['FY', 'Capital Losses', TaxType.CAPGAINS, None, None, None, None, cap_losses]
            )
            self.tax_years[tax_year].loc[len(self.tax_years[tax_year])] = (
                ['FY', 'Total Capital Gains', TaxType.CAPGAINS, None, None, None, None, cap_gains]
            )

            # save to csv
            self.tax_years[tax_year].to_csv(os.path.join(os.path.dirname(__file__), "results", "tax", f"{file_name}-{tax_year}.csv"))

        print("Tax summaries have been saved to /results/tax.")

        # set finished flag
        self.finished_processing = True


class TaxTokenState(TokenState):
    """
    Contains information about a token and all buy/incoming transactions for which a sell/outgoing transaction has not
    yet been processed.
    """
    def __init__(self, name):
        super().__init__(name)

    def subtract_holding(self, sell_volume):
        """May involve subtracting from an existing holding or removing a completely used-up holding."""
        # work through queue of buy transactions, subtracting until all of the sell volume is used up
        holding_info = []
        while sell_volume > 0:
            if self.holdings:
                holding = heapq.heappop(self.holdings)
                if holding.volume > sell_volume:
                    # if this holding is larger than the sold amount, reduce the holding by that amount and push it back
                    holding.volume -= sell_volume
                    heapq.heappush(self.holdings, holding)
                    holding_info.append((holding.time, holding.tax_price, sell_volume))
                else:
                    # if the sell amount >= the holding, no need to push back
                    holding_info.append((holding.time, holding.tax_price, holding.volume))
            else:
                # if we've run out of holdings before getting through all of the sell volume, there's probably been
                # a mistake or not all transactions were processed correctly when creating the transaction bank
                # get the needed info from the user
                print(f"Token: {self.name}, remaining volume not matched: {sell_volume}")
                print("Not enough holdings from buy/income transactions were found to match this disposal. Please enter the necessary information for taxes.")
                time = datetime.datetime.strptime(input("Time when acquired: (YYYY-MM-DD HH:MM:SS) "), "%Y-%m-%d %H:%M:%S")
                price = float(input("Fee-adjusted price per token when acquired: "))
                volume = float(input("Number of units acquired: "))

                # don't pop excess volume back on, we don't want user inputs to mess it up too much
                # they'll just have to input it again if they need it again later
                sell_volume -= volume

                holding_info.append((time, price, volume))

        return holding_info


class TaxHolding(Holding):
    """
    Represents a token that has been aquired but for which the disposal has not been processed or occurred. This is
    generally an intermediate item in a tax queue awaiting processing.
    """
    def __init__(self, name, time, price, tax_price, volume):
        super().__init__(name, time, price, volume)
        self.tax_price = tax_price


def calculate_tax_year(date):
    """
    Given a datetime object, returns the tax year that it belongs to as a string in the format "YYYY-YYFY" and an int
    of the second year
    :param date: a datetime object
    :return: (string: FY string, int: year)
    """
    if date >= datetime.datetime(date.year, 7, 1):
        return f"{date.year}-{date.year - 1999}FY", date.year + 1
    else:
        return f"{date.year - 1}-{date.year - 2000}FY", date.year


def tax_process_all_transactions(transaction_bank, start_date, end_date):
    # create a TaxState object that holds information about the state and results of the processing so far
    print("Trying to create a tax state...")
    tax = TaxState(start_date, end_date)
    print("Created a tax state...")

    # transaction bank is a dictionary of (token ticker: list of transactions) pairs
    # go through tokens, processing each transaction and the tax consequences
    for (token, transactions) in transaction_bank.items():
        # sort the list of transactions by date
        transactions.sort()

        # go through transactions in chronological order
        for transaction in transactions:
            if transaction.transaction_type == TransactionType.BUY:
                tax.process_buy(transaction)
            elif transaction.transaction_type == TransactionType.SELL:
                tax.process_sell(transaction)
            elif transaction.transaction_type == TransactionType.GAIN:
                tax.process_gain(transaction)
            elif transaction.transaction_type == TransactionType.LOSS:
                tax.process_loss(transaction)
            else:
                raise Exception("Transaction Type is not valid")
            print("Processed a transaction..")

    # finish processing
    file_name = input("Processing finished. \nOutput file name: ")
    tax.finish_processing(file_name)


def tax_read_in_transactions():
    # read in from pickled file
    file_list = glob.glob(os.path.join(os.path.dirname(__file__), "results", "transactions", "*.p"))
    if file_list:
        print("Transaction files:")
        for n, f in enumerate(file_list):
            print(f"{n + 1}. {os.path.basename(f)}")
        while True:
            file_num = input(f"Which transaction file would you like to load? (#/N) ")
            if file_num in [str(m) for m in range(1, len(file_list) + 1)]:
                with open(file_list[int(file_num) - 1], "rb") as pickle_file:
                    (transaction_bank, processed_transaction_hashes) = pickle.load(pickle_file)
                print(f"Loaded transaction hashes: {processed_transaction_hashes}")
                pp = pprint.PrettyPrinter()
                print("Loaded transactions:")
                pp.pprint(transaction_bank)
                return transaction_bank
    else:
        print("No transaction files found, you will need to process transactions before calculating tax.")
        exit()


def process_tax():

    print("What period would you like to calculate taxable income and capital gains for?")
    start_date = datetime.datetime.strptime(input(f"Enter the start date: (YYYY-MM-DD) "), "%Y-%m-%d")
    end_date = datetime.datetime.strptime(input(f"Enter the end date: (YYYY-MM-DD) "), "%Y-%m-%d")

    transaction_bank = tax_read_in_transactions()
    print("Returned transaction bank")

    tax_process_all_transactions(transaction_bank, start_date, end_date)


if __name__ == '__main__':
    tax_df = process_tax()