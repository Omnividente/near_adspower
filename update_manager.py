import os
import subprocess
import requests
import sys
import time
from threading import Lock
from utils import load_settings, GlobalFlags, stop_event
from colorama import Fore, Style
import logging
import hashlib


logger = logging.getLogger("application_logger")
update_lock = Lock()

# ========================= Классы ==========================


class GitUpdater:
    """
    Класс для обновления через Git.
    """
    @staticmethod
    def is_git_installed():
        try:
            subprocess.run(["git", "--version"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
            logger.debug("Git is installed on the system.")
            return True
        except FileNotFoundError:
            logger.debug("Git is not installed on this system.")
            return False
        except Exception as e:
            logger.error(f"Error while checking for Git installation: {e}")
            return False

    @staticmethod
    def check_updates():
        try:
            logger.debug("Checking for updates via Git...")
            subprocess.run(["git", "fetch"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
            result = subprocess.run(
                ["git", "status", "-uno"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            output = result.stdout.decode("utf-8")
            logger.debug(f"Git status output: {output}")
            return "Your branch is behind" in output
        except Exception as e:
            logger.debug(f"Git update check failed: {e}")
            return False

    @staticmethod
    def perform_update():
        try:
            logger.info("Updating via Git...")
            subprocess.run(["git", "pull"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
            logger.info("Update completed successfully via Git.",
                        extra={'color': Fore.CYAN})
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git pull failed due to local changes: {e}")
            try:
                logger.info("Resetting local changes...",
                            extra={'color': Fore.CYAN})
                subprocess.run(["git", "reset", "--hard"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                logger.info("Retrying git pull after resetting changes...", extra={
                            'color': Fore.CYAN})
                subprocess.run(["git", "pull"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=True)
                logger.info(
                    "Update completed successfully after resetting local changes.", extra={'color': Fore.CYAN})
                return True
            except subprocess.CalledProcessError as reset_error:
                logger.error(
                    f"Update failed even after resetting changes: {reset_error}")
                return False


class FileUpdater:
    """
    Класс для обновления файлов напрямую через raw URL.
    """ 

    @staticmethod
    def check_updates():
        """
        Проверяет обновления для локальных файлов на основе удалённого репозитория.
        Если указан файл remote_files_for_update, загружает список файлов из него.
        """
        settings = load_settings()
        repo_url = settings.get("REPOSITORY_URL")
        files_to_update = [file.strip() for file in settings.get(
            "FILES_TO_UPDATE", "").split(",") if file.strip()]
        branch = "main"  # Укажите ветку

        if not repo_url:
            logger.error("Repository URL is not specified in settings.")
            return False, []

        # Проверяем наличие специального файла remote_files_for_update
        if "remote_files_for_update" in files_to_update:
            logger.debug("Fetching file list from remote_files_for_update...")
            try:
                # Формируем URL для получения файла remote_files_for_update
                timestamp = int(time.time())
                raw_url = f"https://raw.githubusercontent.com/{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/{branch}/remote_files_for_update?nocache={timestamp}"
                headers = {"Cache-Control": "no-cache"}
                response = requests.get(raw_url, headers=headers, timeout=10)
                response.raise_for_status()

                # Загрузка и парсинг файла
                remote_files_content = response.text.strip()
                files_to_update = [
                    file.strip() for file in remote_files_content.splitlines() if file.strip()]
                logger.debug(
                    f"Fetched files from remote_files_for_update: {files_to_update}")
            except Exception as e:
                logger.debug(f"Failed to fetch remote_files_for_update: {e}")
                return False, []

        if not files_to_update:
            logger.error(
                "No files specified in FILES_TO_UPDATE or remote_files_for_update.")
            return False, []

        updates = []
        headers = {
            "Cache-Control": "no-cache"  # Принудительное обновление без кэширования
        }

        for file_path in files_to_update:
            try:
                # Формируем URL для получения файла через raw.githubusercontent.com с параметром для обхода кэша
                timestamp = int(time.time())
                raw_url = f"https://raw.githubusercontent.com/{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/{branch}/{file_path}?nocache={timestamp}"

                # Отправляем запрос
                response = requests.get(raw_url, headers=headers, timeout=10)
                response.raise_for_status()

                # Получаем удалённое содержимое файла
                remote_content = response.content
                remote_hash = calculate_hash(remote_content)
                logger.debug(f"remote_hash for {file_path}: {remote_hash}")
                # Проверяем локальный файл
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        local_content = f.read()
                    local_hash = calculate_hash(local_content)
                    logger.debug(f"local_hash for {file_path}: {local_hash}")
                    # Сравниваем хэши локального и удалённого содержимого
                    if local_hash != remote_hash:
                        updates.append(file_path)
                else:
                    updates.append(file_path)

            except Exception as e:
                logger.error(f"Error checking file {file_path}: {e}")

        # Логируем список обновлений в конце
        if updates:
            logger.debug(f"Updates found for the following files: {updates}")
        else:
            logger.debug("No updates found.")

        return bool(updates), updates

    @staticmethod
    def perform_update(update_files, repo_url, stop_on_failure=True):
        """
        Updates files via URL and creates backups in the temp folder.
        Returns True if all files were successfully updated, otherwise False.
        """       
        logger.info("Updating files directly via raw URLs...", extra={
            'color': Fore.CYAN})

        # Удаляем расширение .git из URL, если оно присутствует
        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]

        branch = "main"  # Укажите ветку
        success = True   # Флаг успешности обновления
        temp_dir = "temp"  # Директория для временных файлов

        # Создаём папку temp, если она не существует
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            logger.debug(f"Temporary folder created: {temp_dir}")

        # Обновляем каждый файл из списка
        for file_path in update_files:
            try:
                logger.info(f"Updating file: {file_path}", extra={
                            'color': Fore.CYAN})

                # Добавляем уникальный параметр для обхода кэша
                timestamp = int(time.time())
                raw_url = (
                    f"https://raw.githubusercontent.com/"
                    f"{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/{branch}/{file_path}?nocache={timestamp}"
                )

                # Настраиваем заголовки Cache-Control для запроса
                headers = {"Cache-Control": "no-cache"}
                response = requests.get(raw_url, headers=headers, timeout=10)
                response.raise_for_status()  # Проверяем, что запрос прошёл успешно

                content = response.content  # Получаем содержимое файла

                # Путь для резервной копии
                file_name = os.path.basename(file_path)  # Извлекаем имя файла
                backup_path = os.path.join(temp_dir, f"{file_name}.backup")

                # Удаляем старую резервную копию, если она существует
                if os.path.exists(backup_path):
                    os.remove(backup_path)

                # Создаём резервную копию текущего файла
                if os.path.exists(file_path):
                    os.rename(file_path, backup_path)
                    logger.info(f"Backup created: {backup_path}", extra={
                        'color': Fore.CYAN})

                # Сохраняем обновленный файл обратно в его изначальный путь
                with open(file_path, "wb") as f:
                    f.write(content)

                logger.info(f"File {file_name} successfully updated at {file_path}.", extra={
                            'color': Fore.CYAN})

            except Exception as e:
                logger.error(f"Error updating file {file_path}: {e}")
                success = False
                if stop_on_failure:
                    raise  # Немедленное прерывание, если флаг установлен

        return success


# ========================= Основная логика ==========================

def calculate_hash(content):
        """
        Вычисляет SHA256 хэш содержимого.
        """
        sha256 = hashlib.sha256()
        sha256.update(content)
        return sha256.hexdigest()

def restart_script():
    # signal.signal(signal.SIGINT, signal.default_int_handler)
    """Перезапускает текущий скрипт."""
    python = sys.executable  # Путь к Python
    args = [python] + sys.argv  # Все аргументы командной строки
    try:
        # Создаём новый процесс
        GlobalFlags.interrupted = True
        logger.info("Restarting script...",
                    extra={'color': Fore.YELLOW})
        os.spawnv(os.P_WAIT, python, args)

    except KeyboardInterrupt:
        if not GlobalFlags.interrupted:  # Обрабатываем только один раз
            logger.warning("Restart interrupted by KeyboardInterrupt.")
            GlobalFlags.interrupted = True
        sys.exit(1)  # Завершаем текущий процесс с кодом ошибки
    except Exception as e:
        logger.error(f"Error during script restart: {e}")
        sys.exit(1)  # Завершаем текущий процесс с кодом ошибки
    finally:
        if not GlobalFlags.interrupted:
            logger.info("Exiting current process.")
        sys.exit(0)

def ignore_files_in_git(file_paths):
    """
    Отключает отслеживание изменений для нескольких файлов в Git (локально).
    :param file_paths: Список путей к файлам, которые нужно игнорировать.
    """
    for file_path in file_paths:
        try:
            subprocess.run(
                ["git", "update-index", "--assume-unchanged", file_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

def check_and_update(priority_task_queue, is_task_active):
    """
    Проверяет обновления и выполняет необходимые действия.
    """
    settings = load_settings()
    auto_update_enabled = settings.get("AUTO_UPDATE", "true").lower() == "true"

    try:
        if GitUpdater.is_git_installed() and GitUpdater.check_updates() and auto_update_enabled:
            logger.info("Git updates found. Performing update...",
                        extra={'color': Fore.CYAN})
            if GitUpdater.perform_update():
                logger.debug(
                    "Update successful. Stopping processes for restart...")
                stop_event.set()  # Останавливаем потоки
                stop_event.restart_mode = True
        else:
            updates_available, update_files = FileUpdater.check_updates()
            if updates_available:
                if auto_update_enabled:
                    logger.info("File updates found. Performing update...", extra={
                                'color': Fore.CYAN})
                    if FileUpdater.perform_update(
                        update_files, settings.get("REPOSITORY_URL")
                    ):
                        stop_event.set()  # Останавливаем потоки
                        stop_event.restart_mode = True
                else:
                    logger.info(
                        "Automatic updates are disabled. Updates available:", extra={'color': Fore.CYAN})
                    for file in update_files:
                        logger.info(f"   {file}", extra={'color': Fore.CYAN})
            else:
                logger.debug("No updates found.")

    except Exception as e:
        logger.error(f"Error during check_and_update: {e}")
