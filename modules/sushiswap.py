from modules.approve import Approve, from_wei
# from modules.tg_bot import TgBot
from requests import ConnectionError
from web3.exceptions import TransactionNotFound
from web3 import Web3
from settings import remainder_eth, SLIPPAGE, swap_decimal
import json as js
import time


class SushiSwap(Approve):

    def __init__(self, private_key, web3, number, log):
        super().__init__(private_key, web3, number, log)
        self.web3 = web3
        self.number = number
        self.log = log
        self.private_key = private_key
        self.address_wallet = self.web3.eth.account.from_key(private_key).address
        self.token_abi = js.load(open('./abi/Token.txt'))
        self.address = Web3.to_checksum_address('0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506')
        self.abi = js.load(open('./abi/sushi.txt'))
        self.contract = self.web3.eth.contract(address=self.address, abi=self.abi)
        self.ETH = Web3.to_checksum_address('0x722e8bdd2ce80a4422e880164f2079488e115365')
        self.token_remove_abi = js.load(open('./abi/Token_remove.txt'))

    def buy_token(self, token_to_buy, prescale, retry=0):
        try:
            self.log.info(f'Buy {token_to_buy["name"]} token on SushiSwap')

            balance = self.web3.eth.get_balance(self.address_wallet) - Web3.to_wei(remainder_eth, 'ether')
            if balance < 0:
                self.log.info('Insufficient funds')
                return 'balance'
            value = int(balance * prescale)
            value_wei = round(Web3.from_wei(value, 'ether'), swap_decimal)
            value = Web3.to_wei(value_wei, 'ether')

            amount_out = self.contract.functions.getAmountsOut(value, (self.ETH, token_to_buy['address'])).call()[1]
            min_tokens = int(amount_out - (amount_out * SLIPPAGE // 100))
            min_tok = round(from_wei(token_to_buy["decimal"], min_tokens), 5)

            contract_txn = self.contract.functions.swapExactETHForTokens(
                min_tokens,
                [self.ETH, token_to_buy['address']],
                self.address_wallet,
                (int(time.time()) + 10000)  # deadline
            ).build_transaction({
                'from': self.address_wallet,
                'value': value,
                'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            })

            signed_txn = self.web3.eth.account.sign_transaction(contract_txn, private_key=self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            self.log.info('Отправил транзакцию')
            time.sleep(1)
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300, poll_latency=10)
            if tx_receipt.status == 1:
                self.log.info(f'Транзакция смайнилась успешно')
            else:
                self.log.error('Транзакция сфейлилась, пытаюсь еще раз')
                # if TgBot.TG_BOT_SEND is True:
                #     TgBot.send_message_error(self, self.number, 'Buy token SushiSwap', self.address_wallet,
                #                              'Транзакция сфейлилась, пытаюсь еще раз')
                time.sleep(60)
                retry += 1
                if retry > 5:
                    return 0
                self.buy_token(token_to_buy, prescale, retry)
                return

            self.log.info(f'[{self.number}] Buy {min_tok} {token_to_buy["name"]} SushiSwap || https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}\n')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_success(self, self.number, f'Buy {min_tok} {token_to_buy["name"]} SushiSwap', self.address_wallet,
            #                                f'https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}')

        except TransactionNotFound:
            self.log.error('Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Buy token SushiSwap', self.address_wallet,
            #                              'Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.buy_token(token_to_buy, prescale, retry)

        except ConnectionError:
            self.log.error('Ошибка подключения к интернету или проблемы с РПЦ')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Buy token SushiSwap', self.address_wallet,
            #                              'Ошибка подключения к интернету или проблемы с РПЦ')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.buy_token(prescale, prescale, retry)

        except Exception as error:
            if isinstance(error.args[0], dict):
                if 'insufficient funds' in error.args[0]['message']:
                    self.log.error('Ошибка, скорее всего нехватает комсы')
                    # if TgBot.TG_BOT_SEND is True:
                    #     TgBot.send_message_error(self, self.number, 'Buy token SushiSwap', self.address_wallet,
                    #                              'Ошибка, скорее всего нехватает комсы')
                    return 'balance'
                else:
                    self.log.error(error)
                    time.sleep(60)
                    retry += 1
                    if retry > 5:
                        return 0
                    self.buy_token(token_to_buy, prescale, retry)
            else:
                self.log.error(error)
                time.sleep(60)
                retry += 1
                if retry > 5:
                    return 0
                self.buy_token(token_to_buy, prescale, retry)

    def sold_token(self, token_to_sold, retry=0):
        try:
            self.log.info(f'Sold {token_to_sold["name"]} token on SushiSwap')

            token_contract = self.web3.eth.contract(address=token_to_sold['address'], abi=self.token_abi)
            token_balance = token_contract.functions.balanceOf(self.address_wallet).call()
            if token_balance == 0:
                self.log.info(f'Balance {token_to_sold["name"]} - 0\n')
                return
            decimal = token_contract.functions.decimals().call()
            allowance = token_contract.functions.allowance(self.address_wallet, self.address).call()
            if allowance < 10000 * 10 ** decimal:
                self.log.info('Нужен аппрув, делаю')
                self.approve(token_to_sold['address'], self.address)
                time.sleep(60)

            amount_out = self.contract.functions.getAmountsOut(token_balance, [token_to_sold['address'], self.ETH]).call()[1]
            min_tokens = int(amount_out - (amount_out * SLIPPAGE // 100))
            min_tok = round(from_wei(token_to_sold["decimal"], token_balance), 5)

            contract_txn = self.contract.functions.swapExactTokensForETH(
                token_balance,
                min_tokens,
                [token_to_sold['address'], self.ETH],
                self.address_wallet,
                (int(time.time()) + 10000)  # deadline
            ).build_transaction({
                'from': self.address_wallet,
                'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            })

            signed_txn = self.web3.eth.account.sign_transaction(contract_txn, private_key=self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            self.log.info('Отправил транзакцию')
            time.sleep(1)
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300, poll_latency=10)
            if tx_receipt.status == 1:
                self.log.info(f'Транзакция смайнилась успешно')
            else:
                self.log.error('Транзакция сфейлилась, пытаюсь еще раз')
                # if TgBot.TG_BOT_SEND is True:
                #     TgBot.send_message_error(self, self.number, 'Sold token SushiSwap', self.address_wallet,
                #                              'Транзакция сфейлилась, пытаюсь еще раз')
                time.sleep(30)
                retry += 1
                if retry > 5:
                    return 0
                self.sold_token(token_to_sold, retry)
                return

            self.log.info(f'[{self.number}] Sold {min_tok} {token_to_sold["name"]} SushiSwap || https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}\n')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_success(self, self.number, f'Sold {min_tok} {token_to_sold["name"]} SushiSwap', self.address_wallet,
            #                                f'https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}')

        except TransactionNotFound:
            self.log.error('Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Sold token SushiSwap', self.address_wallet,
            #                              'Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.sold_token(token_to_sold, retry)

        except ConnectionError:
            self.log.error('Ошибка подключения к интернету или проблемы с РПЦ')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Sold token SushiSwap', self.address_wallet,
            #                              'Ошибка подключения к интернету или проблемы с РПЦ')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.sold_token(token_to_sold, retry)

        except Exception as error:
            if isinstance(error.args[0], dict):
                if 'insufficient funds' in error.args[0]['message']:
                    self.log.error('Ошибка, скорее всего нехватает комсы')
                    # if TgBot.TG_BOT_SEND is True:
                    #     TgBot.send_message_error(self, self.number, 'Sold token SushiSwap', self.address_wallet,
                    #                              'Ошибка, скорее всего нехватает комсы')
                    return 'balance'
                else:
                    self.log.error(error)
                    time.sleep(60)
                    retry += 1
                    if retry > 5:
                        return 0
                    self.sold_token(token_to_sold, retry)
            else:
                self.log.error(error)
                time.sleep(60)
                retry += 1
                if retry > 5:
                    return 0
                self.sold_token(token_to_sold, retry)

    def add_liquidity(self, token_to_add, retry=0):
        try:
            self.log.info(f'Add Liquidity {token_to_add["name"]} token on SushiSwap')

            token_contract = self.web3.eth.contract(address=token_to_add['address'], abi=self.token_abi)
            token_balance = token_contract.functions.balanceOf(self.address_wallet).call()
            if token_balance == 0:
                self.log.info(f'Balance {token_to_add["name"]} - 0\n')
                return
            decimal = token_contract.functions.decimals().call()
            allowance = token_contract.functions.allowance(self.address_wallet, self.address).call()
            if allowance < 10000 * 10 ** decimal:
                self.log.info('Нужен аппрув, делаю')
                self.approve(token_to_add['address'], self.address)
                time.sleep(60)

            amount_out = self.contract.functions.getAmountsOut(token_balance, [token_to_add['address'], self.ETH]).call()[1]
            amount_out_eth = int(amount_out - (amount_out * SLIPPAGE // 100))
            min_tok = round(from_wei(token_to_add["decimal"], token_balance), 5)

            contract_txn = self.contract.functions.addLiquidityETH(
                token_to_add['address'],
                token_balance,
                int(token_balance - (token_balance * SLIPPAGE // 100)),
                amount_out_eth,
                self.address_wallet,
                (int(time.time()) + 10000),  # deadline
            ).build_transaction({
                'from': self.address_wallet,
                'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
                'value': amount_out
            })

            signed_txn = self.web3.eth.account.sign_transaction(contract_txn, private_key=self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            self.log.info('Отправил транзакцию')
            time.sleep(1)
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300, poll_latency=10)
            if tx_receipt.status == 1:
                self.log.info(f'Транзакция смайнилась успешно')
            else:
                self.log.error('Транзакция сфейлилась, пытаюсь еще раз')
                # if TgBot.TG_BOT_SEND is True:
                #     TgBot.send_message_error(self, self.number, 'Add token SushiSwap', self.address_wallet,
                #                              'Транзакция сфейлилась, пытаюсь еще раз')
                time.sleep(30)
                retry += 1
                if retry > 5:
                    return 0
                self.add_liquidity(token_to_add, retry)
                return

            self.log.info(f'[{self.number}] Add {min_tok} {token_to_add["name"]} SushiSwap || https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}\n')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_success(self, self.number, f'Add {min_tok} {token_to_add["name"]} SushiSwap', self.address_wallet,
            #                                f'https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}')

        except TransactionNotFound:
            self.log.error('Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Add token SushiSwap', self.address_wallet,
            #                              'Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.add_liquidity(token_to_add, retry)

        except ConnectionError:
            self.log.error('Ошибка подключения к интернету или проблемы с РПЦ')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Add token SushiSwap', self.address_wallet,
            #                              'Ошибка подключения к интернету или проблемы с РПЦ')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.add_liquidity(token_to_add, retry)

        except Exception as error:
            if isinstance(error.args[0], dict):
                if 'insufficient funds' in error.args[0]['message']:
                    self.log.error('Ошибка, скорее всего нехватает комсы')
                    # if TgBot.TG_BOT_SEND is True:
                    #     TgBot.send_message_error(self, self.number, 'Add token SushiSwap', self.address_wallet,
                    #                              'Ошибка, скорее всего нехватает комсы')
                    return 'balance'
                else:
                    self.log.error(error)
                    time.sleep(60)
                    retry += 1
                    if retry > 5:
                        return 0
                    self.add_liquidity(token_to_add, retry)
            else:
                self.log.error(error)
                time.sleep(60)
                retry += 1
                if retry > 5:
                    return 0
                self.add_liquidity(token_to_add, retry)

    def remove_liquidity(self, token_to_remove, retry=0):
        try:
            self.log.info(f'Remove Liquidity {token_to_remove["name"]} token on SushiSwap')

            token_contract = self.web3.eth.contract(address=token_to_remove['lp sushi'], abi=self.token_remove_abi)
            token_balance = token_contract.functions.balanceOf(self.address_wallet).call()
            if token_balance == 0:
                self.log.info(f'Balance {token_to_remove["name"]} - 0\n')
                return 'token 0'
            decimal = token_contract.functions.decimals().call()
            allowance = token_contract.functions.allowance(self.address_wallet, self.address).call()
            if allowance < 10000 * 10 ** decimal:
                self.log.info('Нужен аппрув, делаю')
                self.approve(token_to_remove['lp sushi'], self.address)
                time.sleep(60)

            price_eth1, price_token1, _ = token_contract.functions.getReserves().call()
            price_eth = int(price_eth1 / token_balance)
            price_token = int(price_token1 / token_balance)

            amount_eth_min = int(price_eth - (price_eth * SLIPPAGE // 100))
            amount_token_min = int(price_token - (price_token * SLIPPAGE // 100))

            contract_txn = self.contract.functions.removeLiquidityETH(
                token_to_remove['address'],
                token_balance,
                amount_token_min,
                amount_eth_min,
                self.address_wallet,
                (int(time.time()) + 10000),  # deadline
            ).build_transaction({
                'from': self.address_wallet,
                'nonce': self.web3.eth.get_transaction_count(self.address_wallet)
            })

            signed_txn = self.web3.eth.account.sign_transaction(contract_txn, private_key=self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            self.log.info('Отправил транзакцию')
            time.sleep(1)
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300, poll_latency=10)
            if tx_receipt.status == 1:
                self.log.info(f'Транзакция смайнилась успешно')
            else:
                self.log.error('Транзакция сфейлилась, пытаюсь еще раз')
                # if TgBot.TG_BOT_SEND is True:
                #     TgBot.send_message_error(self, self.number, 'Remove liquidity SushiSwap', self.address_wallet,
                #                              'Транзакция сфейлилась, пытаюсь еще раз')
                time.sleep(30)
                retry += 1
                if retry > 5:
                    return 0
                self.remove_liquidity(token_to_remove, retry)
                return

            self.log.info(f'[{self.number}] Remove {token_to_remove["name"]} SushiSwap || https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}\n')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_success(self, self.number, f'Remove {token_to_remove["name"]} SushiSwap', self.address_wallet,
            #                                f'https://nova.arbiscan.io/tx/{Web3.to_hex(tx_hash)}')

        except TransactionNotFound:
            self.log.error('Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Remove liquidity SushiSwap', self.address_wallet,
            #                              'Транзакция не смайнилась за долгий промежуток времени, пытаюсь еще раз')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.remove_liquidity(token_to_remove, retry)

        except ConnectionError:
            self.log.error('Ошибка подключения к интернету или проблемы с РПЦ')
            # if TgBot.TG_BOT_SEND is True:
            #     TgBot.send_message_error(self, self.number, 'Remove liquidity SushiSwap', self.address_wallet,
            #                              'Ошибка подключения к интернету или проблемы с РПЦ')
            time.sleep(60)
            retry += 1
            if retry > 5:
                return 0
            self.remove_liquidity(token_to_remove, retry)

        except Exception as error:
            if isinstance(error.args[0], dict):
                if 'insufficient funds' in error.args[0]['message']:
                    self.log.error('Ошибка, скорее всего нехватает комсы')
                    # if TgBot.TG_BOT_SEND is True:
                    #     TgBot.send_message_error(self, self.number, 'Remove liquidity SushiSwap', self.address_wallet,
                    #                              'Ошибка, скорее всего нехватает комсы')
                    return 'balance'
                else:
                    self.log.error(error)
                    time.sleep(60)
                    retry += 1
                    if retry > 5:
                        return 0
                    self.remove_liquidity(token_to_remove, retry)
            else:
                self.log.error(error)
                time.sleep(60)
                retry += 1
                if retry > 5:
                    return 0
                self.remove_liquidity(token_to_remove, retry)
