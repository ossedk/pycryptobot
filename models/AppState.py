"""Application state class"""

import sys
from numpy import array as np_array, min as np_min, ptp as np_ptp
from models.PyCryptoBot import PyCryptoBot
from models.TradingAccount import TradingAccount
from models.exchange.binance import AuthAPI as BAuthAPI
from models.exchange.coinbase_pro import AuthAPI as CAuthAPI

class AppState():
    def __init__(self, app:PyCryptoBot, account:TradingAccount) -> None:
        if app.getExchange() == 'binance':
            self.api = BAuthAPI(app.getAPIKey(), app.getAPISecret(), app.getAPIURL())
        elif app.getExchange() == 'coinbasepro':
            self.api = CAuthAPI(app.getAPIKey(), app.getAPISecret(), app.getAPIPassphrase(), app.getAPIURL())
        else:
            self.api = None

        self.app = app
        self.account = account

        self.action = 'WAIT'
        self.buy_count = 0
        self.buy_state = ''
        self.buy_sum = 0
        self.eri_text = ''
        self.fib_high = 0
        self.fib_low = 0
        self.first_buy_size = 0
        self.iterations = 0
        self.last_action = 'WAIT'
        self.last_buy_size = 0
        self.last_buy_price = 0
        self.last_buy_filled = 0
        self.last_buy_fee = 0
        self.last_buy_high = 0 
        self.last_df_index = ''
        self.sell_count = 0
        self.sell_sum = 0

    def minimumOrderBase(self):
        print (f'Executing minimumOrderBase()')

        if self.app.getExchange() == 'binance':
            print (f'Executing minimumOrderBase() - binance')

            info = self.api.client.get_symbol_info(symbol=self.app.getMarket())

            base_min = 0
            if 'filters' in info:
                for filter_type in info['filters']:
                    if 'LOT_SIZE' == filter_type['filterType']:
                        base_min = float(filter_type['minQty'])

            base = float(self.account.getBalance(self.app.getBaseCurrency()))

            if base < base_min:
                sys.tracebacklimit = 0
                raise Exception(f'Insufficient Base Funds! (Actual: {base}, Minimum: {base_min})')

        elif self.app.getExchange() == 'coinbasepro':
            print (f'Executing minimumOrderBase() - coinbasepro')

            product = self.api.authAPI('GET', f'products/{self.app.getMarket()}')
            if len(product) == 0:
                sys.tracebacklimit = 0
                raise Exception(f'Market not found! ({self.app.getMarket()})')

            base = float(self.account.getBalance(self.app.getBaseCurrency()))
            base_min = float(product['base_min_size'])

            print (f'base {base}, base_min {base_min}')

            if base < base_min:
                sys.tracebacklimit = 0
                raise Exception(f'Insufficient Base Funds! (Actual: {base}, Minimum: {base_min})')

    def minimumOrderQuote(self):
        print (f'Executing minimumOrderQuote()')

        if self.app.getExchange() == 'binance':
            print (f'Executing minimumOrderQuote() - binance')

            info = self.api.client.get_symbol_info(symbol=self.app.getMarket())

            quote_min = 0
            if 'filters' in info:
                for filter_type in info['filters']:
                    if 'MIN_NOTIONAL' == filter_type['filterType']:
                        quote_min = float(filter_type['minNotional'])

            quote = float(self.account.getBalance(self.app.getQuoteCurrency()))

            if quote < quote_min:
                sys.tracebacklimit = 0
                raise Exception(f'Insufficient Quote Funds! (Actual: {quote}, Minimum: {quote_min})')

        elif self.app.getExchange() == 'coinbasepro':
            print (f'Executing minimumOrderQuote() - coinbasepro')

            product = self.api.authAPI('GET', f'products/{self.app.getMarket()}')
            if len(product) == 0:
                sys.tracebacklimit = 0
                raise Exception(f'Market not found! ({self.app.getMarket()})')

            ticker = self.api.authAPI('GET', f'products/{self.app.getMarket()}/ticker')
            price = float(ticker['price'])

            quote = float(self.account.getBalance(self.app.getQuoteCurrency()))
            base_min = float(product['base_min_size'])

            print (f'price {price}, quote {quote}, base_min {base_min}, quotedivprice: {quote / price}')

            if (quote / price) < base_min:
                sys.tracebacklimit = 0
                raise Exception(f'Insufficient Quote Funds! (Actual: {"{:.8f}".format((quote / price))}, Minimum: {base_min})')

    def initLastAction(self):
        # ignore if manually set
        if self.app.getLastAction() is not None:
            print (f'last_action manually set to {self.app.getLastAction()}')
            self.last_action = self.app.getLastAction()
            return

        # if not live
        if not self.app.isLive():
            print (f'last_action set to SELL as bot is not live!')
            self.last_action = 'SELL'
            return

        orders = self.account.getOrders(self.app.getMarket(), '', 'done')
        if len(orders) > 0:
            last_order = orders[-1:]

            # if orders exist and last order is a buy
            if str(last_order.action.values[0]) == 'buy':
                print (f'Last exchange order is a buy so setting the last_action to BUY')

                self.last_buy_size = float(last_order[last_order.action == 'buy']['size'])
                self.last_buy_filled = float(last_order[last_order.action == 'buy']['filled'])
                self.last_buy_price = float(last_order[last_order.action == 'buy']['price'])
                self.last_buy_fee = float(last_order[last_order.action == 'buy']['fees'])
                self.last_action = 'BUY'
                return
            else:
                print (f'Last exchange order is a buy so setting the last_action to SELL')

                self.minimumOrderBase()
                self.last_action = 'SELL'
                self.last_buy_price = 0.0
                return
        else:
            base = float(self.account.getBalance(self.app.getBaseCurrency()))
            quote = float(self.account.getBalance(self.app.getQuoteCurrency()))

            print (f'{self.app.getBaseCurrency()} base is {base}, {self.app.getQuoteCurrency()} base is {quote}')

            # nil base or quote funds
            if base == 0.0 and quote == 0.0:
                print (f'Base and quote is 0.0')

                sys.tracebacklimit = 0
                raise Exception(f'Insufficient Funds! ({self.app.getBaseCurrency()}={str(base)}, {self.app.getQuoteCurrency()}={str(base)})') 

            # determine last action by comparing normalised [0,1] base and quote balances 
            order_pairs = np_array([ base, quote ])
            print ('Order pairs', order_pairs)

            order_pairs_normalised = (order_pairs - np_min(order_pairs)) / np_ptp(order_pairs)
            print ('Order pairs normalised:', order_pairs_normalised)

            if order_pairs_normalised[0] < order_pairs_normalised[1]:
                self.minimumOrderQuote()
                self.last_action = 'SELL'
            elif order_pairs_normalised[0] > order_pairs_normalised[1]:
                self.minimumOrderBase()
                self.last_action = 'BUY'

            else:
                self.last_action = 'WAIT'

            return