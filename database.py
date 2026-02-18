import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Исключение для ошибок подключения к БД"""
    pass


class DatabaseManager:
    """Класс для управления подключением и операциями с базой данных"""

    def __init__(self):
        self._connection = None

    @property
    def connection_params(self) -> Dict[str, str]:
        params = {
            'host': os.getenv('FSTR_DB_HOST', 'localhost'),
            'port': os.getenv('FSTR_DB_PORT', '5432'),
            'database': os.getenv('FSTR_DB_NAME', 'pereval'),
            'user': os.getenv('FSTR_DB_LOGIN', 'postgres'),
        }

        password = os.getenv('FSTR_DB_PASS')
        if password and password.strip():
            params['password'] = password
            logger.info("✅ Подключение с паролем")
        else:
            logger.warning("⚠️ Подключение БЕЗ пароля")

        return params

    def get_connection(self):
        """Создание подключения к базе данных"""
        if self._connection is None or self._connection.closed:
            try:
                params = self.connection_params
                self._connection = psycopg2.connect(
                    **params,
                    cursor_factory=RealDictCursor
                )
                logger.info("Успешное подключение к базе данных")
            except Exception as e:
                logger.error(f"Ошибка подключения к БД: {e}")
                raise DatabaseConnectionError(f"Не удалось подключиться к БД: {e}")
        return self._connection

    def close_connection(self):
        """Закрытие подключения к базе данных"""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None
            logger.info("Подключение к БД закрыто")


class MountainPassDAO:
    """Data Access Object для работы с перевалами"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def add_mountain_pass(self, pass_data: Dict[str, Any]) -> Optional[int]:
        """
        Добавление нового перевала в базу данных

        Args:
            pass_data: Словарь с данными перевала

        Returns:
            ID созданного перевала или None в случае ошибки
        """
        connection = self.db_manager.get_connection()

        try:
            with connection.cursor() as cursor:
                # Начинаем транзакцию
                connection.autocommit = False

                # 1. Сначала добавляем пользователя или находим существующего
                user_id = self._get_or_create_user(cursor, pass_data['user'])

                # 2. Добавляем перевал
                pass_query = """
                             INSERT INTO mountain_passes
                             (beauty_title, title, other_titles, connect, user_id,
                              latitude, longitude, height, add_time, status)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id \
                             """

                cursor.execute(pass_query, (
                    pass_data.get('beautyTitle', ''),
                    pass_data['title'],
                    pass_data.get('other_titles', ''),
                    pass_data.get('connect', ''),
                    user_id,
                    pass_data['coords']['latitude'],
                    pass_data['coords']['longitude'],
                    pass_data['coords']['height'],
                    datetime.now(),
                    'new'  # Статус по умолчанию
                ))

                pass_id = cursor.fetchone()['id']

                # 3. Добавляем уровни сложности
                if 'level' in pass_data:
                    self._add_difficulty_levels(cursor, pass_id, pass_data['level'])

                # 4. Добавляем изображения
                if 'images' in pass_data:
                    self._add_images(cursor, pass_id, pass_data['images'])

                # Фиксируем транзакцию
                connection.commit()

                logger.info(f"Перевал успешно добавлен с ID: {pass_id}")
                return pass_id

        except Exception as e:
            connection.rollback()
            logger.error(f"Ошибка при добавлении перевала: {e}")
            return None

    def _get_or_create_user(self, cursor, user_data: Dict[str, Any]) -> int:
        """Получение ID пользователя или создание нового"""
        try:
            # Проверяем, существует ли пользователь
            check_query = """
                          SELECT id
                          FROM users
                          WHERE email = %s
                             OR phone = %s LIMIT 1 \
                          """

            cursor.execute(check_query, (
                user_data.get('email', ''),
                user_data.get('phone', '')
            ))

            existing_user = cursor.fetchone()

            if existing_user:
                return existing_user['id']

            # Создаем нового пользователя
            insert_query = """
                           INSERT INTO users (email, phone, fam, name, otc)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id \
                           """

            cursor.execute(insert_query, (
                user_data.get('email', ''),
                user_data.get('phone', ''),
                user_data['fam'],
                user_data['name'],
                user_data.get('otc', '')
            ))

            return cursor.fetchone()['id']

        except Exception as e:
            logger.error(f"Ошибка при работе с пользователем: {e}")
            raise

    def _add_difficulty_levels(self, cursor, pass_id: int, level_data: Dict[str, str]):
        """Добавление уровней сложности"""
        seasons = ['winter', 'summer', 'autumn', 'spring']

        for season in seasons:
            if season in level_data and level_data[season]:
                query = """
                        INSERT INTO difficulty_levels (pass_id, season, level)
                        VALUES (%s, %s, %s) ON CONFLICT (pass_id, season) DO
                        UPDATE SET level = EXCLUDED.level \
                        """

                cursor.execute(query, (pass_id, season, level_data[season]))

    def _add_images(self, cursor, pass_id: int, images: List[Dict[str, Any]]):
        """Добавление изображений"""
        for img in images:
            query = """
                    INSERT INTO images (pass_id, title, img_url)
                    VALUES (%s, %s, %s) \
                    """

            cursor.execute(query, (
                pass_id,
                img.get('title', ''),
                img.get('url', '')
            ))

    def get_pass_by_id(self, pass_id: int) -> Optional[Dict[str, Any]]:
        """Получение перевала по ID"""
        connection = self.db_manager.get_connection()

        try:
            with connection.cursor() as cursor:
                # Получаем основную информацию о перевале
                query = """
                        SELECT mp.*,
                               u.email,
                               u.phone,
                               u.fam,
                               u.name,
                               u.otc
                        FROM mountain_passes mp
                                 JOIN users u ON mp.user_id = u.id
                        WHERE mp.id = %s \
                        """

                cursor.execute(query, (pass_id,))
                pass_data = cursor.fetchone()

                if not pass_data:
                    return None

                # Получаем уровни сложности
                level_query = """
                              SELECT season, level
                              FROM difficulty_levels
                              WHERE pass_id = %s \
                              """
                cursor.execute(level_query, (pass_id,))
                levels = cursor.fetchall()

                # Получаем изображения
                images_query = """
                               SELECT title, img_url
                               FROM images
                               WHERE pass_id = %s \
                               """
                cursor.execute(images_query, (pass_id,))
                images = cursor.fetchall()

                # Формируем ответ
                result = {
                    'id': pass_data['id'],
                    'beauty_title': pass_data['beauty_title'],
                    'title': pass_data['title'],
                    'other_titles': pass_data['other_titles'],
                    'connect': pass_data['connect'],
                    'user': {
                        'email': pass_data['email'],
                        'phone': pass_data['phone'],
                        'fam': pass_data['fam'],
                        'name': pass_data['name'],
                        'otc': pass_data['otc']
                    },
                    'coords': {
                        'latitude': float(pass_data['latitude']),
                        'longitude': float(pass_data['longitude']),
                        'height': pass_data['height']
                    },
                    'status': pass_data['status'],
                    'add_time': pass_data['add_time'].isoformat() if pass_data['add_time'] else None,
                    'level': {l['season']: l['level'] for l in levels},
                    'images': [
                        {'title': img['title'], 'url': img['img_url']}
                        for img in images
                    ]
                }

                return result

        except Exception as e:
            logger.error(f"Ошибка при получении перевала: {e}")
            return None

    def update_mountain_pass(self, pass_id: int, pass_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновление существующего перевала, если он в статусе 'new'

        Args:
            pass_id: ID перевала
            pass_data: Новые данные перевала

        Returns:
            Словарь с результатом операции:
            {
                'state': 1 или 0,
                'message': описание результата
            }
        """
        connection = self.db_manager.get_connection()

        try:
            with connection.cursor() as cursor:
                # Проверяем существование и статус перевала
                check_query = """
                              SELECT status, user_id
                              FROM mountain_passes
                              WHERE id = %s
                              """
                cursor.execute(check_query, (pass_id,))
                existing_pass = cursor.fetchone()

                if not existing_pass:
                    return {
                        'state': 0,
                        'message': f'Перевал с ID {pass_id} не найден'
                    }

                if existing_pass['status'] != 'new':
                    return {
                        'state': 0,
                        'message': f'Редактирование невозможно: перевал в статусе "{existing_pass["status"]}". Доступно только для статуса "new"'
                    }

                # Начинаем транзакцию
                connection.autocommit = False

                # Проверяем, что не пытаемся изменить данные пользователя
                if 'user' in pass_data:
                    # Проверяем, совпадает ли пользователь
                    user_query = "SELECT email, phone, fam, name, otc FROM users WHERE id = %s"
                    cursor.execute(user_query, (existing_pass['user_id'],))
                    existing_user = cursor.fetchone()

                    new_user = pass_data['user']

                    # Проверяем изменения в защищенных полях
                    protected_fields = ['email', 'phone', 'fam', 'name', 'otc']
                    changed_fields = []

                    for field in protected_fields:
                        old_value = existing_user.get(field)
                        new_value = new_user.get(field)

                        # Приводим None к пустой строке для сравнения
                        old_value = old_value if old_value is not None else ''
                        new_value = new_value if new_value is not None else ''

                        if old_value != new_value:
                            changed_fields.append(field)

                    if changed_fields:
                        return {
                            'state': 0,
                            'message': f'Редактирование защищенных полей пользователя запрещено: {", ".join(changed_fields)}'
                        }

                # Обновляем данные перевала (без изменения user_id и статуса)
                update_query = """
                               UPDATE mountain_passes
                               SET beauty_title = %s,
                                   title        = %s,
                                   other_titles = %s,
                                   connect      = %s,
                                   latitude     = %s,
                                   longitude    = %s,
                                   height       = %s
                               WHERE id = %s \
                               """

                cursor.execute(update_query, (
                    pass_data.get('beautyTitle', ''),
                    pass_data['title'],
                    pass_data.get('other_titles', ''),
                    pass_data.get('connect', ''),
                    pass_data['coords']['latitude'],
                    pass_data['coords']['longitude'],
                    pass_data['coords']['height'],
                    pass_id
                ))

                # Обновляем уровни сложности
                if 'level' in pass_data:
                    # Удаляем старые уровни
                    cursor.execute("DELETE FROM difficulty_levels WHERE pass_id = %s", (pass_id,))
                    # Добавляем новые
                    self._add_difficulty_levels(cursor, pass_id, pass_data['level'])

                # Обновляем изображения
                if 'images' in pass_data:
                    # Удаляем старые изображения
                    cursor.execute("DELETE FROM images WHERE pass_id = %s", (pass_id,))
                    # Добавляем новые
                    self._add_images(cursor, pass_id, pass_data['images'])

                # Фиксируем транзакцию
                connection.commit()

                logger.info(f"Перевал с ID {pass_id} успешно обновлен")
                return {
                    'state': 1,
                    'message': 'Запись успешно обновлена'
                }

        except Exception as e:
            connection.rollback()
            logger.error(f"Ошибка при обновлении перевала {pass_id}: {e}")
            return {
                'state': 0,
                'message': f'Ошибка при обновлении записи: {str(e)}'
            }

    def get_passes_by_user_email(self, email: str) -> List[Dict[str, Any]]:
        """
        Получение всех перевалов, добавленных пользователем с указанным email

        Args:
            email: Email пользователя

        Returns:
            Список перевалов пользователя
        """
        connection = self.db_manager.get_connection()

        try:
            with connection.cursor() as cursor:
                query = """
                        SELECT mp.*,
                               u.email,
                               u.phone,
                               u.fam,
                               u.name,
                               u.otc
                        FROM mountain_passes mp
                                 JOIN users u ON mp.user_id = u.id
                        WHERE u.email = %s
                        ORDER BY mp.add_time DESC
                        """

                cursor.execute(query, (email,))
                passes = cursor.fetchall()

                result = []
                for pass_data in passes:
                    # Получаем уровни сложности
                    level_query = """
                                  SELECT season, level
                                  FROM difficulty_levels
                                  WHERE pass_id = %s \
                                  """
                    cursor.execute(level_query, (pass_data['id'],))
                    levels = cursor.fetchall()

                    # Получаем изображения
                    images_query = """
                                   SELECT title, img_url
                                   FROM images
                                   WHERE pass_id = %s \
                                   """
                    cursor.execute(images_query, (pass_data['id'],))
                    images = cursor.fetchall()

                    # Формируем ответ
                    pass_info = {
                        'id': pass_data['id'],
                        'beauty_title': pass_data['beauty_title'],
                        'title': pass_data['title'],
                        'other_titles': pass_data['other_titles'],
                        'connect': pass_data['connect'],
                        'user': {
                            'email': pass_data['email'],
                            'phone': pass_data['phone'],
                            'fam': pass_data['fam'],
                            'name': pass_data['name'],
                            'otc': pass_data['otc']
                        },
                        'coords': {
                            'latitude': float(pass_data['latitude']),
                            'longitude': float(pass_data['longitude']),
                            'height': pass_data['height']
                        },
                        'status': pass_data['status'],
                        'add_time': pass_data['add_time'].isoformat() if pass_data['add_time'] else None,
                        'level': {l['season']: l['level'] for l in levels},
                        'images': [
                            {'title': img['title'], 'url': img['img_url']}
                            for img in images
                        ]
                    }
                    result.append(pass_info)

                return result

        except Exception as e:
            logger.error(f"Ошибка при получении перевалов пользователя {email}: {e}")
            return []


# Синглтон для доступа к DAO
_db_manager = DatabaseManager()
mountain_pass_dao = MountainPassDAO(_db_manager)