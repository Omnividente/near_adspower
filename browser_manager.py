import requests
import time
from selenium import webdriver
from requests.exceptions import RequestException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
import traceback
from utils import visible, stop_event
from colorama import Fore, Style
import logging

# Настройка логирования
logger = logging.getLogger("application_logger")


class BrowserManager:
    MAX_RETRIES = 3

    def __init__(self, serial_number):
        self.serial_number = serial_number
        self.driver = None
        self.headless_mode = 0 if visible.is_set() else 1

    def check_browser_status(self):
        """
        Проверяет статус активности браузера через API AdsPower.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Checking browser status via API.")
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/active',
                params={'serial_number': self.serial_number}
            )
            logger.debug(
                f"#{self.serial_number}: API request sent to check browser status.")

            response.raise_for_status()
            data = response.json()
            logger.debug(
                f"#{self.serial_number}: API response received: {data}")

            if data.get('code') == 0 and data.get('data', {}).get('status') == 'Active':
                logger.debug(f"#{self.serial_number}: Browser is active.")
                return True
            else:
                logger.debug(
                    f"#{self.serial_number}: Browser is not active or unexpected status received.")
                return False
        except WebDriverException as e:
            logger.warning(
                f"#{self.serial_number}: WebDriverException occurred while checking browser status: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
        except requests.exceptions.RequestException as e:
            logger.error(
                f"#{self.serial_number}: Failed to check browser status due to network issue: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected exception while checking browser status: {str(e)}")
            logger.debug(traceback.format_exc())
            return False

    def wait_browser_close(self):
        """
        Ожидает закрытия браузера, если он активен, с проверкой stop_event.
        """
        try:
            if not self.check_browser_status():
                logger.debug(f"#{self.serial_number}: Browser is not active, no need to wait.")
                return True

            logger.debug(f"#{self.serial_number}: Browser is active. Waiting for closure.")
            timeout = 900  # Тайм-аут на 15 минут
            start_time = time.time()

            while time.time() - start_time < timeout:
                if stop_event.is_set():
                    logger.debug(f"#{self.serial_number}: Stop event detected. Exiting wait.")
                    return False

                try:
                    if not self.check_browser_status():
                        logger.debug(f"#{self.serial_number}: Browser successfully closed.")
                        return True
                except Exception as e:
                    logger.debug(f"#{self.serial_number}: Error checking browser status: {str(e)}")

                # Используем короткий sleep с проверкой stop_event
                stop_event.wait(5)

            logger.debug(f"#{self.serial_number}: Waiting time for browser closure expired.")
            return False

        except WebDriverException as e:
            logger.debug(f"#{self.serial_number}: WebDriverException while waiting for browser closure: {str(e)}")
            return False
        except Exception as e:
            logger.debug(f"#{self.serial_number}: Unexpected error while waiting for browser closure: {str(e)}")
            return False


    def start_browser(self):
        """
        Запускает браузер через AdsPower API и настраивает Selenium WebDriver.
        """
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempting to start the browser (attempt {retries + 1}).")

                if self.check_browser_status():
                    logger.info(
                        f"#{self.serial_number}: Browser already open. Closing the existing browser.")
                    self.close_browser()
                    stop_event.wait(5)

                # Формирование URL для запуска браузера
                request_url = (
                    f'http://local.adspower.net:50325/api/v1/browser/start?'
                    f'serial_number={self.serial_number}&ip_tab=0&headless={self.headless_mode}'
                )
                logger.debug(
                    f"#{self.serial_number}: Request URL for starting browser: {request_url}")

                # Выполнение запроса к API
                response = requests.get(request_url)
                response.raise_for_status()
                data = response.json()
                logger.debug(f"#{self.serial_number}: API response: {data}")

                if data['code'] == 0:
                    selenium_address = data['data']['ws']['selenium']
                    webdriver_path = data['data']['webdriver']
                    logger.debug(
                        f"#{self.serial_number}: Selenium address: {selenium_address}, WebDriver path: {webdriver_path}")

                    # Настройка ChromeOptions
                    chrome_options = Options()
                    chrome_options.add_argument("--disable-notifications")
                    chrome_options.add_argument("--disable-popup-blocking")
                    chrome_options.add_argument("--disable-geolocation")
                    chrome_options.add_argument("--disable-translate")
                    chrome_options.add_argument("--disable-infobars")
                    chrome_options.add_argument(
                        "--disable-blink-features=AutomationControlled")
                    chrome_options.add_argument("--no-sandbox")
                    chrome_options.add_argument(
                        "--disable-background-timer-throttling")
                    chrome_options.add_experimental_option(
                        "debuggerAddress", selenium_address)

                    # Инициализация WebDriver
                    service = Service(executable_path=webdriver_path)
                    self.driver = webdriver.Chrome(
                        service=service, options=chrome_options)
                    self.driver.set_window_size(600, 720)
                    logger.info(
                        f"#{self.serial_number}: Browser started successfully.")
                    return True
                else:
                    logger.warning(
                        f"#{self.serial_number}: Failed to start the browser. Error: {data.get('msg', 'Unknown error')}")
                    retries += 1
                    stop_event.wait(5)  # Задержка перед повторной попыткой

            except requests.exceptions.RequestException as e:
                logger.error(
                    f"#{self.serial_number}: Network issue when starting browser: {str(e)}")
                retries += 1
                stop_event.wait(5)
            except WebDriverException as e:
                logger.warning(
                    f"#{self.serial_number}: WebDriverException occurred: {str(e)}")
                retries += 1
                stop_event.wait(5)
            except Exception as e:
                logger.exception(
                    f"#{self.serial_number}: Unexpected exception in starting browser: {str(e)}")
                retries += 1
                stop_event.wait(5)

        logger.error(
            f"#{self.serial_number}: Failed to start browser after {self.MAX_RETRIES} retries.")
        return False

    def close_browser(self):
        """
        Закрывает браузер с использованием WebDriver как основного способа и API как резервного.
        """
        logger.debug(
            f"#{self.serial_number}: Initiating browser closure process.")

        # Флаг для предотвращения повторного закрытия
        if getattr(self, "browser_closed", False):
            logger.debug(
                f"#{self.serial_number}: Browser already closed. Skipping closure.")
            return False

        self.browser_closed = True  # Устанавливаем флаг перед попыткой закрытия

        # Попытка закрыть браузер через WebDriver
        if not stop_event.is_set():
            try:
                if self.driver:
                    logger.debug(
                        f"#{self.serial_number}: Attempting to close Chromedriver via WebDriver.")
                    self.driver.quit()  # Закрываем все окна и завершаем сессию WebDriver
                    logger.debug(
                        f"#{self.serial_number}: Chromedriver closed successfully via WebDriver.")
            except WebDriverException as e:
                logger.debug(
                    f"#{self.serial_number}: WebDriverException while closing Chromedriver: {str(e)}")
            except Exception as e:
                logger.debug(
                    f"#{self.serial_number}: General exception while closing Chromedriver via WebDriver: {str(e)}")
            finally:
                # Устанавливаем driver в None
                self.driver = None
                logger.debug(
                    f"#{self.serial_number}: Resetting driver to None.")
        try:
            logger.debug(
                f"#{self.serial_number}: Attempting to stop browser via API as fallback.")
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/stop',
                params={'serial_number': self.serial_number},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            logger.debug(
                f"#{self.serial_number}: API response for browser stop: {data}")

            if data.get('code') == 0:
                logger.debug(
                    f"#{self.serial_number}: Browser stopped successfully via API.")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: API stop returned unexpected code: {data.get('code')}")
        except requests.exceptions.RequestException as e:
            logger.debug(
                f"#{self.serial_number}: Network issue while stopping browser via API: {str(e)}")
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Unexpected error during API stop: {str(e)}")

        logger.error(
            f"#{self.serial_number}: Browser closure process completed with errors.")
        return False
