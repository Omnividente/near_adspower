import logging
import random
import time
import json
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException, ElementNotInteractableException
from browser_manager import BrowserManager
from selenium.webdriver.common.action_chains import ActionChains
from utils import update_balance_table
from colorama import Fore, Style
from termcolor import colored

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
            log_message = log_message.replace(record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}")
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)
            log_message = log_message.replace(record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")
            return log_message

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
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
    time.sleep(pause_duration)        
    
class TelegramBotAutomation:
    MAX_RETRIES = 3

    def __init__(self, serial_number, settings):
        self.serial_number = serial_number
        self.username = None
        self.balance = 0.0
        self.browser_manager = BrowserManager(serial_number)
        self.settings = settings
        logger.info(colored(f"Account {self.serial_number}: Initializing automation", "cyan"))
        
        if not self.browser_manager.wait_browser_close():
            logger.error("Account {serial_number}: Failed to close previous browser session.")
            return
        if not self.browser_manager.start_browser():
            logger.error(f"Account {serial_number}: Failed to start browser.")
            return
        self.driver = self.browser_manager.driver 

    def log_account_as_complete(self):
        try:
            with open("all_quest_complete.txt", "a", encoding="utf-8") as file:
                file.write(f"{self.serial_number}\n")
            logger.info(f"Account {self.serial_number}: Logged as complete in 'all_quest_complete.txt'")
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error writing to file 'all_quest_complete.txt'. Error: {e}")  
    
    
    def process_mission_quests(self):
        logger.info(f"Account {self.serial_number}: Starting mission quests.")
        
        try:
            # Переход в раздел "Missions"
            self.open_section(3, "Missions")

            # Запускаем выполнение основных квестов и проверяем их статус
            main_quests_performed = self.check_and_complete_main_quests()

            # Если основные квесты не завершены из-за ошибки, прерываем выполнение
            if not main_quests_performed:
                logger.warning(f"Account {self.serial_number}: Main quests not completed due to an error.")
                for attempt in range(5):  # Пытаемся не более 5 раз
                    if self.open_section(1, "Home"):
                        logger.info(f"Account {self.serial_number}: Returned to 'Home' section.")
                        break  # Успешный переход на главную страницу, выходим из цикла
                    else:
                        #logger.warning(f"Account {self.serial_number}: 'Home' section not available, attempting to go back (Attempt {attempt + 1}).")
                        self.go_back_to_previous_page()
                        time.sleep(2)  # Небольшая пауза перед следующей попыткой
                else:
                    logger.error(f"Account {self.serial_number}: Failed to return to 'Home' section after 5 attempts.")
                return  # Прерывание выполнения при ошибке в основных квестах

            # Запускаем выполнение дополнительных квестов и проверяем их статус
            additional_quests_completed = self.process_additional_quests_from_missions()

            # Если дополнительные квесты не завершены из-за ошибки, прерываем выполнение
            if not additional_quests_completed:
                logger.warning(f"Account {self.serial_number}: Additional quests not completed due to an error.")
                for attempt in range(5):  # Пытаемся не более 5 раз
                    if self.open_section(1, "Home"):
                        logger.info(f"Account {self.serial_number}: Returned to 'Home' section.")
                        break  # Успешный переход на главную страницу, выходим из цикла
                    else:
                        #logger.warning(f"Account {self.serial_number}: 'Home' section not available, attempting to go back (Attempt {attempt + 1}).")
                        self.go_back_to_previous_page()
                        time.sleep(2)  # Небольшая пауза перед следующей попыткой
                else:
                    logger.error(f"Account {self.serial_number}: Failed to return to 'Home' section after 5 attempts.")
                return  # Прерывание выполнения при ошибке в дополнительных квестах

            # Проверка, что все квесты завершены
            if main_quests_performed and additional_quests_completed:
                # Запись номера аккаунта в файл all_quest_complete.txt
                self.log_account_as_complete()

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in process_mission_quests - {e}")
            # Не прерываем выполнение здесь, так как блок перехода будет вне `try`

        # Переход на главную страницу после завершения или в случае ошибки
        for attempt in range(5):  # Пытаемся не более 5 раз
            if self.open_section(1, "Home"):
                logger.info(f"Account {self.serial_number}: Returned to 'Home' section.")
                break  # Успешный переход на главную страницу, выходим из цикла
            else:
                logger.warning(f"Account {self.serial_number}: 'Home' section not available, attempting to go back (Attempt {attempt + 1}).")
                self.go_back_to_previous_page()
                time.sleep(2)  # Небольшая пауза перед следующей попыткой
        else:
            logger.error(f"Account {self.serial_number}: Failed to return to 'Home' section after 5 attempts.")


    
    
    
    def check_and_complete_main_quests(self):
        logger.info(f"Account {self.serial_number}: Checking main quests.")

        try:
            # Проверка выполнения всего блока основных квестов
            if self.is_quest_completed():
                logger.info(f"Account {self.serial_number}: All main quests already completed.")
                return True  # Возвращаем True, если весь блок уже завершён

            # Переход к секции квестов
            quest_section = self.wait_for_element(By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")
            
            if quest_section:
                self.scroll_and_click(quest_section)
            else:
                logger.warning(f"Account {self.serial_number}: Quest section not found.")  
                return False  # Если секция не найдена, завершаем выполнение

            # Выполняем квесты
            quest_count = 16  # Количество квестов (или используем динамическое определение)
            for i in range(1, quest_count + 1):
                try:
                    # Ищем основной контейнер с квестами перед каждой итерацией
                    main_container = self.wait_for_element(
                        By.XPATH, 
                        "//h3[contains(text(), 'EARN') or contains(text(), 'Заработать')]/following-sibling::div"
                    )

                    if not main_container:
                        logger.warning(f"Account {self.serial_number}: Main quest container not found.")
                        return False

                    # Получаем актуальный список квестов
                    quests = main_container.find_elements(By.XPATH, "./div")

                    # Проверяем, что текущий квест существует и не завершен
                    if i <= len(quests):
                        quest = quests[i - 1]
                        if not self.is_quest_button_completed(quest):
                            quest.click()
                            logger.info(f"Account {self.serial_number}: Main quest button {i} clicked.")

                            # Добавляем небольшую паузу, чтобы элементы страницы обновились
                            time.sleep(2)

                            # Запускаем и завершаем квест
                            if not self.start_and_complete_quest(f"Quest {i}"):
                                logger.warning(f"Account {self.serial_number}: Quest {i} failed to complete.")
                                return False  # Прерываем выполнение и возвращаем False при ошибке
                           
                            time.sleep(1)
                    else:
                        logger.warning(f"Account {self.serial_number}: Quest {i} not found in the list.")
                        break  # Прекращаем цикл, если квестов меньше, чем ожидалось

                except Exception as e:
                    logger.warning(f"Account {self.serial_number}: Error processing quest {i} - {e}")
                    return False  # Прерываем выполнение и возвращаем False при любой ошибке

            return True  # Возвращаем True, если все квесты выполнены успешно

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in check_and_complete_main_quests - {e}")
            return False



        
    def check_and_complete_main_quests2(self):
        logger.info(f"Account {self.serial_number}: Checking main quests.")

        try:
            # Проверка выполнения всего блока основных квестов
            if self.is_quest_completed():
                logger.info(f"Account {self.serial_number}: All main quests already completed.")
                return True  # Возвращаем True, если весь блок уже завершён

            all_main_quests_completed = True

            # Переход к секции квестов
            quest_section = self.wait_for_element(By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")
            
            if quest_section:
                self.scroll_and_click(quest_section)
            else:
                logger.warning(f"Account {self.serial_number}: Quest section not found.")  
                return False  # Если секция не найдена, завершаем выполнение

            # Находим основной контейнер, содержащий квесты
            main_container = self.wait_for_element(By.XPATH, "//div[contains(@style, 'justify-content: space-around')]")
            
            # Проверяем, что контейнер найден
            if not main_container:
                logger.warning(f"Account {self.serial_number}: Main quest container not found.")
                return False

            # Получаем все дочерние элементы (квесты) в контейнере
            quests = main_container.find_elements(By.XPATH, "./div")

            # Проходим по каждому квесту
            for index, quest in enumerate(quests, start=1):
                try:
                    # Если кнопка квеста найдена и квест ещё не завершён, выполняем его
                    if quests and not self.is_quest_button_completed(quests):
                       quests.click()
                       logger.info(f"Account {self.serial_number}: Main quest button {i} clicked.")

                       # Запускаем и завершаем основной квест
                       if not self.start_and_complete_quest(f"Quest {i}"):
                           all_main_quests_completed = False
                           return False  # Прекращаем выполнение цикла, если возникла ошибка                        
                except Exception as e:
                    logger.warning(f"Account {self.serial_number}: Error processing quest {index} - {e}")
                    all_main_quests_completed = False
                    return False

            return all_main_quests_completed

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in check_and_complete_main_quests - {e}")
            return False
    

    def process_additional_quests_from_missions(self):
        logger.info(f"Account {self.serial_number}: Starting additional quests from 'Missions'.")

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
                    logger.warning(f"Account {self.serial_number}: Quest in '{section_name}' section not found or already completed.")
                    all_additional_quests_completed = False
                    break  # Прерываем выполнение цикла при первой ошибке

            return all_additional_quests_completed

        except Exception as e:
            # Логируем ошибку и завершаем выполнение дополнительных квестов
            logger.error(f"Account {self.serial_number}: Error in process_additional_quests_from_missions - {e}")
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
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", section)
                    time.sleep(1)  # Задержка для прогрузки контента

                    # Пробуем кликнуть по элементу с обработкой возможной блокировки
                    for _ in range(3):
                        try:
                            section.click()
                            logger.info(f"Account {self.serial_number}: Navigated to section '{section_name}'.")
                            return  # Успешно найден и кликнут нужный раздел
                        except Exception as click_error:
                            logger.warning(f"Account {self.serial_number}: Retrying click on section '{section_name}' due to interception.")
                            time.sleep(1)  # Задержка перед повторной попыткой

            logger.warning(f"Account {self.serial_number}: Section '{section_name}' not found.")
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error navigating to section '{section_name}'. Error: {e}")

    
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
            quest_element = self.wait_for_element(By.XPATH, xpath_expression, timeout=10)

            if quest_element:
                # Плавный скролл к элементу с динамической паузой
                self.driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", quest_element)
                time.sleep(random.uniform(1.5, 2.5))  # Динамическая пауза

                # Проверяем, завершен ли квест
                if self.is_quest_completed_for_additional(quest_element):
                    logger.info(f"Account {self.serial_number}: Quest '{quest_titles[0]}' in section '{section_name}' is already completed.")
                    self.go_back_to_previous_page()  # Переход назад, если квест уже завершен
                    return True  # Завершаем выполнение, если квест уже выполнен

                # Плавное движение мыши к элементу и клик
                actions = ActionChains(self.driver)
                actions.move_to_element(quest_element)
                dynamic_pause()
                quest_element.click()
                logger.info(f"Account {self.serial_number}: Quest '{quest_element.text}' found and clicked in section '{section_name}'.")
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
                    #logger.info(f"Account {self.serial_number}: Answered quest '{quest_element.text}' with '{answer}'.")
                    self.enter_answer(answer)
                    dynamic_pause()
                    self.confirm_answer_submission()                   
                    return True
                else:
                    logger.warning(f"Account {self.serial_number}: No answer found for question '{question_text}' in quest '{quest_element.text}'.")
                    return False

            else:
                logger.warning(f"Account {self.serial_number}: Quest '{quest_titles[0]}' or '{quest_titles[1]}' not found in section '{section_name}'.")
                return False

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in start_and_complete_additional_quest in section '{section_name}'. Error: {e}")
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
                    logger.info(f"Account {self.serial_number}: All quests completed.")
                    return True
                else:
                    # Если не все квесты завершены, переходим к разделу квестов
                    quest_section = self.wait_for_element(By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")
                    if quest_section:
                        self.driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", quest_section)
                        ActionChains(self.driver).move_to_element(quest_section).pause(random.uniform(0.5, 1.5)).click(quest_section).perform()
                        logger.info(f"Account {self.serial_number}: Navigated to quest section.")
                        return True
                    else:
                        logger.warning(f"Account {self.serial_number}: Quest section not found.")
                        return False                
            else:
                logger.warning(f"Account {self.serial_number}: No answer found for question '{question_text}' in quest.")
                return False

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in start_and_complete_quest in section '{section_name}'. Error: {e}")
            return False


    def go_back_to_previous_page(self):
        """
        Использует браузерную функцию "Назад", чтобы вернуться на предыдущую страницу.
        """
        try:
            # Используем команду браузера "Назад"
            self.driver.back()
            #logger.info(f"Account {self.serial_number}: Used browser's back function to return to the previous page.")
            time.sleep(2)  # Задержка для загрузки предыдущей страницы
            self.switch_to_iframe()
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error while using browser's back function. Error: {e}")

    def is_quest_completed_for_additional(self, quest_button):
        try:
            # Проверяем, что элемент для квеста существует
            if quest_button:
                # Пробуем найти родительский контейнер для квеста
                quest_container = quest_button.find_element(By.XPATH, "./ancestor::div[1]")
                completed_text_elements = quest_container.find_elements(By.XPATH, ".//*[contains(text(), 'Выполнено') or contains(text(), 'Completed')]")
                return bool(completed_text_elements)
            else:
                logger.warning(f"Account {self.serial_number}: Quest button not found or not accessible.")
                return False
        except NoSuchElementException:
            logger.warning(f"Account {self.serial_number}: Quest container for completion check not found.")
            return False
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Unexpected error during quest completion check. Error: {e}")
            return False

    def open_text_input_window(self):
        # Ищем кнопку, которая открывает окно ввода текста, по тексту "Submit password" или "Отправить фразу"
        text_input_button = self.wait_for_element(By.XPATH, "//button[contains(text(), 'Submit password') or contains(text(), 'Отправить фразу')]")
        
        # Проверяем, если кнопка найдена
        if text_input_button:
            text_input_button.click()
            logger.info(f"Account {self.serial_number}: 'Submit password' to open text input window.")
            time.sleep(2)  # Небольшая задержка для загрузки окна ввода
        else:
            logger.warning(f"Account {self.serial_number}: 'Submit password' or 'Отправить фразу' button not found.")
    
    def open_section(self, position, section_name):
        try:
            # Ищем элемент по позиции внутри контейнера #here-tabs
            section_button = self.wait_for_element(By.XPATH, f"//*[@id='here-tabs']/div[{position}]")
            
            if section_button:
                # Прокручиваем к элементу, чтобы он был в зоне видимости, и нажимаем на него
                self.driver.execute_script("arguments[0].scrollIntoView(true);", section_button)
                section_button.click()
                logger.info(f"Account {self.serial_number}: '{section_name}' section button clicked.")
                return True  # Успешный клик
            else:
                logger.warning(f"Account {self.serial_number}: '{section_name}' section button not found at position {position}.")
                return False  # Элемент не найден
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error while trying to open '{section_name}' section at position {position}. Error: {e}")
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
                logger.warning(f"Account {self.serial_number}: No buttons found on the page.")
                return

            logger.info(f"Account {self.serial_number}: Found {len(buttons)} buttons. Attempting to click each.")

            for index, button in enumerate(buttons, start=1):
                try:
                    # Проверяем текст кнопки (для логирования)
                    button_text = button.text.strip() if button.text else "No text"
                    logger.info(f"Account {self.serial_number}: Trying button {index}: '{button_text}'.")

                    # Прокручиваем к кнопке
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", button
                    )
                    time.sleep(1)

                    # Пытаемся кликнуть стандартным способом
                    try:
                        button.click()
                        logger.info(f"Account {self.serial_number}: Clicked button {index} using standard click.")
                    except Exception as click_error:
                        logger.warning(f"Account {self.serial_number}: Standard click failed for button {index}. Trying JavaScript click. Error: {click_error}")
                        # Резервный клик через JavaScript
                        self.driver.execute_script("arguments[0].click();", button)
                        logger.info(f"Account {self.serial_number}: Clicked button {index} using JavaScript click.")

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
                        logger.info(f"Account {self.serial_number}: Switched to new video window.")
                        time.sleep(5)  # Задержка для имитации просмотра видео

                        # Закрываем вкладку с видео
                        self.driver.close()
                        logger.info(f"Account {self.serial_number}: Video window closed.")

                        # Возвращаемся к исходной вкладке
                        self.driver.switch_to.window(original_window)
                        logger.info(f"Account {self.serial_number}: Switched back to original window.")
                        self.switch_to_iframe()
                        return  # Успешное завершение

                except Exception as button_error:
                    logger.warning(f"Account {self.serial_number}: Error clicking button {index}: {button_error}")

            logger.error(f"Account {self.serial_number}: No buttons opened a new video window.")
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in play_video: {e}")





     
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
                logger.info(f"Account {self.serial_number}: Switched to new video window.")
                time.sleep(5)  # Задержка для имитации просмотра видео

                # Закрываем вкладку с видео
                self.driver.close()
                logger.info(f"Account {self.serial_number}: Video window closed.")
                
                # Возвращаемся к исходной вкладке
                self.driver.switch_to.window(original_window)
                logger.info(f"Account {self.serial_number}: Switched back to original window.")
                self.switch_to_iframe()
            else:
                logger.warning(f"Account {self.serial_number}: New video window not detected.")
        else:
            logger.warning(f"Account {self.serial_number}: Video button not found.")

    def click_submit_password_button(self):
        # Находим кнопку по тексту "Submit password" или "Отправить фразу"
        submit_button = self.wait_for_element(By.XPATH, "//button[contains(text(), 'Submit password') or contains(text(), 'Отправить фразу')]")
        
        # Проверяем, если кнопка найдена
        if submit_button:
            submit_button.click()
            logger.info(f"Account {self.serial_number}: 'Submit password' or 'Отправить фразу' button clicked.")
        else:
            logger.warning(f"Account {self.serial_number}: 'Submit password' or 'Отправить фразу' button not found.")

    def scroll_and_click(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
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
                #logger.info(f"Attempt {attempt}/{max_attempts} to check if quest is completed.")
                
                # Находим секцию квеста по тексту
                quest_section = self.wait_for_element(By.XPATH, "//*[contains(text(), 'Explore crypto') or contains(text(), 'Исследуйте мир крипты')]")
                
                if quest_section:
                    # Прокручиваем к секции, чтобы она была видимой
                    self.driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", quest_section)
                    logger.info(f"Quest section found and navigated to on attempt {attempt}.")

                    # Поднимаемся к общему контейнеру
                    quest_container = quest_section.find_element(By.XPATH, "./ancestor::div[contains(@style, 'position: relative')]")
                    
                    # Проверяем наличие текста "Completed" или "Выполнено" в контейнере
                    completed_text_element = quest_container.find_elements(By.XPATH, ".//*[contains(text(), 'Completed') or contains(text(), 'Выполнено')]")
                    
                    if completed_text_element:
                        logger.info(f"Quest is marked as completed on attempt {attempt}.")
                        return True
                    elif attempt == max_attempts:
                        logger.info("Quest is not marked as completed after all attempts.")
                        return False
                elif attempt == max_attempts:
                    logger.warning("Quest section not found after all attempts.")
                    return False

            except Exception as e:
                logger.error(f"Error in attempt {attempt}/{max_attempts} of is_quest_completed: {e}")
            
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
        question_text_element = self.wait_for_element(By.XPATH, "//div[contains(@class, 'react-modal-sheet-content')]//h3")         
        return question_text_element.text.lower() if question_text_element else None

    def find_answer(self, question_text, questions_answers):
        # Приводим текст вопроса к нижнему регистру для единообразия
        question_text_lower = question_text.lower()

        # Сортируем ключи из JSON по длине в обратном порядке, чтобы более длинные вопросы проверялись первыми
        sorted_questions = sorted(questions_answers.keys(), key=len, reverse=True)

        # Ищем полное совпадение с более длинными вопросами
        for key in sorted_questions:
            if key.lower() in question_text_lower:
                return questions_answers[key]  # Возвращаем ответ при первом совпадении

        # Если ничего не найдено, возвращаем None
        return None

    def enter_answer(self, answer):
        # Ищем первое поле input в пределах окна ввода пароля, ориентируясь на структуру
        answer_input = self.wait_for_element(By.XPATH, "//div[@id='root']//input")
        
        # Проверяем, найдено ли поле ввода
        if answer_input:
            # Вводим ответ символ за символом с небольшой задержкой
            for char in answer:
                answer_input.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))  # Задержка для эмуляции ввода пользователем
            logger.info(f"Account {self.serial_number}: Answer '{answer}' entered.")
        else:
            logger.warning(f"Account {self.serial_number}: Answer input field not found.")

        # Ищем кнопку отправки в пределах окна, не завися от классов
        submit_button = self.wait_for_element(By.XPATH, "//div[@id='root']//button")
        
        # Ждем, пока кнопка станет активной, затем кликаем
        if submit_button:
            while not submit_button.is_enabled():
                time.sleep(0.5)  # Проверяем каждые 0.5 секунды, активна ли кнопка
            submit_button.click()
            logger.info(f"Account {self.serial_number}: Submit button clicked.")
        else:
            logger.warning(f"Account {self.serial_number}: Submit button not found.")

    def confirm_answer_submission(self):
        try:
            # Находим контейнер, который содержит кнопку
            confirmation_container = self.wait_for_element(By.CSS_SELECTOR, "div.react-modal-sheet-scroller", timeout=120)
            
            # Ищем первую кнопку внутри контейнера
            confirm_button = confirmation_container.find_element(By.TAG_NAME, "button")
            
            # Прокручиваем к кнопке, чтобы она была видимой
            self.driver.execute_script("arguments[0].scrollIntoView(true);", confirm_button)
            time.sleep(1)  # Небольшая задержка после прокрутки
            
            # Пытаемся выполнить стандартный клик по кнопке
            confirm_button.click()
            logger.info(f"Account {self.serial_number}: Confirmation button clicked.")
            
        except Exception as e:
            logger.warning(f"Account {self.serial_number}: Could not click confirmation button. Error: {e}")
   
 
    def wait_for_element(self, by, value, parent=None, timeout=10):
        """
        Ожидает появления элемента на странице и возвращает его.
        Если указан parent, поиск будет в пределах указанного родителя.
        """
        try:
            if parent:
                WebDriverWait(parent, timeout).until(lambda _: parent.find_element(by, value))
                return parent.find_element(by, value)
            else:
                WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, value)))
                return self.driver.find_element(by, value)
        except TimeoutException:
            #logger.warning(f"Could not find element by {by} with value {value} in {timeout} seconds.")
            return None

    def navigate_to_bot(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                self.driver.get('https://web.telegram.org/k/')
                logger.info(f"Account {self.serial_number}: Navigated to Telegram web.")
                self.close_extra_windows()
                time.sleep(random.randint(5, 7))
                return True
            except (WebDriverException, TimeoutException) as e:
                logger.warning(f"Account {self.serial_number}: Error navigating to Telegram (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
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
                #logger.info(f"Account {self.serial_number}: Switched to iframe.")
                return True
            else:
                logger.warning(f"Account {self.serial_number}: No iframe found to switch.")
                return False
        except NoSuchElementException:
            logger.warning(f"Account {self.serial_number}: No iframe found.")
            return False
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Unexpected error while switching to iframe: {str(e)}")
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
            logger.warning(f"Account {self.serial_number}: Error closing extra windows: {str(e)}")

    def send_message(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                chat_input_area = self.wait_for_element(By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/input[1]')
                if chat_input_area:
                    chat_input_area.click()
                    
                    group_url = self.settings.get('TELEGRAM_GROUP_URL', 'https://t.me/CryptoProjects_sbt')
                    chat_input_area.send_keys(group_url)
                    search_area = self.wait_for_element(By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/ul[1]/a[1]/div[1]')
                    if search_area:
                        search_area.click()
                        logger.info(f"Account {self.serial_number}: Message sent to group.")
                time.sleep(random.randint(5, 7))
                return True
            except (NoSuchElementException, WebDriverException) as e:
                logger.warning(f"Account {self.serial_number}: Error in send_message (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
        return False

    def click_link(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                # Получаем ссылку из настроек
                bot_link = self.settings.get('BOT_LINK', 'https://t.me/herewalletbot/app?startapp=286283')
                # Поиск элемента ссылки
                
                link = self.wait_for_element(By.CSS_SELECTOR, f"a[href*='{bot_link}']")

                if link:
                    link.click()
                    time.sleep(2)                    
                logger.info(f"Account {self.serial_number}: Link clicked and process initiated.")
                time.sleep(3)
                
                launch_button = self.driver.find_elements(By.CSS_SELECTOR, "button.popup-button.btn.primary.rp")

                if not launch_button:
                    # Попытка найти кнопку по дополнительному XPATH, используя содержимое <span>
                    launch_button = self.driver.find_elements(By.XPATH, "//button[contains(@class, 'popup-button') and contains(@class, 'primary') and span[text()='Launch']]")

                if launch_button:
                    # Прокручиваем к элементу, чтобы он был видимым, и выполняем клик
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", launch_button[0])
                    launch_button[0].click()
                    logger.info(f"Account {self.serial_number}: Launch button clicked.")
                
                time.sleep(random.randint(15, 20))
                self.switch_to_iframe()
                return True
            except WebDriverException as e:
                logger.warning(f"Account {self.serial_number}: Error clicking link (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
        return False

    def find_timer_element(self):
        try:
            # Находим контейнер прогресса по уникальным признакам
            progress_container = self.wait_for_element(By.XPATH, "//div[contains(@style, 'display: flex;') and contains(@style, 'height: 8px;')]")
            
            if progress_container:
                # Находим вложенный элемент с процентом ширины (заполненности)
                progress_element = progress_container.find_element(By.XPATH, "./div[2]")
                style = progress_element.get_attribute("style")

                # Извлекаем значение процента заполнения из стиля
                width_value = None
                if "width" in style:
                    try:
                        width_str = style.split("width:")[1].split("%")[0].strip()
                        width_value = float(width_str)
                        #logger.info(f"Account {self.serial_number}: Progress percentage found - {width_value}%")
                    except ValueError:
                        logger.warning(f"Account {self.serial_number}: Unable to parse width value from style: {style}")
                else:
                    logger.warning(f"Account {self.serial_number}: Width attribute not found in style: {style}")

                return width_value

            else:
                logger.warning(f"Account {self.serial_number}: Progress container not found.")
                return None

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error retrieving progress percentage. Error: {e}")
            return None    

    def farming(self):
        self.open_storage_section()
        try:
            # Ищем элемент таймера с помощью find_timer_element, который возвращает процент заполнения
         
            percent = self.find_timer_element()  # Теперь percent сразу становится числовым значением
            if percent is not None:
                if percent == 100.0:
                    logger.info(f"Account {self.serial_number}: Timer is at 100%. Attempting to claim.")
                    time.sleep(5)
                    self.claim_hot()
                else:
                    logger.info(f"Account {self.serial_number}: Timer percentage is not 100% (current: {percent}%).")
            else:
                logger.warning(f"Account {self.serial_number}: Timer element not found.")
        except Exception as e:
            logger.error(f"Account {self.serial_number}: An error occurred while processing the timer: {e}")
   
    def claim_hot(self):
        try:
            # Находим кнопку "News" с уникальным признаком '--Pink-Primary' в её стиле
            news_button = next((btn for btn in self.driver.find_elements(By.TAG_NAME, "button") 
                                if "--Pink-Primary" in btn.get_attribute("style") and btn.is_displayed()), None)

            # Если нашли кнопку "News", нажимаем её
            if news_button:
                news_button.click()
                logger.info(f"Account {self.serial_number}: 'News' button clicked. Waiting for 'Claim HOT' button to appear.")
                time.sleep(2)  # Небольшая задержка для обновления интерфейса

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
                logger.info(f"Account {self.serial_number}: 'Claim HOT' button clicked.")

                # Ожидаем обновления баланса, проверяя каждые 5 секунд, пока не истекут 3 минуты (180 секунд)
                initial_balance = self.get_update_balance()
                start_time = time.time()

                while time.time() - start_time < 180:  # 3 минуты в секундах
                    current_balance = self.get_update_balance()
                    if current_balance != initial_balance:
                        logger.info(f"Account {self.serial_number}: Balance updated successfully to {current_balance}")
                        break
                    time.sleep(5)  # Проверяем баланс каждые 5 секунд
                else:
                    logger.warning(f"Account {self.serial_number}: Balance update not detected within 3 minutes.")
            else:
                logger.warning(f"Account {self.serial_number}: 'Claim HOT' button not found.")

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error in claim_hot function. Error: {e}")
    
    def get_balance(self):
        try:
            # Поиск имени пользователя
            user_button = self.wait_for_element(By.XPATH, "//div[@style='position: relative; margin-top: 4px;']//button")
            if user_button:
                username = user_button.find_element(By.TAG_NAME, "p").text
                logger.info(f"Account {self.serial_number}: Username found - {username}")
            else:
                username = None
                logger.warning(f"Account {self.serial_number}: Username not found.")
            
            # Поиск баланса
            balance_element = self.wait_for_element(By.XPATH, "//p[contains(@style, 'display: inline-block; font-size: 18px;')]")
            if balance_element:
                balance_text = balance_element.text
                try:
                    # Преобразуем баланс в число с плавающей точкой
                    balance = float(balance_text.replace(",", "").strip())
                    logger.info(f"Account {self.serial_number}: Balance found - {balance}")
                except ValueError:
                    balance = None
                    logger.warning(f"Account {self.serial_number}: Failed to convert balance text '{balance_text}' to a float.")
            else:
                balance = None
                logger.warning(f"Account {self.serial_number}: Balance not found.")
            update_balance_table(self.serial_number, username, balance)
            return balance, username

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error retrieving username and balance. Error: {e}")
            return None, None

    def open_storage_section(self):
        try:
            # Используем XPath для поиска контейнера с курсором pointer, содержащего тег h4
            storage_button = self.wait_for_element(By.XPATH, "//div[contains(@style, 'cursor: pointer') and .//h4]")

            if storage_button:
                # Прокручиваем к элементу с плавной анимацией
                self.driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", storage_button)
                dynamic_pause()  # Динамическая пауза перед кликом

                # Эмулируем плавное наведение и клик для более естественного поведения
                actions = ActionChains(self.driver)
                actions.move_to_element(storage_button).pause(0.5).click(storage_button).perform()
                logger.info(f"Account {self.serial_number}: 'Storage' button clicked.")
            else:
                logger.warning(f"Account {self.serial_number}: 'Storage' button not found.")
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error while trying to click 'Storage' button. Error: {e}")
  
    def get_update_balance(self):
        try:
            # Ищем все элементы <p> на странице
            elements = self.driver.find_elements(By.TAG_NAME, "p")
            
            for element in elements:
                # Проверяем текст элемента
                if "HOT Баланс" in element.text or "HOT Balance" in element.text:
                    # Если текст найден, переходим к родительскому контейнеру
                    parent_container = element.find_element(By.XPATH, "./parent::div")
                    
                    # Находим второй <p>, содержащий баланс
                    balance_value_element = parent_container.find_element(By.XPATH, ".//p[2]")
                    
                    # Извлекаем текст и преобразуем его в число
                    balance_text = balance_value_element.text.strip()
                    try:
                        balance = float(balance_text.replace(",", ""))
                        logger.info(f"Account {self.serial_number}: HOT Balance found: {balance}")
                        return balance
                    except ValueError:
                        logger.warning(f"Account {self.serial_number}: Could not convert balance text to number: {balance_text}")
                        return 0.0
            
            # Если ни один из элементов не содержит нужного текста
            logger.warning(f"Account {self.serial_number}: HOT Balance text not found.")
            return 0.0

        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error retrieving HOT balance. Error: {e}")
            return 0.0
  
    def get_remaining_time(self):
            try:
                # Ищем все элементы <p> и проверяем, если они вообще найдены
                time_elements = self.driver.find_elements(By.TAG_NAME, "p")
                if not time_elements:
                    logger.warning(f"Account {self.serial_number}: No <p> elements found on the page.")
                    return None

                for element in time_elements:
                    time_text = element.text.strip()
                    logger.debug(f"Account {self.serial_number}: Found time text - '{time_text}'")

                    # Проверка формата "Xh Ym" или "Xч Ym" (часы и минуты)
                    match_hours_minutes = re.search(r"(\d+)\s*[hч]\s*(\d+)\s*[mм]", time_text, re.IGNORECASE)
                    if match_hours_minutes:
                        hours = int(match_hours_minutes.group(1))
                        minutes = int(match_hours_minutes.group(2))
                        remaining_time = hours * 3600 + minutes * 60
                        break
                    
                    # Проверка формата "Xh" или "Xч" (только часы)
                    match_hours_only = re.search(r"(\d+)\s*[hч]", time_text, re.IGNORECASE)
                    if match_hours_only:
                        hours = int(match_hours_only.group(1))
                        remaining_time = hours * 3600
                        break
                    
                    # Проверка формата "Ym" или "Yм" (только минуты)
                    match_minutes_only = re.search(r"(\d+)\s*[mм]", time_text, re.IGNORECASE)
                    if match_minutes_only:
                        minutes = int(match_minutes_only.group(1))
                        remaining_time = minutes * 60

                        # Если минутное значение равно 0, устанавливаем оставшееся время на 5 минут
                        if minutes == 0:
                            remaining_time = 5 * 60
                        break
                else:
                    logger.warning(f"Account {self.serial_number}: No valid time format found in <p> elements.")
                    return None

                # Добавляем случайное время от 5 до 10 минут
                additional_seconds = random.randint(5, 10) * 60
                remaining_time += additional_seconds
                logger.info(f"Account {self.serial_number}: Total remaining time with random addition - {remaining_time} seconds")
                return remaining_time

            except Exception as e:
                logger.error(f"Account {self.serial_number}: Error retrieving remaining time. Error: {e}")
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
                    logger.warning("Кнопка 'Создать новый аккаунт' не найдена.")
                    return False

                # Проверяем наличие заголовка страницы "Создать аккаунт"
                header_element = self.wait_for_element(
                    By.XPATH,
                    "//h1[contains(text(), 'Создать аккаунт') or contains(text(), 'Create Account')]",
                    timeout=10
                )
                if not header_element:
                    logger.warning("Заголовок страницы 'Создать аккаунт' не найден.")
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
                    logger.info("Нажата кнопка 'Создать' для завершения создания аккаунта.")
                else:
                    logger.warning("Кнопка подтверждения создания аккаунта не найдена.")
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
            logger.info("Процесс регистрации нового аккаунта завершен успешно.")
            return True

        except Exception as e:
            logger.error(f"Ошибка в процессе регистрации нового аккаунта: {e}")
            return False

    def is_new_account_page(self):
        try:
            # Проверка заголовка страницы
            header = self.wait_for_element(By.XPATH, "//h1[contains(text(), 'HOT Wallet')]", timeout=5)
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
        logger.info(f"Account information for {nickname} appended to {filename}")
    
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
            target_button = WebDriverWait(self.driver, 120).until(tutorial_popup_condition)
            
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
            logger.error(f"Неожиданная ошибка при закрытии обучающего попапа: {e}")

    def click_continue_button_until_unavailable(self, max_attempts=20):
        attempts = 0
        while attempts < max_attempts:
            try:
                # Находим контейнер с кнопкой "Продолжить"
                container = self.driver.find_element(By.XPATH, "//div[contains(@style, 'display: flex') and contains(@style, 'justify-content: space-between')]")

                # Находим все кнопки внутри контейнера
                buttons = container.find_elements(By.TAG_NAME, "button")

                # Если кнопки найдены, кликаем по первой доступной
                if buttons:
                    for button in buttons:
                        try:
                            button.click()
                            logger.info(f"Clicked 'Continue' button. Attempt {attempts + 1}.")
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
            logger.warning("Достигнуто максимальное количество попыток нажатия кнопки 'Продолжить'.")
        time.sleep(3)

    def subscribe_to_telegram_channel(self):
        try:
            # Сохраняем текущую вкладку
            original_window = self.driver.current_window_handle

            # URL канала
            channel_url = "https://web.telegram.org/k/#@hotonnear"

            # Открываем новую вкладку
            self.driver.execute_script(f"window.open('{channel_url}', '_blank');")
            logger.info("Открыли новую вкладку для подписки на Telegram-канал.")

            # Переходим в новую вкладку
            self.driver.switch_to.window(self.driver.window_handles[-1])
            logger.info("Переключились на вкладку с Telegram-каналом.")

            # Ждём загрузки страницы
            self.wait_for_element(By.CSS_SELECTOR, ".btn-primary.btn-color-primary.chat-join.rp", timeout=10)

            # Находим и нажимаем кнопку "Подписаться"
            join_button = self.driver.find_element(By.CSS_SELECTOR, ".btn-primary.btn-color-primary.chat-join.rp")
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", join_button)
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
                    popup = self.driver.find_element(By.XPATH, "//div[contains(@class, 'popup') or contains(@class, 'modal')]")

                    # Находим все кнопки внутри окна
                    buttons = popup.find_elements(By.TAG_NAME, "button")
                    
                    if buttons:
                        for button in buttons:
                            try:
                                # Скроллим к кнопке и нажимаем
                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                                button.click()
                                logger.info("Кнопка найдена и нажата.")
                                time.sleep(2)  # Ждём обновления после нажатия
                                break  # Переходим к следующей итерации
                            except Exception as e:
                                logger.warning(f"Ошибка при нажатии кнопки: {e}")
                                continue
                    else:
                        logger.info("Кнопки в окне не найдены. Проверяем окно снова.")

                except NoSuchElementException:
                    # Если окно исчезло, выходим из цикла
                    logger.info("Окно исчезло. Переходим к ожиданию хранилища.")
                    break

            # Переходим назад на предыдущую страницу
            time.sleep(5)
            self.go_back_to_previous_page()

            # Ожидание появления хранилища (до 3 минут)
            try:
                logger.info("Ожидаем появления элемента хранилища до 3 минут...")
                storage_element = WebDriverWait(self.driver, 180).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@style, 'cursor: pointer') and .//h4]"))
                )
                logger.info("Элемент хранилища найден.")
                return storage_element
            except TimeoutException:
                logger.error("Не удалось дождаться появления элемента хранилища в течение 3 минут.")
                return None

        except Exception as e:
            logger.error(f"Ошибка в процессе нажатия кнопок или ожидания хранилища: {e}")
            return None
    
    def process_claim_block(self):
        self.switch_to_iframe
        """
        Проверяет наличие блока с текстом '0.01' на странице,
        скроллит к нему и нажимает на него при обнаружении, затем выполняет последовательность действий.
        """
        try:
            #logger.info("Ищем блок с текстом 'Клейм 0.01 ()' на всей странице...")

            # Ожидаем появления блока 
            claim_block = self.wait_for_element(By.XPATH, "//*[contains(text(), 'Клейм') or contains(text(), 'Claim')]")
            

            if claim_block:
                logger.info("Обнаружена незавершенная регистрация. Завершаем...")
                # Скроллим к найденному элементу
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", claim_block)

                # Делаем небольшой таймаут для завершения скроллинга
                time.sleep(1)

                # Нажимаем на элемент
                #logger.info("Нажимаем на блок с текстом 'Клейм 0.01 ()'...")
                claim_block.click()

                #logger.info("Нажимаем кнопку 'Продолжить', пока она доступна...")
                self.click_continue_button_until_unavailable()

                time.sleep(5)

                #logger.info("Нажимаем кнопки до тех пор, пока окно не исчезнет...")
                self.click_until_disappear()

                #logger.info("Обработка блока с текстом 'Клейм 0.01 ()' завершена.")
            else:
                pass
                #logger.warning("Блок с текстом 'Клейм 0.01 ()' не найден на странице.")
        except TimeoutException:
            logger.warning("Не удалось найти блок с текстом 'Клейм 0.01 ()' в течение 2 минут.")
        except Exception as e:
            logger.error(f"Ошибка при обработке блока с текстом 'Клейм 0.01 ()': {e}")






