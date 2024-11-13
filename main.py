import logging
import random
import time
from datetime import datetime, timedelta
import threading
import signal
import sys
from telegram_bot_automation import TelegramBotAutomation
from browser_manager import BrowserManager
from utils import read_accounts_from_file, write_accounts_to_file, reset_balances, print_balance_table, update_balance_table
from colorama import Fore, Style
from prettytable import PrettyTable
from termcolor import colored
from requests.exceptions import RequestException

# Флаг для отслеживания прерывания программы
interrupted = False

# Load settings from settings.txt
def load_settings():
    settings = {}
    try:
        with open('settings.txt', 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                settings[key.strip()] = value.strip()
    except FileNotFoundError:
        logging.error(f"Settings file 'settings.txt' not found.")
    except Exception as e:
        logging.error(f"Error reading settings file: {e}")
    return settings

settings = load_settings()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Handler for SIGINT to ensure graceful shutdown
def signal_handler(sig, frame):
    global interrupted
    interrupted = True  # Устанавливаем флаг прерывания
    logger.error("Process interrupted by user. Exiting...")
    sys.exit(0)

def is_account_completed(account, filename="all_quest_complete.txt"):
    try:
        with open(filename, "r") as file:
            completed_accounts = file.read().splitlines()
        return str(account) in completed_accounts
    except FileNotFoundError:
        return False

signal.signal(signal.SIGINT, signal_handler)  # Register signal handler for SIGINT

if not logger.hasHandlers():
    class CustomFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: Fore.CYAN,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.MAGENTA,
        }

        def format(self, record):
            record.asctime = self.formatTime(record, self.datefmt).split('.')[0]
            log_message = super().format(record)
            log_message = log_message.replace(record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}")
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)
            log_message = log_message.replace(record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")
            return log_message

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# Data structure to store account information
account_info = {}

def process_account_task(account, settings):
    """
    Process each account's tasks and schedule a next run based on remaining_time.
    """
    bot = None
    remaining_time_seconds = None

    try:
        bot = TelegramBotAutomation(account, settings)

        if not bot.navigate_to_bot():
            raise Exception("Failed to navigate to bot")

        if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
            raise Exception("Failed to send message")
        if not bot.click_link():
            raise Exception("Failed to click link")

        if not is_account_completed(account):
            try:
                bot.process_mission_quests()
            except Exception as e:
                logger.error(f"Error occurred during mission quests: {e}")
                bot.open_section(1, "Home")
        else:
            logger.info(f"Account {account}: Quests already completed, skipping.")  

        balance, username = bot.get_balance()
        account_info[account]["username"] = username
        account_info[account]["balance"] = balance    
        bot.farming()     
        
        #Обновление баланса после фарминга
        balance = bot.get_update_balance()
        account_info[account]["balance"] = balance
        logger.info(f"Account {account}: Processing completed successfully.")
        update_balance_table(account, username, balance)

        remaining_time_seconds = bot.get_remaining_time()
    except Exception as e:
        logger.warning(f"Account {account}: Error occurred: {e}")
    finally:
        if bot:
            bot.browser_manager.api_stop_browser()
        logger.info(f"Account {account}: Task ended.")

    if remaining_time_seconds:
        next_run_time = (datetime.now() + timedelta(seconds=remaining_time_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        account_info[account]["next_run_time"] = next_run_time
        account_info[account]["status"] = "Scheduled"
        logger.info(f"Account {account}: Next run scheduled at {next_run_time}.")

        # Устанавливаем индивидуальный таймер для перезапуска задачи аккаунта
        timer = threading.Timer(remaining_time_seconds, process_account_task, args=(account, settings))
        timer.start()
    else:
        account_info[account]["next_run_time"] = "Immediate"
        account_info[account]["status"] = "Completed"

def process_accounts():
    reset_balances()
    accounts = read_accounts_from_file()
    random.shuffle(accounts)
    write_accounts_to_file(accounts)

    for account in accounts:
        account_info[account] = {
            "username": "N/A",
            "balance": 0.0,
            "next_run_time": "N/A",
            "status": "Pending"
        }
        process_account_task(account, settings)

    # Отображение таблицы перед перезапуском
    #logger.info("Main Cycle Balance Table (Before Retry):")
    #display_balance_table(account_info)

    # Перезапуск для аккаунтов со статусом, отличным от 'Scheduled'
    retried_accounts = []
    for account, info in account_info.items():
        if info["status"] != "Scheduled":
            logger.warning(f"Account {account} did not complete successfully. Attempting restart.")
            process_account_task(account, settings)
            retried_accounts.append(account)

    # Отображаем итоговую таблицу
    display_balance_table(account_info)

    if retried_accounts:
        logger.info(colored("The following accounts were retried:"))
        retry_table = PrettyTable()
        retry_table.field_names = ["ID", "Username", "Balance", "Next Run Time", "Status"]
        for account in retried_accounts:
            info = account_info[account]
            retry_table.add_row([
                account,
                info["username"],
                info["balance"],
                info["next_run_time"],
                info["status"]
            ])
        print(colored(retry_table, "yellow"))

    # Генерация случайного времени ожидания от 8 до 14 часов для полного перезапуска всех аккаунтов
    wait_hours = random.randint(8, 14)
    logger.info(colored(f"All accounts processed. Waiting {wait_hours} hours before restarting."))
    for hour in range(wait_hours):
        logger.info(colored(f"Waiting... {wait_hours - hour} hours left till restart."))
        time.sleep(60 * 60)  # ожидание в течение одного часа

def display_balance_table(account_info):
    logger.info("Main Cycle Balance Table:")
    main_table = PrettyTable()
    main_table.field_names = ["ID", "Username", "Balance", "Next Run Time", "Status"]
    total_balance = 0.0
    for account, info in account_info.items():
        row = [
            account,
            info["username"],
            info["balance"],
            info["next_run_time"],
            info["status"]
        ]
        main_table.add_row([colored(cell, 'cyan') for cell in row])
        if isinstance(info["balance"], (int, float)):
            total_balance += info["balance"]

    logger.info("\n" + str(main_table))
    logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:,.2f}{Style.RESET_ALL}")

if __name__ == "__main__":
    try:
        process_accounts()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")