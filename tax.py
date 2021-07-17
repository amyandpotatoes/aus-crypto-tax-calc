from engine import FeatureState


class TaxState(FeatureState):
    """
    Contains the tax information for each of the financial years between the start and end dates.
    """
    def __init__(self, start_date, end_date):
        super().__init__()
        self.tax_years = self.setup_tax_years()

    def setup_tax_years(self):
        # TODO
        tax_years = dict()
        return tax_years

    def process_sell(self, transaction):
        # TODO
        pass

    def process_gain(self, transaction):
        # TODO
        pass

    def process_loss(self, transaction):
        # TODO
        pass

    def adjust_tax(self, year, type, amount):
        self.tax_years[year][type] += amount