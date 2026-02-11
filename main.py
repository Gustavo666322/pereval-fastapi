import os
from dotenv import load_dotenv


load_dotenv()


from datetime import datetime
import logging
from enum import Enum


from typing import Optional, List, Dict, Any


from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field, validator


from database import mountain_pass_dao, DatabaseManager, MountainPassDAO
# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(
    title="Mountain Passes API",
    description="API для управления данными о горных перевалах",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# Модели данных Pydantic
class Coords(BaseModel):
    """Модель координат"""
    latitude: float = Field(..., ge=-90, le=90, description="Широта от -90 до 90")
    longitude: float = Field(..., ge=-180, le=180, description="Долгота от -180 до 180")
    height: int = Field(..., ge=0, le=9000, description="Высота от 0 до 9000 метров")


class Level(BaseModel):
    """Модель уровня сложности"""
    winter: Optional[str] = Field(None, pattern='^(1A|1B|2A|2B|3A|3B)$')
    summer: Optional[str] = Field(None, pattern='^(1A|1B|2A|2B|3A|3B)$')
    autumn: Optional[str] = Field(None, pattern='^(1A|1B|2A|2B|3A|3B)$')
    spring: Optional[str] = Field(None, pattern='^(1A|1B|2A|2B|3A|3B)$')

class Image(BaseModel):
    """Модель изображения"""
    title: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1)


class User(BaseModel):
    """Модель пользователя"""
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    fam: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=50)
    otc: Optional[str] = Field(None, max_length=50)


class MountainPassCreate(BaseModel):
    """Модель для создания перевала"""
    beautyTitle: Optional[str] = Field(None, max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    other_titles: Optional[str] = Field(None, max_length=255)
    connect: Optional[str] = Field(None, max_length=255)

    user: User
    coords: Coords

    level: Optional[Level] = None
    images: Optional[List[Image]] = Field(None, max_items=10)

    @validator('images')
    def validate_images(cls, v):
        if v and len(v) > 10:
            raise ValueError('Не более 10 изображений')
        return v


class MountainPassResponse(BaseModel):
    """Модель ответа при создании/получении перевала"""
    id: int
    status: str
    message: Optional[str] = None


class MountainPassStatus(str, Enum):
    """Статусы перевала"""
    NEW = "new"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# Dependency для получения DAO
def get_mountain_pass_dao():
    """Dependency injection для MountainPassDAO"""
    return mountain_pass_dao


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Mountain Passes API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "submit_data": "POST /submitData",
            "get_pass": "GET /submitData/{id}"
        }
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    try:
        # Проверяем подключение к БД
        db_manager = DatabaseManager()
        conn = db_manager.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_manager.close_connection()

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: {str(e)}"
        )


@app.post(
    "/submitData",
    response_model=MountainPassResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить новый перевал",
    description="""
    Добавляет информацию о новом горном перевале в базу данных.

    После успешного добавления переводу автоматически присваивается статус 'new'.
    """
)
async def submit_data(
        data: MountainPassCreate,
        dao: MountainPassDAO = Depends(get_mountain_pass_dao)
):
    """
    Создание новой записи о перевале

    - **beautyTitle**: Красивое название перевала
    - **title**: Официальное название
    - **other_titles**: Другие названия
    - **connect**: Что соединяет перевал
    - **user**: Информация о пользователе (отправителе)
    - **coords**: Координаты перевала
    - **level**: Уровни сложности по сезонам
    - **images**: Список изображений (до 10)
    """
    try:
        logger.info(f"Получен запрос на добавление перевала: {data.title}")

        # Преобразуем данные в формат для БД
        pass_data = data.dict()

        # Добавляем перевал в базу данных
        pass_id = dao.add_mountain_pass(pass_data)

        if pass_id is None:
            logger.error("Не удалось добавить перевал в БД")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка при сохранении данных в базу данных"
            )

        logger.info(f"Перевал успешно добавлен с ID: {pass_id}")

        return MountainPassResponse(
            id=pass_id,
            status="new",
            message="Данные успешно отправлены на модерацию"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@app.get(
    "/submitData/{pass_id}",
    summary="Получить информацию о перевале",
    description="Получение полной информации о перевале по его ID"
)
async def get_mountain_pass(
        pass_id: int,
        dao: MountainPassDAO = Depends(get_mountain_pass_dao)
):
    """Получение информации о перевале по ID"""
    try:
        logger.info(f"Запрос информации о перевале с ID: {pass_id}")

        pass_data = dao.get_pass_by_id(pass_id)

        if pass_data is None:
            logger.warning(f"Перевал с ID {pass_id} не найден")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Перевал с ID {pass_id} не найден"
            )

        return pass_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении перевала: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@app.on_event("startup")
async def startup_event():
    """Действия при запуске приложения"""
    logger.info("Запуск Mountain Passes API...")

    # Проверяем наличие необходимых переменных окружения
    required_env_vars = ['FSTR_DB_LOGIN', 'FSTR_DB_PASS']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        logger.warning(f"Отсутствуют переменные окружения: {missing_vars}")

    logger.info("Приложение успешно запущено")


@app.on_event("shutdown")
async def shutdown_event():
    """Действия при завершении работы приложения"""
    logger.info("Завершение работы Mountain Passes API...")

    # Закрываем соединение с БД
    try:
        db_manager = DatabaseManager()
        db_manager.close_connection()
        logger.info("Соединения с БД закрыты")
    except Exception as e:
        logger.error(f"Ошибка при закрытии соединений: {e}")