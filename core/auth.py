#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль аутентификации и управления пользователями для WDM_V12.
Отвечает за управление пользователями, ролями и разрешениями.
"""

import os
import threading
import hashlib
import datetime
import time
import secrets
from typing import Dict, List, Any, Optional, Union, Tuple

from utils.logger import get_module_logger, log_exception


class Hasher:
    """Класс для хеширования и проверки паролей"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Хеширование пароля с использованием PBKDF2 и SHA-256
        
        Args:
            password: Пароль для хеширования
            
        Returns:
            str: Хеш пароля в формате pbkdf2:sha256:iterations:salt:hash
        """
        salt = secrets.token_hex(8)
        iterations = 150000
        
        # Хеширование пароля
        key = hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            salt.encode('utf-8'), 
            iterations,
            dklen=32
        )
        
        # Формирование результата
        hash_str = key.hex()
        result = f"pbkdf2:sha256:{iterations}${salt}${hash_str}"
        
        return result
    
    @staticmethod
    def verify_password(stored_password: str, provided_password: str) -> bool:
        """
        Проверка соответствия пароля хешу
        
        Args:
            stored_password: Сохраненный хеш пароля
            provided_password: Предоставленный пароль для проверки
            
        Returns:
            bool: True, если пароль соответствует хешу, иначе False
        """
        try:
            # Разбираем сохраненный хеш
            algorithm, iterations, salt, hash_str = stored_password.split('$')
            iterations = int(iterations.split(':')[-1])
            
            # Вычисляем хеш для предоставленного пароля
            key = hashlib.pbkdf2_hmac(
                'sha256',
                provided_password.encode('utf-8'),
                salt.encode('utf-8'),
                iterations,
                dklen=32
            )
            
            # Сравниваем хеши
            return secrets.compare_digest(key.hex(), hash_str)
        
        except Exception:
            return False


class AuthManager:
    """
    Класс для управления аутентификацией, пользователями, ролями и разрешениями.
    Реализует шаблон Singleton для обеспечения единой точки доступа.
    """
    
    # Единственный экземпляр класса (шаблон Singleton)
    _instance = None
    
    # Блокировка для обеспечения потокобезопасности
    _lock = threading.RLock()
    
    def __new__(cls):
        """Реализация шаблона Singleton"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AuthManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Инициализация менеджера аутентификации"""
        with self._lock:
            if self._initialized:
                return
            
            self.logger = get_module_logger('core.auth')
            self.logger.debug("Инициализация менеджера аутентификации")
            
            # Текущий пользователь
            self.current_user = None
            
            # Кэш разрешений пользователей
            self._user_permissions_cache = {}
            
            # Флаг инициализации
            self._initialized = True
            
            self.logger.debug("Менеджер аутентификации инициализирован")
    
    def login(self, app_context, username: str, password: str) -> Tuple[bool, str]:
        """
        Аутентификация пользователя
        
        Args:
            app_context: Контекст приложения
            username: Имя пользователя
            password: Пароль
            
        Returns:
            Tuple[bool, str]: (Успех операции, Сообщение об ошибке)
        """
        try:
            self.logger.debug(f"Попытка входа для пользователя: {username}")
            
            # Получаем пользователя из базы данных
            query = "SELECT * FROM users WHERE username = ? AND is_active = 1"
            user_data = app_context.db_manager.execute_query(query, (username,))
            
            if not user_data:
                self.logger.warning(f"Пользователь не найден или неактивен: {username}")
                return False, "Неверное имя пользователя или пароль"
            
            user = user_data[0]
            
            # Проверяем пароль
            if not Hasher.verify_password(user['password_hash'], password):
                self.logger.warning(f"Неверный пароль для пользователя: {username}")
                return False, "Неверное имя пользователя или пароль"
            
            # Обновляем время последнего входа
            update_query = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?"
            app_context.db_manager.execute_query(update_query, (user['id'],))
            
            # Устанавливаем текущего пользователя
            self.current_user = user
            
            # Очищаем кэш разрешений для текущего пользователя
            if user['id'] in self._user_permissions_cache:
                del self._user_permissions_cache[user['id']]
            
            self.logger.info(f"Успешный вход пользователя: {username}")
            return True, "Вход выполнен успешно"
        
        except Exception as e:
            self.logger.error(f"Ошибка при аутентификации пользователя {username}: {e}")
            log_exception(self.logger, f"Ошибка аутентификации {username}")
            return False, f"Ошибка при аутентификации: {e}"
    
    def logout(self) -> None:
        """Выход пользователя из системы"""
        if self.current_user:
            self.logger.info(f"Выход пользователя: {self.current_user['username']}")
            self.current_user = None
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """
        Получение информации о текущем пользователе
        
        Returns:
            Optional[Dict[str, Any]]: Информация о текущем пользователе или None
        """
        return self.current_user
    
    def is_authenticated(self) -> bool:
        """
        Проверка, аутентифицирован ли пользователь
        
        Returns:
            bool: True, если пользователь аутентифицирован, иначе False
        """
        return self.current_user is not None
    
    def get_user_role(self, app_context, user_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Получение роли пользователя
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя (если None, используется текущий пользователь)
            
        Returns:
            Optional[Dict[str, Any]]: Информация о роли пользователя или None
        """
        try:
            # Если ID пользователя не указан, используем текущего пользователя
            if user_id is None:
                if not self.current_user:
                    return None
                user_id = self.current_user['id']
            
            # Получаем роль пользователя
            query = """
            SELECT r.* FROM roles r
            JOIN users u ON r.id = u.role_id
            WHERE u.id = ?
            """
            role_data = app_context.db_manager.execute_query(query, (user_id,))
            
            if not role_data:
                return None
            
            return role_data[0]
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении роли пользователя ID={user_id}: {e}")
            log_exception(self.logger, f"Ошибка получения роли пользователя")
            return None
    
    def get_user_permissions(self, app_context, user_id: int = None) -> List[str]:
        """
        Получение списка разрешений пользователя
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя (если None, используется текущий пользователь)
            
        Returns:
            List[str]: Список кодов разрешений пользователя
        """
        try:
            # Если ID пользователя не указан, используем текущего пользователя
            if user_id is None:
                if not self.current_user:
                    return []
                user_id = self.current_user['id']
            
            # Проверяем кэш
            if user_id in self._user_permissions_cache:
                return self._user_permissions_cache[user_id]
            
            # Получаем разрешения пользователя
            query = """
            SELECT p.name FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            JOIN users u ON rp.role_id = u.role_id
            WHERE u.id = ?
            """
            permissions_data = app_context.db_manager.execute_query(query, (user_id,))
            
            # Извлекаем названия разрешений
            permissions = [p['name'] for p in permissions_data]
            
            # Сохраняем в кэш
            self._user_permissions_cache[user_id] = permissions
            
            return permissions
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении разрешений пользователя ID={user_id}: {e}")
            log_exception(self.logger, f"Ошибка получения разрешений пользователя")
            return []
    
    def has_permission(self, app_context, permission: str, user_id: int = None) -> bool:
        """
        Проверка наличия разрешения у пользователя
        
        Args:
            app_context: Контекст приложения
            permission: Код разрешения
            user_id: ID пользователя (если None, используется текущий пользователь)
            
        Returns:
            bool: True, если у пользователя есть разрешение, иначе False
        """
        # Получаем разрешения пользователя
        permissions = self.get_user_permissions(app_context, user_id)
        
        # Проверяем наличие разрешения
        return permission in permissions
    
    def get_all_users(self, app_context) -> List[Dict[str, Any]]:
        """
        Получение списка всех пользователей
        
        Args:
            app_context: Контекст приложения
            
        Returns:
            List[Dict[str, Any]]: Список пользователей
        """
        try:
            query = """
            SELECT u.*, r.name as role_name FROM users u
            JOIN roles r ON u.role_id = r.id
            ORDER BY u.id
            """
            return app_context.db_manager.execute_query(query)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка пользователей: {e}")
            log_exception(self.logger, "Ошибка получения списка пользователей")
            return []
    
    def get_user(self, app_context, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение информации о пользователе
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя
            
        Returns:
            Optional[Dict[str, Any]]: Информация о пользователе или None
        """
        try:
            query = """
            SELECT u.*, r.name as role_name FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.id = ?
            """
            user_data = app_context.db_manager.execute_query(query, (user_id,))
            
            if not user_data:
                return None
            
            return user_data[0]
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о пользователе ID={user_id}: {e}")
            log_exception(self.logger, "Ошибка получения информации о пользователе")
            return None
    
    def create_user(
        self, 
        app_context, 
        username: str, 
        password: str, 
        email: str = None, 
        full_name: str = None, 
        role_id: int = 3,
        is_active: bool = True
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Создание нового пользователя
        
        Args:
            app_context: Контекст приложения
            username: Имя пользователя
            password: Пароль
            email: Email (опционально)
            full_name: Полное имя (опционально)
            role_id: ID роли (по умолчанию 3 - Наблюдатель)
            is_active: Активен ли пользователь (по умолчанию True)
            
        Returns:
            Tuple[bool, str, Optional[int]]: (Успех операции, Сообщение, ID созданного пользователя)
        """
        try:
            # Проверяем, существует ли пользователь с таким именем
            check_query = "SELECT id FROM users WHERE username = ?"
            check_result = app_context.db_manager.execute_query(check_query, (username,))
            
            if check_result:
                return False, "Пользователь с таким именем уже существует", None
            
            # Хешируем пароль
            password_hash = Hasher.hash_password(password)
            
            # Создаем пользователя
            query = """
            INSERT INTO users (username, password_hash, email, full_name, role_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            params = (username, password_hash, email, full_name, role_id, 1 if is_active else 0)
            
            # Выполняем запрос
            app_context.db_manager.execute_query(query, params)
            
            # Получаем ID созданного пользователя
            get_id_query = "SELECT id FROM users WHERE username = ?"
            id_result = app_context.db_manager.execute_query(get_id_query, (username,))
            
            if not id_result:
                return False, "Ошибка при создании пользователя", None
            
            user_id = id_result[0]['id']
            
            self.logger.info(f"Создан новый пользователь: {username} (ID={user_id})")
            return True, "Пользователь успешно создан", user_id
        
        except Exception as e:
            self.logger.error(f"Ошибка при создании пользователя {username}: {e}")
            log_exception(self.logger, f"Ошибка создания пользователя {username}")
            return False, f"Ошибка при создании пользователя: {e}", None
    
    def update_user(
        self, 
        app_context, 
        user_id: int, 
        username: str = None, 
        email: str = None, 
        full_name: str = None, 
        role_id: int = None,
        is_active: bool = None
    ) -> Tuple[bool, str]:
        """
        Обновление информации о пользователе
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя
            username: Новое имя пользователя (опционально)
            email: Новый Email (опционально)
            full_name: Новое полное имя (опционально)
            role_id: Новый ID роли (опционально)
            is_active: Новый статус активности (опционально)
            
        Returns:
            Tuple[bool, str]: (Успех операции, Сообщение)
        """
        try:
            # Проверяем, существует ли пользователь
            check_query = "SELECT id FROM users WHERE id = ?"
            check_result = app_context.db_manager.execute_query(check_query, (user_id,))
            
            if not check_result:
                return False, "Пользователь не найден"
            
            # Составляем запрос и параметры для обновления
            update_fields = []
            update_params = []
            
            if username is not None:
                # Проверяем, существует ли пользователь с таким именем
                check_username_query = "SELECT id FROM users WHERE username = ? AND id != ?"
                check_username_result = app_context.db_manager.execute_query(
                    check_username_query, (username, user_id)
                )
                
                if check_username_result:
                    return False, "Пользователь с таким именем уже существует"
                
                update_fields.append("username = ?")
                update_params.append(username)
            
            if email is not None:
                update_fields.append("email = ?")
                update_params.append(email)
            
            if full_name is not None:
                update_fields.append("full_name = ?")
                update_params.append(full_name)
            
            if role_id is not None:
                update_fields.append("role_id = ?")
                update_params.append(role_id)
            
            if is_active is not None:
                update_fields.append("is_active = ?")
                update_params.append(1 if is_active else 0)
            
            if not update_fields:
                return True, "Нет данных для обновления"
            
            # Формируем запрос
            query = f"""
            UPDATE users
            SET {', '.join(update_fields)}
            WHERE id = ?
            """
            update_params.append(user_id)
            
            # Выполняем запрос
            app_context.db_manager.execute_query(query, tuple(update_params))
            
            # Если обновляем текущего пользователя, обновляем его данные
            if self.current_user and self.current_user['id'] == user_id:
                # Получаем обновленную информацию о пользователе
                get_user_query = "SELECT * FROM users WHERE id = ?"
                user_data = app_context.db_manager.execute_query(get_user_query, (user_id,))
                
                if user_data:
                    self.current_user = user_data[0]
            
            # Очищаем кэш разрешений для пользователя
            if user_id in self._user_permissions_cache:
                del self._user_permissions_cache[user_id]
            
            self.logger.info(f"Обновлена информация о пользователе ID={user_id}")
            return True, "Информация о пользователе успешно обновлена"
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении пользователя ID={user_id}: {e}")
            log_exception(self.logger, f"Ошибка обновления пользователя")
            return False, f"Ошибка при обновлении пользователя: {e}"
    
    def change_password(
        self, 
        app_context, 
        user_id: int, 
        new_password: str, 
        current_password: str = None
    ) -> Tuple[bool, str]:
        """
        Изменение пароля пользователя
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя
            new_password: Новый пароль
            current_password: Текущий пароль (требуется для смены своего пароля)
            
        Returns:
            Tuple[bool, str]: (Успех операции, Сообщение)
        """
        try:
            # Проверяем, существует ли пользователь
            check_query = "SELECT * FROM users WHERE id = ?"
            check_result = app_context.db_manager.execute_query(check_query, (user_id,))
            
            if not check_result:
                return False, "Пользователь не найден"
            
            user = check_result[0]
            
            # Если меняем свой пароль, проверяем текущий пароль
            if self.current_user and self.current_user['id'] == user_id and current_password:
                if not Hasher.verify_password(user['password_hash'], current_password):
                    return False, "Неверный текущий пароль"
            
            # Хешируем новый пароль
            new_password_hash = Hasher.hash_password(new_password)
            
            # Обновляем пароль
            query = "UPDATE users SET password_hash = ? WHERE id = ?"
            app_context.db_manager.execute_query(query, (new_password_hash, user_id))
            
            # Если меняем пароль текущего пользователя, обновляем его данные
            if self.current_user and self.current_user['id'] == user_id:
                self.current_user['password_hash'] = new_password_hash
            
            self.logger.info(f"Изменен пароль пользователя ID={user_id}")
            return True, "Пароль успешно изменен"
        
        except Exception as e:
            self.logger.error(f"Ошибка при изменении пароля пользователя ID={user_id}: {e}")
            log_exception(self.logger, f"Ошибка изменения пароля")
            return False, f"Ошибка при изменении пароля: {e}"
    
    def delete_user(self, app_context, user_id: int) -> Tuple[bool, str]:
        """
        Удаление пользователя
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя
            
        Returns:
            Tuple[bool, str]: (Успех операции, Сообщение)
        """
        try:
            # Проверяем, существует ли пользователь
            check_query = "SELECT id FROM users WHERE id = ?"
            check_result = app_context.db_manager.execute_query(check_query, (user_id,))
            
            if not check_result:
                return False, "Пользователь не найден"
            
            # Проверяем, не является ли пользователь текущим
            if self.current_user and self.current_user['id'] == user_id:
                return False, "Невозможно удалить текущего пользователя"
            
            # Проверяем, не является ли пользователь администратором с ID=1
            if user_id == 1:
                return False, "Невозможно удалить встроенного администратора"
            
            # Удаляем пользователя
            query = "DELETE FROM users WHERE id = ?"
            app_context.db_manager.execute_query(query, (user_id,))
            
            # Очищаем кэш разрешений для пользователя
            if user_id in self._user_permissions_cache:
                del self._user_permissions_cache[user_id]
            
            self.logger.info(f"Удален пользователь ID={user_id}")
            return True, "Пользователь успешно удален"
        
        except Exception as e:
            self.logger.error(f"Ошибка при удалении пользователя ID={user_id}: {e}")
            log_exception(self.logger, f"Ошибка удаления пользователя")
            return False, f"Ошибка при удалении пользователя: {e}"
    
    def get_all_roles(self, app_context) -> List[Dict[str, Any]]:
        """
        Получение списка всех ролей
        
        Args:
            app_context: Контекст приложения
            
        Returns:
            List[Dict[str, Any]]: Список ролей
        """
        try:
            query = "SELECT * FROM roles ORDER BY id"
            return app_context.db_manager.execute_query(query)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка ролей: {e}")
            log_exception(self.logger, "Ошибка получения списка ролей")
            return []
    
    def get_all_permissions(self, app_context) -> List[Dict[str, Any]]:
        """
        Получение списка всех разрешений
        
        Args:
            app_context: Контекст приложения
            
        Returns:
            List[Dict[str, Any]]: Список разрешений
        """
        try:
            query = "SELECT * FROM permissions ORDER BY id"
            return app_context.db_manager.execute_query(query)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка разрешений: {e}")
            log_exception(self.logger, "Ошибка получения списка разрешений")
            return []
    
    def get_role_permissions(self, app_context, role_id: int) -> List[int]:
        """
        Получение списка ID разрешений для роли
        
        Args:
            app_context: Контекст приложения
            role_id: ID роли
            
        Returns:
            List[int]: Список ID разрешений
        """
        try:
            query = "SELECT permission_id FROM role_permissions WHERE role_id = ?"
            permissions_data = app_context.db_manager.execute_query(query, (role_id,))
            
            return [p['permission_id'] for p in permissions_data]
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении разрешений для роли ID={role_id}: {e}")
            log_exception(self.logger, "Ошибка получения разрешений для роли")
            return []
    
    def update_role_permissions(
        self, 
        app_context, 
        role_id: int, 
        permission_ids: List[int]
    ) -> Tuple[bool, str]:
        """
        Обновление разрешений для роли
        
        Args:
            app_context: Контекст приложения
            role_id: ID роли
            permission_ids: Список ID разрешений
            
        Returns:
            Tuple[bool, str]: (Успех операции, Сообщение)
        """
        try:
            # Проверяем, существует ли роль
            check_query = "SELECT id FROM roles WHERE id = ?"
            check_result = app_context.db_manager.execute_query(check_query, (role_id,))
            
            if not check_result:
                return False, "Роль не найдена"
            
            # Удаляем существующие связи
            delete_query = "DELETE FROM role_permissions WHERE role_id = ?"
            app_context.db_manager.execute_query(delete_query, (role_id,))
            
            # Добавляем новые связи
            insert_query = "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)"
            
            for permission_id in permission_ids:
                app_context.db_manager.execute_query(insert_query, (role_id, permission_id))
            
            # Очищаем кэш разрешений для всех пользователей с этой ролью
            self._user_permissions_cache.clear()
            
            self.logger.info(f"Обновлены разрешения для роли ID={role_id}")
            return True, "Разрешения для роли успешно обновлены"
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении разрешений для роли ID={role_id}: {e}")
            log_exception(self.logger, "Ошибка обновления разрешений для роли")
            return False, f"Ошибка при обновлении разрешений для роли: {e}" 