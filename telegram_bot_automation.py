import random
import time
import json
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException, StaleElementReferenceException
from browser_manager import BrowserManager
from utils import stop_event
from colorama import Fore, Style
from urllib.parse import unquote, parse_qs
import traceback
import logging

# Настроим логирование (если не было настроено ранее)
logger = logging.getLogger("application_logger")


def load_questions_answers(filename="questions_answers.json"):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            questions_answers = json.load(file)
        return questions_answers
    except FileNotFoundError:
        logger.error(f"File '{filename}' not found.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from '{filename}': {e}")
        return {}


def dynamic_pause(min_seconds=1, max_seconds=3):
    pause_duration = random.uniform(min_seconds, max_seconds)
    if stop_event.wait(pause_duration):  # Ожидание с возможностью прерывания
        logger.debug("Dynamic pause interrupted by stop_event.")
        return


class TelegramBotAutomation:
    MAX_RETRIES = 3

    def __init__(self, serial_number, settings):
        self.serial_number = serial_number
        self.username = None
        self.balance = 0.0
        self.browser_manager = BrowserManager(serial_number)
        self.settings = settings
        if not self.browser_manager.wait_browser_close():
            logger.error(
                "Account {serial_number}: Failed to close previous browser session.")
            return
        if not self.browser_manager.start_browser():
            logger.error(f"Account {serial_number}: Failed to start browser.")
            return
        self.driver = self.browser_manager.driver

    def log_account_as_complete(self):
        try:
            with open("all_quest_complete.txt", "a", encoding="utf-8") as file:
                file.write(f"{self.serial_number}\n")
            logger.info(
                f"Account {self.serial_number}: Logged as complete in 'all_quest_complete.txt'")
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error writing to file 'all_quest_complete.txt'. Error: {e}")

    def process_mission_quests(self):
        logger.info(f"Account {self.serial_number}: Starting mission quests.")

        try:
            # Переход в раздел "Missions"
            self.open_section(3, "Missions")

            # Запускаем выполнение основных квестов и проверяем их статус
            main_quests_performed = self.check_and_complete_main_quests()

            # Если основные квесты не завершены из-за ошибки, прерываем выполнение
            if not main_quests_performed:
                logger.warning(
                    f"Account {self.serial_number}: Main quests not completed due to an error.")
                for attempt in range(5):  # Пытаемся не более 5 раз
                    if self.open_section(1, "Home"):
                        logger.info(
                            f"Account {self.serial_number}: Returned to 'Home' section.")
                        break  # Успешный переход на главную страницу, выходим из цикла
                    else:
                        # logger.warning(f"Account {self.serial_number}: 'Home' section not available, attempting to go back (Attempt {attempt + 1}).")
                        self.go_back_to_previous_page()
                        # Небольшая пауза перед следующей попыткой
                        time.sleep(2)
                else:
                    logger.error(
                        f"Account {self.serial_number}: Failed to return to 'Home' section after 5 attempts.")
                return  # Прерывание выполнения при ошибке в основных квестах

            # Запускаем выполнение дополнительных квестов и проверяем их статус
            additional_quests_completed = self.process_additional_quests_from_missions()

            # Если дополнительные квесты не завершены из-за ошибки, прерываем выполнение
            if not additional_quests_completed:
                logger.warning(
                    f"Account {self.serial_number}: Additional quests not completed due to an error.")
                for attempt in range(5):  # Пытаемся не более 5 раз
                    if self.open_section(1, "Home"):
                        logger.info(
                            f"Account {self.serial_number}: Returned to 'Home' section.")
                        break  # Успешный переход на главную страницу, выходим из цикла
                    else:
                        # logger.warning(f"Account {self.serial_number}: 'Home' section not available, attempting to go back (Attempt {attempt + 1}).")
                        self.go_back_to_previous_page()
                        # Небольшая пауза перед следующей попыткой
                        time.sleep(2)
                else:
                    logger.error(
                        f"Account {self.serial_number}: Failed to return to 'Home' section after 5 attempts.")
                return  # Прерывание выполнения при ошибке в дополнительных квестах

            # Проверка, что все квесты завершены
            if main_quests_performed and additional_quests_completed:
                # Запись номера аккаунта в файл all_quest_complete.txt
                self.log_account_as_complete()

        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error in process_mission_quests - {e}")
            # Не прерываем выполнение здесь, так как блок перехода будет вне `try`

        # Переход на главную страницу после завершения или в случае ошибки
        for attempt in range(5):  # Пытаемся не более 5 раз
            if self.open_section(1, "Home"):
                logger.info(
                    f"Account {self.serial_number}: Returned to 'Home' section.")
                break  # Успешный переход на главную страницу, выходим из цикла
            else:
                logger.warning(
                    f"Account {self.serial_number}: 'Home' section not available, attempting to go back (Attempt {attempt + 1}).")
                self.go_back_to_previous_page()
                time.sleep(2)  # Небольшая пауза перед следующей попыткой
        else:
            logger.error(
                f"Account {self.serial_number}: Failed to return to 'Home' section after 5 attempts.")

    def get_username(self):
        """
        Извлечение имени пользователя из sessionStorage.
        """
        if stop_event.is_set():
            logger.debug(
                f"#{self.serial_number}: Stop event detected. Exiting get_username.")
            return None

        try:
            # Извлекаем __telegram__initParams из sessionStorage
            logger.debug(
                f"#{self.serial_number}: Attempting to retrieve '__telegram__initParams' from sessionStorage.")
            init_params = self.driver.execute_script(
                "return sessionStorage.getItem('__telegram__initParams');"
            )
            if not init_params:
                raise Exception("InitParams not found in sessionStorage.")

            # Преобразуем данные JSON в Python-объект
            init_data = json.loads(init_params)
            logger.debug(
                f"#{self.serial_number}: InitParams successfully retrieved.")

            # Получаем tgWebAppData
            tg_web_app_data = init_data.get("tgWebAppData")
            if not tg_web_app_data:
                raise Exception("tgWebAppData not found in InitParams.")

            # Декодируем tgWebAppData
            decoded_data = unquote(tg_web_app_data)
            logger.debug(
                f"#{self.serial_number}: Decoded tgWebAppData: {decoded_data}")

            # Парсим строку параметров
            parsed_data = parse_qs(decoded_data)
            logger.debug(
                f"#{self.serial_number}: Parsed tgWebAppData: {parsed_data}")

            # Извлекаем параметр 'user' и преобразуем в JSON
            user_data = parsed_data.get("user", [None])[0]
            if not user_data:
                raise Exception("User data not found in tgWebAppData.")

            # Парсим JSON и извлекаем username
            user_info = json.loads(user_data)
            username = user_info.get("username")
            logger.debug(
                f"#{self.serial_number}: Username successfully extracted: {username}")

            return username

        except Exception as e:
            # Логируем ошибку без громоздкого Stacktrace
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"#{self.serial_number}: Error extracting Telegram username: {error_message}")
            return None

    def check_and_complete_main_quests(self):
        logger.info(f"Account {self.serial_number}: Checking main quests.")

        try:
            # Проверка выполнения всего блока основных квестов
            if self.is_quest_completed():
                logger.info(
                    f"Account {self.serial_number}: All main quests already completed.")
                return True  # Возвращаем True, если весь блок уже завершён

            # Переход к секции квестов
            quest_section = self.wait_for_element(
                By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")

            if quest_section:
                self.scroll_and_click(quest_section)
            else:
                logger.warning(
                    f"Account {self.serial_number}: Quest section not found.")
                return False  # Если секция не найдена, завершаем выполнение

            # Выполняем квесты
            # Количество квестов (или используем динамическое определение)
            quest_count = 16
            for i in range(1, quest_count + 1):
                try:
                    # Ищем основной контейнер с квестами перед каждой итерацией
                    main_container = self.wait_for_element(
                        By.XPATH,
                        "//h3[contains(text(), 'EARN') or contains(text(), 'Заработать')]/following-sibling::div"
                    )

                    if not main_container:
                        logger.warning(
                            f"Account {self.serial_number}: Main quest container not found.")
                        return False

                    # Получаем актуальный список квестов
                    quests = main_container.find_elements(By.XPATH, "./div")

                    # Проверяем, что текущий квест существует и не завершен
                    if i <= len(quests):
                        quest = quests[i - 1]
                        if not self.is_quest_button_completed(quest):
                            quest.click()
                            logger.info(
                                f"Account {self.serial_number}: Main quest button {i} clicked.")

                            # Добавляем небольшую паузу, чтобы элементы страницы обновились
                            time.sleep(2)

                            # Запускаем и завершаем квест
                            if not self.start_and_complete_quest(f"Quest {i}"):
                                logger.warning(
                                    f"Account {self.serial_number}: Quest {i} failed to complete.")
                                return False  # Прерываем выполнение и возвращаем False при ошибке

                            time.sleep(1)
                    else:
                        logger.warning(
                            f"Account {self.serial_number}: Quest {i} not found in the list.")
                        break  # Прекращаем цикл, если квестов меньше, чем ожидалось

                except Exception as e:
                    logger.warning(
                        f"Account {self.serial_number}: Error processing quest {i} - {e}")
                    return False  # Прерываем выполнение и возвращаем False при любой ошибке

            return True  # Возвращаем True, если все квесты выполнены успешно

        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error in check_and_complete_main_quests - {e}")
            return False

    def check_and_complete_main_quests2(self):
        logger.info(f"Account {self.serial_number}: Checking main quests.")

        try:
            # Проверка выполнения всего блока основных квестов
            if self.is_quest_completed():
                logger.info(
                    f"Account {self.serial_number}: All main quests already completed.")
                return True  # Возвращаем True, если весь блок уже завершён

            all_main_quests_completed = True

            # Переход к секции квестов
            quest_section = self.wait_for_element(
                By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")

            if quest_section:
                self.scroll_and_click(quest_section)
            else:
                logger.warning(
                    f"Account {self.serial_number}: Quest section not found.")
                return False  # Если секция не найдена, завершаем выполнение

            # Находим основной контейнер, содержащий квесты
            main_container = self.wait_for_element(
                By.XPATH, "//div[contains(@style, 'justify-content: space-around')]")

            # Проверяем, что контейнер найден
            if not main_container:
                logger.warning(
                    f"Account {self.serial_number}: Main quest container not found.")
                return False

            # Получаем все дочерние элементы (квесты) в контейнере
            quests = main_container.find_elements(By.XPATH, "./div")

            # Проходим по каждому квесту
            for index, quest in enumerate(quests, start=1):
                try:
                    # Если кнопка квеста найдена и квест ещё не завершён, выполняем его
                    if quests and not self.is_quest_button_completed(quests):
                        quests.click()
                        logger.info(
                            f"Account {self.serial_number}: Main quest button {i} clicked.")

                        # Запускаем и завершаем основной квест
                        if not self.start_and_complete_quest(f"Quest {i}"):
                            all_main_quests_completed = False
                            return False  # Прекращаем выполнение цикла, если возникла ошибка
                except Exception as e:
                    logger.warning(
                        f"Account {self.serial_number}: Error processing quest {index} - {e}")
                    all_main_quests_completed = False
                    return False

            return all_main_quests_completed

        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error in check_and_complete_main_quests - {e}")
            return False

    def process_additional_quests_from_missions(self):
        logger.info(
            f"Account {self.serial_number}: Starting additional quests from 'Missions'.")

        try:
            # Список разделов и названий квестов с учетом языковых вариаций
            additional_quests = {
                "TON": ["What is TON Blockchain", "что такое блокчейн TON"],
                "BNB": ["What is BNB Chain", "что такое BNB сеть"],
                "SOLANA": ["What is Solana Blockchain", "что такое блокчейн Solana"]
            }

            all_additional_quests_completed = True

            for section_name, quest_titles in additional_quests.items():
                # Переход в нужный раздел
                self.navigate_to_section_from_missions(section_name)

                # Передаем в start_and_complete_additional_quest
                if not self.start_and_complete_additional_quest(quest_titles, section_name):
                    logger.warning(
                        f"Account {self.serial_number}: Quest in '{section_name}' section not found or already completed.")
                    all_additional_quests_completed = False
                    break  # Прерываем выполнение цикла при первой ошибке

            return all_additional_quests_completed

        except Exception as e:
            # Логируем ошибку и завершаем выполнение дополнительных квестов
            logger.error(
                f"Account {self.serial_number}: Error in process_additional_quests_from_missions - {e}")
            return False

    def navigate_to_section_from_missions(self, section_name):
        try:
            # Приводим `section_name` к нижнему регистру для сравнения
            lower_section_name = section_name.lower()

            # Находим элементы, которые могут быть разделами
            sections = self.driver.find_elements(By.TAG_NAME, "h3")

            # Ищем нужный раздел среди элементов, сравнивая в нижнем регистре
            for section in sections:
                if section.text.lower() == lower_section_name:
                    # Прокручиваем к элементу, чтобы он был видимым
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView(true);", section)
                    time.sleep(1)  # Задержка для прогрузки контента

                    # Пробуем кликнуть по элементу с обработкой возможной блокировки
                    for _ in range(3):
                        try:
                            section.click()
                            logger.info(
                                f"Account {self.serial_number}: Navigated to section '{section_name}'.")
                            return  # Успешно найден и кликнут нужный раздел
                        except Exception as click_error:
                            logger.warning(
                                f"Account {self.serial_number}: Retrying click on section '{section_name}' due to interception.")
                            time.sleep(1)  # Задержка перед повторной попыткой

            logger.warning(
                f"Account {self.serial_number}: Section '{section_name}' not found.")
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error navigating to section '{section_name}'. Error: {e}")

    def check_iframe_src(self):
        """
        Проверяет, загружен ли правильный iframe по URL в атрибуте src с ожиданием.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Waiting for iframe to appear...")

            # Ждем появления iframe в течение 20 секунд
            iframe = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            logger.debug(
                f"#{self.serial_number}: Iframe detected. Checking src attribute.")

            iframe_src = iframe.get_attribute("src")

            # Проверяем, соответствует ли src ожидаемому значению
            if "tgapp.herewallet.app" in iframe_src and "tgWebAppData" in iframe_src:
                logger.debug(
                    f"#{self.serial_number}: Iframe src is valid: {iframe_src}")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: Unexpected iframe src: {iframe_src}")
                return False
        except TimeoutException:
            logger.error(
                f"#{self.serial_number}: Iframe not found within the timeout period.")
            return False
        except (WebDriverException, Exception) as e:
            logger.warning(
                f"#{self.serial_number}: Error while checking iframe src: {str(e).splitlines()[0]}")
            return False

    def start_and_complete_additional_quest(self, quest_titles, section_name=None):
        """
        This method starts and completes a quest by finding the element containing the full text of one of the quest titles.
        """
        try:
            # Нормализуем оба названия для устойчивости к регистру
            normalized_title_1 = quest_titles[0].lower()
            normalized_title_2 = quest_titles[1].lower()
            # Создаем XPATH для поиска текста, содержащего оба варианта заголовка
            xpath_expression = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ', 'abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя'), '{normalized_title_1}') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ', 'abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя'), '{normalized_title_2}')]"

            # Ищем элемент с текстом, содержащим нужный квест
            quest_element = self.wait_for_element(
                By.XPATH, xpath_expression, timeout=10)

            if quest_element:
                # Плавный скролл к элементу с динамической паузой
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", quest_element)
                time.sleep(random.uniform(1.5, 2.5))  # Динамическая пауза

                # Проверяем, завершен ли квест
                if self.is_quest_completed_for_additional(quest_element):
                    logger.info(
                        f"Account {self.serial_number}: Quest '{quest_titles[0]}' in section '{section_name}' is already completed.")
                    self.go_back_to_previous_page()  # Переход назад, если квест уже завершен
                    return True  # Завершаем выполнение, если квест уже выполнен

                # Плавное движение мыши к элементу и клик
                actions = ActionChains(self.driver)
                actions.move_to_element(quest_element)
                dynamic_pause()
                quest_element.click()
                logger.info(
                    f"Account {self.serial_number}: Quest '{quest_element.text}' found and clicked in section '{section_name}'.")
                time.sleep(random.uniform(1, 2))  # Пауза после клика

                # Выполняем действия для выполнения квеста
                self.play_video()  # Воспроизведение видео

                # Получаем текст вопроса и находим ответ
                question_text = self.get_question_text()
                dynamic_pause()
                questions_answers = load_questions_answers()
                dynamic_pause()
                answer = self.find_answer(question_text, questions_answers)
                dynamic_pause()

                # Если ответ найден, вводим его и подтверждаем
                if answer:
                    self.open_text_input_window()
                    dynamic_pause()
                    # logger.info(f"Account {self.serial_number}: Answered quest '{quest_element.text}' with '{answer}'.")
                    self.enter_answer(answer)
                    dynamic_pause()
                    self.confirm_answer_submission()
                    return True
                else:
                    logger.warning(
                        f"Account {self.serial_number}: No answer found for question '{question_text}' in quest '{quest_element.text}'.")
                    return False

            else:
                logger.warning(
                    f"Account {self.serial_number}: Quest '{quest_titles[0]}' or '{quest_titles[1]}' not found in section '{section_name}'.")
                return False

        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error in start_and_complete_additional_quest in section '{section_name}'. Error: {e}")
            return False

    def start_and_complete_quest(self, section_name=None):
        """
        This method starts and completes a quest by finding the element containing the full text of one of the quest titles.
        """
        try:
            # Запускаем и выполняем видео квеста
            self.play_video()
            dynamic_pause()

            # Получаем текст вопроса и находим ответ
            question_text = self.get_question_text()
            dynamic_pause()
            questions_answers = load_questions_answers()
            answer = self.find_answer(question_text, questions_answers)

            # Если ответ найден, вводим его и подтверждаем
            if answer:
                self.open_text_input_window()
                dynamic_pause()

                # Вводим ответ с имитацией набора текста
                self.enter_answer(answer)

                # Подтверждаем ввод с плавным движением к кнопке и кликом
                self.confirm_answer_submission()
                dynamic_pause()

                # Проверка завершения всех квестов
                if self.is_quest_completed():
                    logger.info(
                        f"Account {self.serial_number}: All quests completed.")
                    return True
                else:
                    # Если не все квесты завершены, переходим к разделу квестов
                    quest_section = self.wait_for_element(
                        By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")
                    if quest_section:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", quest_section)
                        ActionChains(self.driver).move_to_element(quest_section).pause(
                            random.uniform(0.5, 1.5)).click(quest_section).perform()
                        logger.info(
                            f"Account {self.serial_number}: Navigated to quest section.")
                        return True
                    else:
                        logger.warning(
                            f"Account {self.serial_number}: Quest section not found.")
                        return False
            else:
                logger.warning(
                    f"Account {self.serial_number}: No answer found for question '{question_text}' in quest.")
                return False

        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error in start_and_complete_quest in section '{section_name}'. Error: {e}")
            return False

    def go_back_to_previous_page(self):
        """
        Использует браузерную функцию "Назад", чтобы вернуться на предыдущую страницу.
        """
        try:
            # Используем команду браузера "Назад"
            self.driver.back()
            # logger.info(f"Account {self.serial_number}: Used browser's back function to return to the previous page.")
            time.sleep(2)  # Задержка для загрузки предыдущей страницы
            self.switch_to_iframe()
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error while using browser's back function. Error: {e}")

    def is_quest_completed_for_additional(self, quest_button):
        try:
            # Проверяем, что элемент для квеста существует
            if quest_button:
                # Пробуем найти родительский контейнер для квеста
                quest_container = quest_button.find_element(
                    By.XPATH, "./ancestor::div[1]")
                completed_text_elements = quest_container.find_elements(
                    By.XPATH, ".//*[contains(text(), 'Выполнено') or contains(text(), 'Completed')]")
                return bool(completed_text_elements)
            else:
                logger.warning(
                    f"Account {self.serial_number}: Quest button not found or not accessible.")
                return False
        except NoSuchElementException:
            logger.warning(
                f"Account {self.serial_number}: Quest container for completion check not found.")
            return False
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Unexpected error during quest completion check. Error: {e}")
            return False

    def open_text_input_window(self):
        # Ищем кнопку, которая открывает окно ввода текста, по тексту "Submit password" или "Отправить фразу"
        text_input_button = self.wait_for_element(
            By.XPATH, "//button[contains(text(), 'Submit password') or contains(text(), 'Отправить фразу')]")

        # Проверяем, если кнопка найдена
        if text_input_button:
            text_input_button.click()
            logger.info(
                f"Account {self.serial_number}: 'Submit password' to open text input window.")
            time.sleep(2)  # Небольшая задержка для загрузки окна ввода
        else:
            logger.warning(
                f"Account {self.serial_number}: 'Submit password' or 'Отправить фразу' button not found.")

    def open_section(self, position, section_name):
        try:
            # Ищем элемент по позиции внутри контейнера #here-tabs
            section_button = self.wait_for_element(
                By.XPATH, f"//*[@id='here-tabs']/div[{position}]")

            if section_button:
                # Прокручиваем к элементу, чтобы он был в зоне видимости, и нажимаем на него
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", section_button)
                section_button.click()
                logger.info(
                    f"Account {self.serial_number}: '{section_name}' section button clicked.")
                return True  # Успешный клик
            else:
                logger.warning(
                    f"Account {self.serial_number}: '{section_name}' section button not found at position {position}.")
                return False  # Элемент не найден
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error while trying to open '{section_name}' section at position {position}. Error: {e}")
            return False  # Ошибка при попытке найти или кликнуть на элемент

    def play_video(self):
        """
        Нажимает на кнопку для просмотра видео, перебирая все доступные кнопки, пока не откроется новая вкладка.
        """
        # Сохраняем текущую вкладку
        original_window = self.driver.current_window_handle

        try:
            # Находим все кнопки
            buttons = self.driver.find_elements(By.XPATH, "//button | //a")
            if not buttons:
                logger.warning(
                    f"Account {self.serial_number}: No buttons found on the page.")
                return

            logger.info(
                f"Account {self.serial_number}: Found {len(buttons)} buttons. Attempting to click each.")

            for index, button in enumerate(buttons, start=1):
                try:
                    # Проверяем текст кнопки (для логирования)
                    button_text = button.text.strip() if button.text else "No text"
                    logger.info(
                        f"Account {self.serial_number}: Trying button {index}: '{button_text}'.")

                    # Прокручиваем к кнопке
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", button
                    )
                    time.sleep(1)

                    # Пытаемся кликнуть стандартным способом
                    try:
                        button.click()
                        logger.info(
                            f"Account {self.serial_number}: Clicked button {index} using standard click.")
                    except Exception as click_error:
                        logger.warning(
                            f"Account {self.serial_number}: Standard click failed for button {index}. Trying JavaScript click. Error: {click_error}")
                        # Резервный клик через JavaScript
                        self.driver.execute_script(
                            "arguments[0].click();", button)
                        logger.info(
                            f"Account {self.serial_number}: Clicked button {index} using JavaScript click.")

                    time.sleep(3)  # Задержка для загрузки новой вкладки

                    # Проверяем, появилась ли новая вкладка
                    new_window = None
                    for window in self.driver.window_handles:
                        if window != original_window:
                            new_window = window
                            break

                    if new_window:
                        # Переключаемся на новую вкладку
                        self.driver.switch_to.window(new_window)
                        logger.info(
                            f"Account {self.serial_number}: Switched to new video window.")
                        time.sleep(5)  # Задержка для имитации просмотра видео

                        # Закрываем вкладку с видео
                        self.driver.close()
                        logger.info(
                            f"Account {self.serial_number}: Video window closed.")

                        # Возвращаемся к исходной вкладке
                        self.driver.switch_to.window(original_window)
                        logger.info(
                            f"Account {self.serial_number}: Switched back to original window.")
                        self.switch_to_iframe()
                        return  # Успешное завершение

                except Exception as button_error:
                    logger.warning(
                        f"Account {self.serial_number}: Error clicking button {index}: {button_error}")

            logger.error(
                f"Account {self.serial_number}: No buttons opened a new video window.")
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Error in play_video: {e}")

    def play_video2(self):
        # Сохраняем текущую вкладку
        original_window = self.driver.current_window_handle

        # Находим и нажимаем кнопку для просмотра видео
        video_button = self.wait_for_element(By.XPATH, "(//button | //a)[1]")

        if video_button:
            video_button.click()
            logger.info(f"Account {self.serial_number}: Video button clicked.")
            time.sleep(3)  # Задержка для загрузки новой вкладки

            # Ожидаем появления новой вкладки
            new_window = None
            for window in self.driver.window_handles:
                if window != original_window:
                    new_window = window
                    break

            # Переходим в новую вкладку
            if new_window:
                self.driver.switch_to.window(new_window)
                logger.info(
                    f"Account {self.serial_number}: Switched to new video window.")
                time.sleep(5)  # Задержка для имитации просмотра видео

                # Закрываем вкладку с видео
                self.driver.close()
                logger.info(
                    f"Account {self.serial_number}: Video window closed.")

                # Возвращаемся к исходной вкладке
                self.driver.switch_to.window(original_window)
                logger.info(
                    f"Account {self.serial_number}: Switched back to original window.")
                self.switch_to_iframe()
            else:
                logger.warning(
                    f"Account {self.serial_number}: New video window not detected.")
        else:
            logger.warning(
                f"Account {self.serial_number}: Video button not found.")

    def click_submit_password_button(self):
        # Находим кнопку по тексту "Submit password" или "Отправить фразу"
        submit_button = self.wait_for_element(
            By.XPATH, "//button[contains(text(), 'Submit password') or contains(text(), 'Отправить фразу')]")

        # Проверяем, если кнопка найдена
        if submit_button:
            submit_button.click()
            logger.info(
                f"Account {self.serial_number}: 'Submit password' or 'Отправить фразу' button clicked.")
        else:
            logger.warning(
                f"Account {self.serial_number}: 'Submit password' or 'Отправить фразу' button not found.")

    def scroll_and_click(self, element):
        self.driver.execute_script(
            "arguments[0].scrollIntoView(true);", element)
        time.sleep(2)
        element.click()

    def is_quest_completed(self):
        """
        Проверяет, завершён ли квест, на основе текста "Выполнено" или "Completed", с тремя попытками поиска
        и навигацией к секции.
        """
        max_attempts = 3  # Максимальное количество попыток
        for attempt in range(1, max_attempts + 1):
            try:
                # logger.info(f"Attempt {attempt}/{max_attempts} to check if quest is completed.")

                # Находим секцию квеста по тексту
                quest_section = self.wait_for_element(
                    By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")

                if quest_section:
                    # Прокручиваем к секции, чтобы она была видимой
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", quest_section)
                    logger.info(
                        f"Quest section found and navigated to on attempt {attempt}.")

                    # Поднимаемся к общему контейнеру
                    quest_container = quest_section.find_element(
                        By.XPATH, "./ancestor::div[contains(@style, 'position: relative')]")

                    # Проверяем наличие текста "Completed" или "Выполнено" в контейнере
                    completed_text_element = quest_container.find_elements(
                        By.XPATH, ".//*[contains(text(), 'Completed') or contains(text(), 'Выполнено')]")

                    if completed_text_element:
                        logger.info(
                            f"Quest is marked as completed on attempt {attempt}.")
                        return True
                    elif attempt == max_attempts:
                        logger.info(
                            "Quest is not marked as completed after all attempts.")
                        return False
                elif attempt == max_attempts:
                    logger.warning(
                        "Quest section not found after all attempts.")
                    return False

            except Exception as e:
                logger.error(
                    f"Error in attempt {attempt}/{max_attempts} of is_quest_completed: {e}")

            # Задержка перед следующей попыткой
            if attempt < max_attempts:
                time.sleep(2)

        # Если все попытки не увенчались успехом, возвращаем False
        logger.error("All attempts to check if quest is completed failed.")
        return False

    def is_quest_button_completed(self, quest_button):
        button_html = quest_button.get_attribute("outerHTML")
        return "/assets/hot-check-BAJtIC8H.webp" in button_html

    def get_question_text(self):
        # Находим последний открытый div, в котором находится элемент h3, и берем его текст
        question_text_element = self.wait_for_element(
            By.XPATH, "//div[contains(@class, 'react-modal-sheet-content')]//h3")
        return question_text_element.text.lower() if question_text_element else None

    def find_answer(self, question_text, questions_answers):
        # Приводим текст вопроса к нижнему регистру для единообразия
        question_text_lower = question_text.lower()

        # Сортируем ключи из JSON по длине в обратном порядке, чтобы более длинные вопросы проверялись первыми
        sorted_questions = sorted(
            questions_answers.keys(), key=len, reverse=True)

        # Ищем полное совпадение с более длинными вопросами
        for key in sorted_questions:
            if key.lower() in question_text_lower:
                # Возвращаем ответ при первом совпадении
                return questions_answers[key]

        # Если ничего не найдено, возвращаем None
        return None

    def enter_answer(self, answer):
        # Ищем первое поле input в пределах окна ввода пароля, ориентируясь на структуру
        answer_input = self.wait_for_element(
            By.XPATH, "//div[@id='root']//input")

        # Проверяем, найдено ли поле ввода
        if answer_input:
            # Вводим ответ символ за символом с небольшой задержкой
            for char in answer:
                answer_input.send_keys(char)
                # Задержка для эмуляции ввода пользователем
                time.sleep(random.uniform(0.1, 0.3))
            logger.info(
                f"Account {self.serial_number}: Answer '{answer}' entered.")
        else:
            logger.warning(
                f"Account {self.serial_number}: Answer input field not found.")

        # Ищем кнопку отправки в пределах окна, не завися от классов
        submit_button = self.wait_for_element(
            By.XPATH, "//div[@id='root']//button")

        # Ждем, пока кнопка станет активной, затем кликаем
        if submit_button:
            while not submit_button.is_enabled():
                # Проверяем каждые 0.5 секунды, активна ли кнопка
                time.sleep(0.5)
            submit_button.click()
            logger.info(
                f"Account {self.serial_number}: Submit button clicked.")
        else:
            logger.warning(
                f"Account {self.serial_number}: Submit button not found.")

    def confirm_answer_submission(self):
        try:
            # Находим контейнер, который содержит кнопку
            confirmation_container = self.wait_for_element(
                By.CSS_SELECTOR, "div.react-modal-sheet-scroller", timeout=120)

            # Ищем первую кнопку внутри контейнера
            confirm_button = confirmation_container.find_element(
                By.TAG_NAME, "button")

            # Прокручиваем к кнопке, чтобы она была видимой
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", confirm_button)
            time.sleep(1)  # Небольшая задержка после прокрутки

            # Пытаемся выполнить стандартный клик по кнопке
            confirm_button.click()
            logger.info(
                f"Account {self.serial_number}: Confirmation button clicked.")

        except Exception as e:
            logger.warning(
                f"Account {self.serial_number}: Could not click confirmation button. Error: {e}")

    def wait_for_element(self, by, value, parent=None, timeout=10):
        """
        Ожидает появления элемента на странице и возвращает его.
        Если указан parent, поиск будет в пределах указанного родителя.
        """
        try:
            if parent:
                WebDriverWait(parent, timeout).until(
                    lambda _: parent.find_element(by, value))
                return parent.find_element(by, value)
            else:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value)))
                return self.driver.find_element(by, value)
        except TimeoutException:
            # logger.warning(f"Could not find element by {by} with value {value} in {timeout} seconds.")
            return None

    def navigate_to_bot(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            if stop_event.is_set():  # Проверка на прерывание
                logger.debug(
                    f"Account {self.serial_number}: Navigation to Telegram interrupted by stop_event.")
                return False
            try:
                self.driver.get('https://web.telegram.org/k/')
                logger.debug(
                    f"Account {self.serial_number}: Navigated to Telegram web.")
                self.close_extra_windows()
                if stop_event.wait(random.randint(5, 7)):  # Ожидание вместо time.sleep
                    logger.debug(
                        f"Account {self.serial_number}: Navigation to Telegram interrupted during wait.")
                    return False
                return True
            except (WebDriverException, TimeoutException) as e:
                logger.debug(
                    f"Account {self.serial_number}: Error navigating to Telegram (attempt {retries + 1}): {str(e)}")
                retries += 1
                if stop_event.wait(5):  # Ожидание вместо time.sleep
                    logger.debug(
                        f"Account {self.serial_number}: Navigation to Telegram interrupted during retry wait.")
                    return False
        logger.debug(
            f"Account {self.serial_number}: Exceeded maximum retries ({self.MAX_RETRIES}). Navigation failed.")
        return False

    def switch_to_iframe(self):
        """
        This method switches to the first iframe on the page, if available.
        """
        try:
            # Возвращаемся к основному контенту страницы
            self.driver.switch_to.default_content()

            # Ищем все iframes на странице
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                # Переключаемся на первый iframe
                self.driver.switch_to.frame(iframes[0])
                # logger.info(f"Account {self.serial_number}: Switched to iframe.")
                return True
            else:
                logger.warning(
                    f"Account {self.serial_number}: No iframe found to switch.")
                return False
        except NoSuchElementException:
            logger.warning(f"Account {self.serial_number}: No iframe found.")
            return False
        except Exception as e:
            logger.error(
                f"Account {self.serial_number}: Unexpected error while switching to iframe: {str(e)}")
            return False

    def close_extra_windows(self):
        try:
            current_window = self.driver.current_window_handle
            for window in self.driver.window_handles:
                if window != current_window:
                    self.driver.switch_to.window(window)
                    self.driver.close()
                    self.driver.switch_to.window(current_window)
        except WebDriverException as e:
            logger.warning(
                f"Account {self.serial_number}: Error closing extra windows: {str(e)}")

    def send_message(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            if stop_event.is_set():  # Проверка на прерывание
                logger.debug(
                    f"Account {self.serial_number}: Message sending interrupted by stop_event.")
                return False
            try:
                chat_input_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/input[1]')
                if chat_input_area:
                    chat_input_area.click()

                    group_url = self.settings.get(
                        'TELEGRAM_GROUP_URL', 'https://t.me/CryptoProjects_sbt')
                    chat_input_area.send_keys(group_url)

                    search_area = self.wait_for_element(
                        By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/ul[1]/a[1]/div[1]')
                    if search_area:
                        search_area.click()
                        logger.debug(
                            f"Account {self.serial_number}: Message sent to group.")
                if stop_event.wait(random.randint(5, 7)):  # Ожидание вместо time.sleep
                    logger.debug(
                        f"Account {self.serial_number}: Message sending interrupted during wait.")
                    return False
                return True
            except (NoSuchElementException, WebDriverException) as e:
                logger.debug(
                    f"Account {self.serial_number}: Error in send_message (attempt {retries + 1}): {str(e)}")
                retries += 1
                if stop_event.wait(5):  # Ожидание вместо time.sleep
                    logger.debug(
                        f"Account {self.serial_number}: Message sending interrupted during retry wait.")
                    return False
        logger.debug(
            f"Account {self.serial_number}: Exceeded maximum retries ({self.MAX_RETRIES}). Message sending failed.")
        return False

    def click_link(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempt {retries + 1} to click link.")

                # Получаем ссылку из настроек
                bot_link = self.settings.get(
                    'BOT_LINK', 'https://t.me/herewalletbot/app?startapp=286283')
                logger.debug(f"#{self.serial_number}: Bot link: {bot_link}")

                # Ожидание перед началом поиска
                # Увеличенное ожидание перед первой проверкой
                stop_event.wait(3)

                scroll_attempts = 0
                max_scrolls = 20  # Максимальное количество прокруток

                while scroll_attempts < max_scrolls:
                    # Ожидаем появления всех ссылок, начинающихся с https://t.me
                    try:
                        links = WebDriverWait(self.driver, 5).until(
                            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='https://t.me']"))
                    except TimeoutException:
                        logger.warning(
                            f"#{self.serial_number}: Links did not load in time.")
                        break

                    logger.debug(
                        f"#{self.serial_number}: Found {len(links)} links starting with 'https://t.me/'.")

                    # Прокручиваемся к каждой ссылке поочередно
                    for link in links:
                        href = link.get_attribute("href")
                        if bot_link in href:
                            logger.debug(
                                f"#{self.serial_number}: Found matching link: {href}")

                            # Скроллинг к нужной ссылке
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", link)
                            # Небольшая задержка после прокрутки
                            stop_event.wait(0.5)

                            # Клик по ссылке
                            link.click()
                            logger.debug(
                                f"#{self.serial_number}: Link clicked successfully.")
                            stop_event.wait(2)

                            # Поиск и клик по кнопке запуска
                            launch_button = self.wait_for_element(
                                By.CSS_SELECTOR, "button.popup-button.btn.primary.rp", timeout=5)
                            if launch_button:
                                logger.debug(
                                    f"#{self.serial_number}: Launch button found. Clicking it.")
                                launch_button.click()
                                logger.debug(
                                    f"#{self.serial_number}: Launch button clicked.")

                            # Проверка iframe
                            if self.check_iframe_src():
                                logger.info(
                                    f"#{self.serial_number}: App loaded successfully.")

                                # Случайная задержка перед переключением на iframe
                                sleep_time = random.randint(3, 5)
                                logger.debug(
                                    f"#{self.serial_number}: Sleeping for {sleep_time} seconds before switching to iframe.")
                                stop_event.wait(sleep_time)

                                # Переключение на iframe
                                self.switch_to_iframe()
                                logger.debug(
                                    f"#{self.serial_number}: Switched to iframe successfully.")
                                return True
                            else:
                                logger.warning(
                                    f"#{self.serial_number}: Iframe did not load expected content.")
                                raise Exception(
                                    "Iframe content validation failed.")

                    # Если нужная ссылка не найдена, прокручиваемся к первому элементу
                    logger.debug(
                        f"#{self.serial_number}: Scrolling up (attempt {scroll_attempts + 1}).")
                    if links:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'start' });", links[0])
                    else:
                        logger.debug(
                            f"#{self.serial_number}: No links found to scroll to.")
                        break

                    # Небольшая задержка для загрузки контента
                    stop_event.wait(0.5)
                    scroll_attempts += 1

                    # Проверяем позицию страницы
                    current_position = self.driver.execute_script(
                        "return window.pageYOffset;")
                    logger.debug(
                        f"#{self.serial_number}: Current scroll position: {current_position}")
                    if current_position == 0:  # Если достигнут верх страницы
                        logger.debug(
                            f"#{self.serial_number}: Reached the top of the page.")
                        break

                # Если не удалось найти ссылку
                logger.debug(
                    f"#{self.serial_number}: No matching link found after scrolling through all links.")
                retries += 1
                stop_event.wait(5)

            except (NoSuchElementException, WebDriverException, TimeoutException) as e:
                logger.debug(
                    f"#{self.serial_number}: Failed to click link or interact with elements (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                stop_event.wait(5)
            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error during click_link: {str(e).splitlines()[0]}")
                break

        logger.error(
            f"#{self.serial_number}: All attempts to click link failed after {self.MAX_RETRIES} retries.")
        return False

    def find_timer_element(self):
        try:
            if stop_event.is_set():  # Проверка на прерывание
                logger.debug(
                    f"Account {self.serial_number}: Timer element search interrupted by stop_event.")
                return None

            # Находим контейнер прогресса по уникальным признакам
            progress_container = self.wait_for_element(
                By.XPATH, "//div[contains(@style, 'display: flex;') and contains(@style, 'height: 8px;')]")

            if progress_container:
                # Находим вложенный элемент с процентом ширины (заполненности)
                progress_element = progress_container.find_element(
                    By.XPATH, "./div[2]")
                style = progress_element.get_attribute("style")

                # Извлекаем значение процента заполнения из стиля
                width_value = None
                if "width" in style:
                    try:
                        width_str = style.split(
                            "width:")[1].split("%")[0].strip()
                        width_value = float(width_str)
                        logger.debug(
                            f"Account {self.serial_number}: Progress percentage found - {width_value}%.")
                    except ValueError:
                        logger.debug(
                            f"Account {self.serial_number}: Unable to parse width value from style: {style}.")
                else:
                    logger.debug(
                        f"Account {self.serial_number}: Width attribute not found in style: {style}.")

                return width_value

            else:
                logger.debug(
                    f"Account {self.serial_number}: Progress container not found.")
                return None

        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: Error retrieving progress percentage. Error: {e}.")
            return None

    def farming(self):
        if stop_event.is_set():  # Проверка на прерывание перед началом
            logger.debug(
                f"Account {self.serial_number}: Farming process interrupted by stop_event.")
            return

        self.open_storage_section()

        try:
            # Ищем элемент таймера с помощью find_timer_element, который возвращает процент заполнения
            # Передаём stop_event для возможности прерывания
            percent = self.find_timer_element()
            if percent is not None:
                if percent == 100.0:
                    logger.info(
                        f"Account {self.serial_number}: Timer is at 100%. Attempting to claim.")
                    if stop_event.wait(5):  # Ожидание вместо time.sleep
                        logger.debug(
                            f"Account {self.serial_number}: Farming process interrupted during wait before claiming.")
                        return
                    self.claim_hot()
                else:
                    logger.info(
                        f"Account {self.serial_number}: Timer percentage is not 100% (current: {percent}%).")
            else:
                logger.info(
                    f"Account {self.serial_number}: Timer element not found.")
        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: An error occurred while processing the timer: {e}.")

    def claim_hot(self):
        try:
            # Находим кнопку "News" с уникальным признаком '--Pink-Primary' в её стиле
            news_button = next((btn for btn in self.driver.find_elements(By.TAG_NAME, "button")
                                if "--Pink-Primary" in btn.get_attribute("style") and btn.is_displayed()), None)

            # Если нашли кнопку "News", нажимаем её
            if news_button:
                news_button.click()
                logger.info(
                    f"Account {self.serial_number}: 'News' button clicked. Waiting for 'Claim HOT' button to appear.")
                if stop_event.wait(2):  # Ожидание вместо time.sleep
                    logger.debug(
                        f"Account {self.serial_number}: Claim HOT process interrupted during initial wait.")
                    return

                # Ожидаем, пока на том же месте появится кнопка "Claim HOT"
                WebDriverWait(self.driver, 20).until(
                    lambda d: any(btn.is_displayed() and "--Pink-Primary" not in btn.get_attribute("style")
                                  for btn in d.find_elements(By.TAG_NAME, "button"))
                )

            # Теперь ищем и нажимаем кнопку "Claim HOT"
            claim_button = next((btn for btn in self.driver.find_elements(By.TAG_NAME, "button")
                                if "--Pink-Primary" not in btn.get_attribute("style") and btn.is_displayed()), None)

            if claim_button:
                claim_button.click()
                logger.info(
                    f"Account {self.serial_number}: 'Claim HOT' button clicked.")

                # Ожидаем обновления баланса, проверяя каждые 5 секунд, пока не истекут 3 минуты (180 секунд)
                initial_balance = self.get_update_balance()
                start_time = time.time()

                while time.time() - start_time < 180:  # 3 минуты в секундах
                    if stop_event.is_set():  # Проверка на прерывание
                        logger.debug(
                            f"Account {self.serial_number}: Claim HOT process interrupted during balance update.")
                        return

                    current_balance = self.get_update_balance()
                    if current_balance != initial_balance:
                        logger.info(
                            f"Account {self.serial_number}: Balance updated successfully to {current_balance}.")
                        break

                    if stop_event.wait(5):  # Ожидание вместо time.sleep
                        logger.debug(
                            f"Account {self.serial_number}: Claim HOT process interrupted during balance check.")
                        return
                else:
                    logger.info(
                        f"Account {self.serial_number}: Balance update not detected within 3 minutes.")
            else:
                logger.info(
                    f"Account {self.serial_number}: 'Claim HOT' button not found.")

        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: Error in claim_hot function. Error: {e}")

    def get_balance(self):
        try:
            if stop_event.is_set():  # Проверка на прерывание перед началом
                logger.debug(
                    f"Account {self.serial_number}: Balance retrieval process interrupted by stop_event.")
                return None, None

            if stop_event.is_set():  # Проверка перед поиском баланса
                logger.debug(
                    f"Account {self.serial_number}: Balance retrieval process interrupted after username check.")
                return None

            # Поиск баланса
            balance_element = self.wait_for_element(
                By.XPATH, "//p[contains(@style, 'display: inline-block; font-size: 18px;')]")
            if balance_element:
                balance_text = balance_element.text
                try:
                    # Преобразуем баланс в число с плавающей точкой
                    balance = float(balance_text.replace(",", "").strip())
                    logger.info(
                        f"Account {self.serial_number}: Balance found - {balance}")
                except ValueError:
                    balance = None
                    logger.info(
                        f"Account {self.serial_number}: Failed to convert balance text '{balance_text}' to a float.")
            else:
                balance = None
                logger.info(
                    f"Account {self.serial_number}: Balance not found.")

            if stop_event.is_set():  # Проверка перед обновлением таблицы
                logger.debug(
                    f"Account {self.serial_number}: Balance retrieval process interrupted before updating the table.")
                return balance
            return balance

        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: Error retrieving username and balance. Error: {e}")
            return None, None

    def open_storage_section(self):
        try:
            if stop_event.is_set():  # Проверка на прерывание перед началом
                logger.debug(
                    f"Account {self.serial_number}: Opening 'Storage' section interrupted by stop_event.")
                return

            # Используем XPath для поиска контейнера с курсором pointer, содержащего тег h4
            storage_button = self.wait_for_element(
                By.XPATH, "//div[contains(@style, 'cursor: pointer') and .//h4]")

            if storage_button:
                # Прокручиваем к элементу с плавной анимацией
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", storage_button)

                if stop_event.is_set():  # Проверка на прерывание перед паузой
                    logger.debug(
                        f"Account {self.serial_number}: Opening 'Storage' section interrupted after scrolling.")
                    return

                dynamic_pause()  # Динамическая пауза перед кликом

                if stop_event.is_set():  # Проверка на прерывание перед кликом
                    logger.debug(
                        f"Account {self.serial_number}: Opening 'Storage' section interrupted before click.")
                    return

                # Эмулируем плавное наведение и клик для более естественного поведения
                actions = ActionChains(self.driver)
                actions.move_to_element(storage_button).pause(
                    0.5).click(storage_button).perform()
                logger.info(
                    f"Account {self.serial_number}: 'Storage' button clicked.")
            else:
                logger.info(
                    f"Account {self.serial_number}: 'Storage' button not found.")
        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: Error while trying to click 'Storage' button. Error: {e}")

    def get_update_balance(self):
        try:
            if stop_event.is_set():  # Проверка на прерывание перед началом
                logger.debug(
                    f"Account {self.serial_number}: HOT balance retrieval interrupted by stop_event.")
                return 0.0

            # Ищем все элементы <p> на странице
            elements = self.driver.find_elements(By.TAG_NAME, "p")

            for element in elements:
                if stop_event.is_set():  # Проверка на прерывание внутри цикла
                    logger.debug(
                        f"Account {self.serial_number}: HOT balance retrieval interrupted while iterating elements.")
                    return 0.0

                # Проверяем текст элемента
                if "HOT Баланс" in element.text or "HOT Balance" in element.text:
                    # Если текст найден, переходим к родительскому контейнеру
                    parent_container = element.find_element(
                        By.XPATH, "./parent::div")

                    # Находим второй <p>, содержащий баланс
                    balance_value_element = parent_container.find_element(
                        By.XPATH, ".//p[2]")

                    # Извлекаем текст и преобразуем его в число
                    balance_text = balance_value_element.text.strip()
                    try:
                        balance = float(balance_text.replace(",", ""))
                        logger.info(
                            f"Account {self.serial_number}: HOT Balance found: {balance}")
                        return balance
                    except ValueError:
                        logger.info(
                            f"Account {self.serial_number}: Could not convert balance text to number: {balance_text}")
                        return 0.0

            # Если ни один из элементов не содержит нужного текста
            logger.info(
                f"Account {self.serial_number}: HOT Balance text not found.")
            return 0.0

        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: Error retrieving HOT balance. Error: {e}")
            return 0.0

    def get_remaining_time(self):
        try:
            if stop_event.is_set():  # Проверка на прерывание перед началом
                logger.debug(
                    f"Account {self.serial_number}: Remaining time retrieval interrupted by stop_event.")
                return None

            # Ищем все элементы <p> и проверяем, если они вообще найдены
            time_elements = self.driver.find_elements(By.TAG_NAME, "p")
            if not time_elements:
                logger.info(
                    f"Account {self.serial_number}: No <p> elements found on the page.")
                return None

            for element in time_elements:
                if stop_event.is_set():  # Проверка на прерывание внутри цикла
                    logger.debug(
                        f"Account {self.serial_number}: Remaining time retrieval interrupted during element processing.")
                    return None

                time_text = element.text.strip()
                logger.debug(
                    f"Account {self.serial_number}: Found time text - '{time_text}'")

                # Проверка формата "Xh Ym" или "Xч Ym" (часы и минуты)
                match_hours_minutes = re.search(
                    r"(\d+)\s*[hч]\s*(\d+)\s*[mм]", time_text, re.IGNORECASE)
                if match_hours_minutes:
                    hours = int(match_hours_minutes.group(1))
                    minutes = int(match_hours_minutes.group(2))
                    remaining_time = hours * 3600 + minutes * 60
                    break

                # Проверка формата "Xh" или "Xч" (только часы)
                match_hours_only = re.search(
                    r"(\d+)\s*[hч]", time_text, re.IGNORECASE)
                if match_hours_only:
                    hours = int(match_hours_only.group(1))
                    remaining_time = hours * 3600
                    break

                # Проверка формата "Ym" или "Yм" (только минуты)
                match_minutes_only = re.search(
                    r"(\d+)\s*[mм]", time_text, re.IGNORECASE)
                if match_minutes_only:
                    minutes = int(match_minutes_only.group(1))
                    remaining_time = minutes * 60

                    # Если минутное значение равно 0, устанавливаем оставшееся время на 5 минут
                    if minutes == 0:
                        remaining_time = 5 * 60
                    break
            else:
                logger.info(
                    f"Account {self.serial_number}: No valid time format found in <p> elements.")
                return None

            # Добавляем случайное время от 5 до 10 минут
            additional_seconds = random.randint(5, 10) * 60
            remaining_time += additional_seconds

            # Преобразуем оставшееся время в формат HH:MM:SS
            hours, remainder = divmod(remaining_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            schedule_time = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

            logger.info(
                f"Account {self.serial_number}: Total remaining time with random addition - {schedule_time}")
            return schedule_time

        except Exception as e:
            logger.debug(
                f"Account {self.serial_number}: Error retrieving remaining time. Error: {e}")
            return None

    def run_account_registration_process(self):
        """
        Основной процесс регистрации нового аккаунта.
        Последовательно выполняет шаги регистрации, включая создание аккаунта, 
        закрытие обучающих попапов, нажатие кнопки "Продолжить" и подписку на Telegram-канал.
        """
        try:
            # Шаг 1: Подписка на Telegram-канал
            logger.info("Подписываемся на Telegram-канал...")
            self.subscribe_to_telegram_channel()
            self.switch_to_iframe()
            # Шаг 2: Создание нового аккаунта
            try:
                # Нажимаем на кнопку "Создать новый аккаунт"
                create_account_button = self.wait_for_element(
                    By.XPATH,
                    "//button[contains(text(), 'Создать новый аккаунт') or contains(text(), 'Create new account')]"
                )
                if create_account_button:
                    create_account_button.click()
                    logger.info("Нажата кнопка 'Создать новый аккаунт'.")
                else:
                    logger.warning(
                        "Кнопка 'Создать новый аккаунт' не найдена.")
                    return False

                # Проверяем наличие заголовка страницы "Создать аккаунт"
                header_element = self.wait_for_element(
                    By.XPATH,
                    "//h1[contains(text(), 'Создать аккаунт') or contains(text(), 'Create Account')]",
                    timeout=10
                )
                if not header_element:
                    logger.warning(
                        "Заголовок страницы 'Создать аккаунт' не найден.")
                    return False

                # Сохраняем никнейм
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                nickname = None
                for input_element in inputs:
                    if input_element.get_attribute("disabled") and ".tg" in input_element.get_attribute("value"):
                        nickname = input_element.get_attribute("value")
                        break

                if nickname:
                    logger.info(f"Найден никнейм: {nickname}")
                else:
                    logger.warning("Никнейм не найден.")
                    return False

                # Найти контейнер seed-фразы и сохранить текст
                seed_phrase_container = self.wait_for_element(
                    By.XPATH,
                    "//div[contains(@style, 'text-align: left;') and contains(@style, 'filter: blur')]"
                )
                if seed_phrase_container:
                    seed_phrase_container.click()  # Отображаем текст seed-фразы
                    seed_phrase = seed_phrase_container.text
                    logger.info(f"Найдена seed-фраза: {seed_phrase}")
                else:
                    logger.warning("Контейнер с seed-фразой не найден.")
                    return False

                # Подтвердить создание аккаунта
                confirm_creation_button = self.wait_for_element(
                    By.XPATH,
                    "//button[contains(text(), 'Создать') or contains(text(), 'Create')]"
                )
                if confirm_creation_button:
                    confirm_creation_button.click()
                    logger.info(
                        "Нажата кнопка 'Создать' для завершения создания аккаунта.")
                else:
                    logger.warning(
                        "Кнопка подтверждения создания аккаунта не найдена.")
                    return False

                # Сохранение информации об аккаунте
                self.save_account_info(nickname, seed_phrase)

            except Exception as e:
                logger.error(f"Ошибка при создании аккаунта: {e}")
                return False

            # Шаг 3: Закрытие обучающих попапов
            logger.info("Ждем и закрываем обучающие попапы...")
            self.close_tutorial_popup()

            # Шаг 4: Нажатие кнопки "Продолжить" до недоступности
            logger.info("Нажимаем кнопку 'Продолжить', пока она доступна...")
            self.click_continue_button_until_unavailable()

            # Шаг 4: Жмем назад
            time.sleep(5)
            self.click_until_disappear()

            # Завершение процесса
            logger.info(
                "Процесс регистрации нового аккаунта завершен успешно.")
            return True

        except Exception as e:
            logger.error(f"Ошибка в процессе регистрации нового аккаунта: {e}")
            return False

    def is_new_account_page(self):
        try:
            # Проверка заголовка страницы
            header = self.wait_for_element(
                By.XPATH, "//h1[contains(text(), 'HOT Wallet')]", timeout=5)
            if not header:
                return False

            # Проверка кнопки «Создать новый аккаунт» или «Create New Account»
            create_account_button = self.wait_for_element(
                By.XPATH,
                "//button[contains(text(), 'Создать новый аккаунт') or contains(text(), 'Create New Account')]",
                timeout=5
            )
            if not create_account_button:
                return False

            # Если оба элемента найдены, возвращаем True
            return True

        except Exception:
            # Любая другая ошибка приведет к возврату False
            return False

    def save_account_info(self, nickname, seed_phrase):
        filename = "all_accounts_info.txt"
        with open(filename, "a") as f:
            f.write(f"Nickname: {nickname}\n")
            f.write(f"Seed Phrase: {seed_phrase}\n")
            f.write("----\n")  # Разделитель между аккаунтами
        logger.info(
            f"Account information for {nickname} appended to {filename}")

    def close_tutorial_popup(self):
        """
        Закрывает обучающий попап, дожидаясь появления div-элементов с нужными признаками в течение 2 минут.
        """
        try:
            # Условие для ожидания элемента
            def tutorial_popup_condition(driver):
                buttons = driver.find_elements(By.TAG_NAME, "div")
                for button in buttons:
                    if button.value_of_css_property("z-index") == "1002" and \
                            ("Клейм" in button.text or "Claim" in button.text):
                        return button  # Возвращает найденный элемент
                return None

            # Ожидаем элемент в течение 2 минут (120 секунд)
            target_button = WebDriverWait(
                self.driver, 120).until(tutorial_popup_condition)

            # Если элемент найден, кликаем по нему
            time.sleep(5)
            if target_button:
                target_button.click()
                logger.info("Обучающий попап закрыт.")
            else:
                logger.warning("Обучающий попап не найден.")

        except TimeoutException:
            logger.error("Обучающий попап не появился в течение 2 минут.")
        except NoSuchElementException:
            logger.error("Error: Обучающий попап не найден.")
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка при закрытии обучающего попапа: {e}")

    def click_continue_button_until_unavailable(self, max_attempts=20):
        attempts = 0
        while attempts < max_attempts:
            try:
                # Находим контейнер с кнопкой "Продолжить"
                container = self.driver.find_element(
                    By.XPATH, "//div[contains(@style, 'display: flex') and contains(@style, 'justify-content: space-between')]")

                # Находим все кнопки внутри контейнера
                buttons = container.find_elements(By.TAG_NAME, "button")

                # Если кнопки найдены, кликаем по первой доступной
                if buttons:
                    for button in buttons:
                        try:
                            button.click()
                            logger.info(
                                f"Clicked 'Continue' button. Attempt {attempts + 1}.")
                            break
                        except ElementNotInteractableException:
                            continue
                else:
                    logger.info("No 'Continue' button found in the container.")
                    break

                # Увеличиваем счётчик попыток
                attempts += 1
                time.sleep(2)

            except NoSuchElementException:
                logger.info("Кнопка 'Продолжить' больше не доступна.")
                break

        if attempts == max_attempts:
            logger.warning(
                "Достигнуто максимальное количество попыток нажатия кнопки 'Продолжить'.")
        time.sleep(3)

    def subscribe_to_telegram_channel(self):
        try:
            # Сохраняем текущую вкладку
            original_window = self.driver.current_window_handle

            # URL канала
            channel_url = "https://web.telegram.org/k/#@hotonnear"

            # Открываем новую вкладку
            self.driver.execute_script(
                f"window.open('{channel_url}', '_blank');")
            logger.info(
                "Открыли новую вкладку для подписки на Telegram-канал.")

            # Переходим в новую вкладку
            self.driver.switch_to.window(self.driver.window_handles[-1])
            logger.info("Переключились на вкладку с Telegram-каналом.")

            # Ждём загрузки страницы
            self.wait_for_element(
                By.CSS_SELECTOR, ".btn-primary.btn-color-primary.chat-join.rp", timeout=10)

            # Находим и нажимаем кнопку "Подписаться"
            join_button = self.driver.find_element(
                By.CSS_SELECTOR, ".btn-primary.btn-color-primary.chat-join.rp")
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", join_button)
            join_button.click()
            logger.info("Успешно подписались на Telegram-канал.")

            # Ждём завершения действий
            time.sleep(5)

            # Закрываем вкладку и возвращаемся на исходную
            self.driver.close()
            logger.info("Закрыли вкладку с Telegram-каналом.")
            self.driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Ошибка при подписке на Telegram-канал: {e}")
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(original_window)

    def click_until_disappear(self):
        """
        Нажимает любую кнопку в окне до тех пор, пока окно не исчезнет,
        затем ожидает появления элемента хранилища.
        """
        try:
            # Нажимаем кнопки до тех пор, пока окно не исчезнет
            while True:
                try:
                    # Проверяем, существует ли окно
                    popup = self.driver.find_element(
                        By.XPATH, "//div[contains(@class, 'popup') or contains(@class, 'modal')]")

                    # Находим все кнопки внутри окна
                    buttons = popup.find_elements(By.TAG_NAME, "button")

                    if buttons:
                        for button in buttons:
                            try:
                                # Скроллим к кнопке и нажимаем
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                                button.click()
                                logger.info("Кнопка найдена и нажата.")
                                time.sleep(2)  # Ждём обновления после нажатия
                                break  # Переходим к следующей итерации
                            except Exception as e:
                                logger.warning(
                                    f"Ошибка при нажатии кнопки: {e}")
                                continue
                    else:
                        logger.info(
                            "Кнопки в окне не найдены. Проверяем окно снова.")

                except NoSuchElementException:
                    # Если окно исчезло, выходим из цикла
                    logger.info(
                        "Окно исчезло. Переходим к ожиданию хранилища.")
                    break

            # Переходим назад на предыдущую страницу
            time.sleep(5)
            self.go_back_to_previous_page()

            # Ожидание появления хранилища (до 3 минут)
            try:
                logger.info(
                    "Ожидаем появления элемента хранилища до 3 минут...")
                storage_element = WebDriverWait(self.driver, 180).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//div[contains(@style, 'cursor: pointer') and .//h4]"))
                )
                logger.info("Элемент хранилища найден.")
                return storage_element
            except TimeoutException:
                logger.error(
                    "Не удалось дождаться появления элемента хранилища в течение 3 минут.")
                return None

        except Exception as e:
            logger.error(
                f"Ошибка в процессе нажатия кнопок или ожидания хранилища: {e}")
            return None

    def process_claim_block(self):
        self.switch_to_iframe
        """
        Проверяет наличие блока с текстом '0.01' на странице,
        скроллит к нему и нажимает на него при обнаружении, затем выполняет последовательность действий.
        """
        try:
            # logger.info("Ищем блок с текстом 'Клейм 0.01 ()' на всей странице...")

            # Ожидаем появления блока
            claim_block = self.wait_for_element(
                By.XPATH, "//*[contains(text(), 'Клейм') or contains(text(), 'Claim')]")

            if claim_block:
                logger.info(
                    "Обнаружена незавершенная регистрация. Завершаем...")
                # Скроллим к найденному элементу
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", claim_block)

                # Делаем небольшой таймаут для завершения скроллинга
                time.sleep(1)

                # Нажимаем на элемент
                # logger.info("Нажимаем на блок с текстом 'Клейм 0.01 ()'...")
                claim_block.click()

                # logger.info("Нажимаем кнопку 'Продолжить', пока она доступна...")
                self.click_continue_button_until_unavailable()

                time.sleep(5)

                # logger.info("Нажимаем кнопки до тех пор, пока окно не исчезнет...")
                self.click_until_disappear()

                # logger.info("Обработка блока с текстом 'Клейм 0.01 ()' завершена.")
            else:
                pass
                # logger.warning("Блок с текстом 'Клейм 0.01 ()' не найден на странице.")
        except TimeoutException:
            logger.warning(
                "Не удалось найти блок с текстом 'Клейм 0.01 ()' в течение 2 минут.")
        except Exception as e:
            logger.error(
                f"Ошибка при обработке блока с текстом 'Клейм 0.01 ()': {e}")
