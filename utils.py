from prettytable import PrettyTable
import logging
from colorama import Fore, Style

# Set up logging with colors
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
            # Set time to white
            log_message = log_message.replace(record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}")
            # Set level name color
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            # Set message color based on level
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)
            log_message = log_message.replace(record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")
            return log_message

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

balances = []

def read_accounts_from_file():
    try:
        with open('accounts.txt', 'r') as file:
            accounts = [line.strip() for line in file.readlines()]
            logger.info(f"Successfully read {len(accounts)} accounts from file.")
            return accounts
    except FileNotFoundError:
        logger.error("accounts.txt file not found.")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error while reading accounts file: {str(e)}")
        return []

def write_accounts_to_file(accounts):
    try:
        with open('accounts.txt', 'w') as file:
            for account in accounts:
                file.write(f"{account}\n")
        #logger.info("Accounts written to file successfully.")
    except IOError as e:
        logger.error(f"Failed to write accounts to file: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error while writing accounts to file: {str(e)}")

def reset_balances():
    global balances
    balances = []
    logger.info("Balances reset successfully.")

def update_balance_table(serial_number, username_text, balance):
    global balances
    for i, (serial, user, bal) in enumerate(balances):
        if serial == serial_number:
            balances[i] = (serial_number, username_text, balance)
            return
    balances.append((serial_number, username_text, balance))
    logger.info(f"Account {serial_number}: Balance updated: Username - {username_text}, Balance - {balance}")

def print_balance_table():
    table = PrettyTable()
    table.field_names = ["S/N", "Username", "Balance"]
    for serial, user, bal in balances:
        table.add_row([serial, user, bal])
    print(table)
    logger.info("Balance table printed successfully.")

def export_balances_to_csv(filename='balances.csv'):
    try:
        with open(filename, 'w') as file:
            file.write("S/N,Username,Balance\n")
            for serial, user, bal in balances:
                file.write(f"{serial},{user},{bal}\n")
        logger.info(f"Balances exported to {filename} successfully.")
    except IOError as e:
        logger.error(f"Failed to export balances to CSV file: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error while exporting balances to CSV file: {str(e)}")
