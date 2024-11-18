import requests
import time
import logging
import sys
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from requests.exceptions import RequestException
from urllib3.exceptions import MaxRetryError, NewConnectionError
from colorama import Fore, Style

# Set up logging with colors
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Single-line handler to prevent cluttered log output
class SingleLineHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.needs_newline = False

    def emit(self, record):
        try:
            msg = self.format(record)
            if "Browser is already active" in msg:
                sys.stdout.write(f"\r{msg}")
                sys.stdout.flush()
                self.needs_newline = True
            else:
                if self.needs_newline:
                    sys.stdout.write("\n")
                    self.needs_newline = False
                sys.stdout.write(f"{msg}\n")
            self.flush()
        except Exception:
            self.handleError(record)

# Custom formatter with colors
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

    handler = SingleLineHandler()
    handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class BrowserManager:
    MAX_RETRIES = 3

    def __init__(self, serial_number):
        self.serial_number = serial_number
        self.driver = None
        self.browser_open = False

    def check_browser_status(self):
        """Проверяет состояние браузера через API и логирует результат."""
        try:
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/active',
                params={'serial_number': self.serial_number}
            )
            response.raise_for_status()
            data = response.json()
            if data['code'] == 0 and data['data']['status'] == 'Active':
                logger.info(f"Account {self.serial_number}: Browser is already active.")
                self.browser_open = True
                return True
            else:
                self.browser_open = False
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Account {self.serial_number}: Failed to check browser status due to network issue: {str(e)}")
            self.browser_open = False
            return False
        except Exception as e:
            logger.exception(f"Account {self.serial_number}: Unexpected exception while checking browser status: {str(e)}")
            self.browser_open = False
            return False

    def wait_browser_close(self):
        if self.check_browser_status():
            logger.info(f"Account {self.serial_number}: Browser already open. Waiting for closure.")
            start_time = time.time()
            timeout = 900
            while time.time() - start_time < timeout:
                if not self.check_browser_status():
                    logger.info(f"Account {self.serial_number}: Browser already closed.")
                    return True
                time.sleep(5)
            logger.warning(f"Account {self.serial_number}: Waiting time for browser closure has expired.")
            return False
        return True

    def start_browser(self):
        """Запускает браузер, проверяя состояние перед запуском и закрывая при необходимости."""
        if self.driver:
            logger.warning(f"Account {self.serial_number}: Previous driver session found. Attempting to close.")
            self.api_stop_browser()

        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                if self.check_browser_status():
                    logger.info(f"Account {self.serial_number}: Browser already open. Closing the existing browser.")
                    self.api_stop_browser()
                    time.sleep(5)
                def is_account_completed(serial_number, filename="all_quest_complete.txt"):
                    try:
                        with open(filename, "r") as file:
                            completed_accounts = file.read().splitlines()
                        return str(serial_number) in completed_accounts
                    except FileNotFoundError:
                        return False
                if is_account_completed(self.serial_number):        
                   request_url = (
                      f'http://local.adspower.net:50325/api/v1/browser/start?'
                    f'serial_number={self.serial_number}&ip_tab=0&headless=1'
                    )
                else:
                    launch_args = json.dumps([f"--disable-popup-blocking"])
                    request_url = (
                      f'http://local.adspower.net:50325/api/v1/browser/start?'
                    f'serial_number={self.serial_number}&ip_tab=0&headless=0&launch_args={launch_args}'
                    )
                response = requests.get(request_url)
                response.raise_for_status()
                data = response.json()
                if data['code'] == 0:
                    selenium_address = data['data']['ws']['selenium']
                    webdriver_path = data['data']['webdriver']
                    chrome_options = Options()
                    chrome_options.add_experimental_option("debuggerAddress", selenium_address)

                    service = Service(executable_path=webdriver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.driver.set_window_size(600, 720)
                    self.browser_open = True
                    logger.info(f"Account {self.serial_number}: Browser started successfully.")
                    return True
                else:
                    logger.warning(f"Account {self.serial_number}: Failed to start the browser. Error: {data['msg']}")
                    retries += 1
                    time.sleep(5)
            except (RequestException, WebDriverException) as e:
                logger.error(f"Account {self.serial_number}: Error starting browser: {str(e)}")
                retries += 1
                time.sleep(5)
            except Exception as e:
                logger.exception(f"Account {self.serial_number}: Unexpected exception in starting browser: {str(e)}")
                retries += 1
                time.sleep(5)
        
        logger.error(f"Account {self.serial_number}: Failed to start browser after {self.MAX_RETRIES} retries.")
        return False

    def close_browser(self):
        """Закрывает браузер, используя API при прерывании, и стандартные методы в остальных случаях."""
        try:
            if self.driver:
                try:
                    self.driver.close()  # Закрываем активное окно
                    self.driver.quit()   # Полностью закрываем сессию браузера
                    self.driver = None   # Очищаем драйвер, чтобы предотвратить повторное закрытие
                    self.browser_open = False
                    logger.info(f"Account {self.serial_number}: Browser closed successfully.")
                    return True
                except WebDriverException as e:
                    if isinstance(e, KeyboardInterrupt):
                        logger.info(f"Account {self.serial_number}: Browser close interrupted by KeyboardInterrupt. Using API to stop.")
                        return self.api_stop_browser()  # Переходим к завершению через API
                    else:
                        logger.warning(f"Account {self.serial_number}: WebDriverException while closing browser: {str(e)}")
                        self.browser_open = True  # Устанавливаем флаг, что браузер может быть еще открыт
            else:
                logger.warning(f"Account {self.serial_number}: Browser driver is already closed or not initialized.")
                self.browser_open = False
                return True  # Если драйвер уже закрыт, считаем, что завершение выполнено
        except (WebDriverException, RequestException, MaxRetryError, NewConnectionError) as e:
            # Подавляем сетевые ошибки и WebDriverException при прерывании
            if isinstance(e, KeyboardInterrupt):
                logger.info(f"Account {self.serial_number}: Browser close interrupted by KeyboardInterrupt. Suppressing network-related errors.")
                return True
            logger.exception(f"Account {self.serial_number}: General exception while closing browser: {str(e)}")
            self.browser_open = True

        # Если браузер все еще может быть активным, пробуем остановить его через API
        if self.check_browser_status():
            return self.api_stop_browser()

        # Финальная проверка статуса завершения
        if self.check_browser_status():
            logger.error(f"Account {self.serial_number}: Browser could not be closed completely.")
            return False
        else:
            logger.info(f"Account {self.serial_number}: Browser close process completed successfully.")
            return True

    def api_stop_browser(self):
        """Закрывает браузер через API, если стандартное закрытие не сработало, подавляя сетевые ошибки при прерывании."""
        try:
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/stop',
                params={'serial_number': self.serial_number}
            )
            response.raise_for_status()
            data = response.json()
            if data['code'] == 0:
                logger.info(f"Account {self.serial_number}: Browser stopped via API successfully.")
                self.browser_open = False
                return True
            else:
                logger.error(f"Account {self.serial_number}: API did not confirm browser stop. Code: {data['code']}")
                self.browser_open = True  # Считаем, что браузер может оставаться открытым
        except (RequestException, MaxRetryError, NewConnectionError, KeyboardInterrupt) as e:
            # Подавляем сетевые ошибки при прерывании и сетевые исключения
            if isinstance(e, KeyboardInterrupt):
                logger.info(f"Account {self.serial_number}: API stop interrupted by KeyboardInterrupt. Suppressing network-related errors.")
                return True
            logger.error(f"Account {self.serial_number}: Network issue while stopping browser via API: {str(e)}")
            self.browser_open = True
        except Exception as e:
            logger.exception(f"Account {self.serial_number}: Unexpected exception while stopping browser via API: {str(e)}")
            self.browser_open = True
        return False
