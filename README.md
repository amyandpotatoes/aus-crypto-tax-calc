# aus-crypto-tax-calc
This program allows you to easily work through and summarise your cryptocurrency transaction, to make it easier to lodge
an Australian personal tax return. This is not tax advice, and you should carefully look through the the calculations to 
ensure that they are correct and meet current tax laws. This program uses the first-in-first-out (FIFO) method of 
calculating tax bases, and assumes that you are eligible for 50% capital gains tax discounts on tokens held for longer 
than a year.

### Current status
- import_onchain_transactions: working
- transactions.py: Binance working, Coinspot working, BTCMarkets working, ethereum/bsc/polygon/fantom working with small bugs (see Known issues)
- tax.py: working

### Supported platforms
This program currently only supports the following Centralised Exchanges and blockchains:
- Binance (buy/sell, 'earn', eth 2.0 staking)
- CoinSpot (buy/sell only)
- BTCMarkets (buy/sell only)
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
1. Create a file called api_keys.yml in the top level directory and add your API keys, an example format is shown below
```
covalent: ckey_COVALENTKEYHERE
bsc: BSCSCANKEYHERE
polygon: POLYGONSCANKEYHERE
ethereum: ETHERSCANKEYHERE
fantom: FTMSCANKEYHERE
```
2. Create a file called wallets.yml in the top level directory and add your wallet public addresses, you can name each entry whatever is helpful to you
```
wallet1: '0x1234567812345678123456781234567812345678'
wallet2: '0x1234567812345678123456781234567812345678'
```
3. If you have any binance transactions or other earnings including staking  or 'earn' income, extract a CSV transaction summary for the appropriate time frame from binance and 
place this in the /transaction-files/binance folder. This programs supports transactions spread across multiple CSVs, so 
all CSVs in this folder will be read in sequence.
Ensure your transaction history includes:  
- trading activity
- any binance ethereum staking (trading ETH for BETH) and income - note this one seems very hard to export, you might need to copy-paste
- any locked staking income
- any other income

4. If you have any CoinSpot or BTCMarket transactions, export CSVs of these transactions a place them in the /transaction-files/coinspot and /transaction-files/btcmarkets folders.

### How to run

If you would like to use transactions from any of the following blockchains:  
    - ethereum  
    - binance smart chain  
    - polygon  
    - fantom  
  
Then run the 'import_onchain_transaction.py' module.

Next, run the 'transactions.py' module to parse transactions and categorise them. Each time a transaction is parsed, progress is saved to a file which can be retrieved later.

Next, run the 'tax.py' module to produce a summary of transactions, capital gains and income.

### Known issues

- native tokens (BNB/MATIC etc.) sometimes doesn't get parsed correctly when used to make an LP/swapping using a DEX, you'll need to add the native token manually when the question 'Would you like to make any changes?' is asked
- sometimes the quantity in a transaction (usually USDC or USDT?) for onchain transactions is missing 10 zeros, delete and create a new entry as above
