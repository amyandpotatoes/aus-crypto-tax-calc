# aus-crypto-tax-calc
This program allows you to easily work through and summarise your cryptocurrency transaction, to make it easier to lodge
an Australian personal tax return. This is not tax advice, and you should carefully look through the the calculations to 
ensure that they are correct and meet current tax laws. This program uses the first-in-first-out (FIFO) method of 
calculating tax bases, and assumes that you are eligible for 50% capital gains tax discounts on tokens held for longer 
than a year.

### Supported platforms
This program currently only supports the following Centralised Exchanges and blockchains:
- Binance
- ethereum
- binance smart chain
- polygon
- fantom
If you'd like to help us cover more CEXs and chains, please add it in the issues tab!

### Requirements
To use this program, you will need:
- Python (ideally 3.8) installed
- free API keys for the [Covalent API](https://www.covalenthq.com/platform/#/auth/register/) and for any Xscan (eg. [EtherScan](https://etherscan.io/apis)) if you use any
of the following chains:
    - ethereum
    - binance smart chain
    - polygon
    - fantom

### Preparation
Before you start the program you will need to:
1. Add your API keys to the api_keys.yml file, an example format is shown below
```
covalent: ckey_COVALENTKEYHERE
bsc: BSCKEYHERE
```
2. Add your wallet public addresses to the wallets.yml file, you can name each entry whatever is helpful to you
```
wallet1: '0x1234567812345678123456781234567812345678'
wallet2: '0x1234567812345678123456781234567812345678'
```
3. If you have any binance transactions, extract a transaction summary for the appropriate time frame from binance and 
place this in the /transaction-files/binance folder

### How to run

If you would like to use transactions from any of the following blockchains:
    - ethereum
    - binance smart chain
    - polygon
    - fantom
Then run the 'import_onchain_transaction.py' module.

Next, run the 'transactions.py' module to parse transactions and categorise them. Each time a transaction is parsed, progress is saved to a file which can be retrieved later.

Next, run the 'tax.py' module to produce a summary of transactions, capital gains and income.



