# api.py
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, create_engine
from pydantic import BaseModel
import os
from bot import Log
from dotenv import load_dotenv
import logging

load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("api_logger")

# Настройка БД
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class LogSchema(BaseModel):
    """ Модель Pydantic """
    id: int
    user_id: int
    command: str
    timestamp: datetime
    response: str

    class Config:
        orm_mode = True


app = FastAPI(
    title='Weather Bot Logs API',
    description='API для просмотра истории запросов пользователей Telegram-бота погоды.',
    version='1.0.0',
)


# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get('/logs', response_model=List[LogSchema], summary="Получить все логи",
         description="Возвращает список всех запросов пользователей с поддержкой пагинации и фильтрации по дате.")
def get_logs(
    offset: int = Query(0, ge=0, description="Количество пропущенных записей"),
    limit: int = Query(10, ge=1, le=100, description="Количество возвращаемых записей"),
    start_date: Optional[datetime] = Query(None, description="Начальная дата в формате YYYY-MM-DD"),
    end_date: Optional[datetime] = Query(None, description="Конечная дата в формате YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(Log)
        if start_date:
            query = query.filter(Log.timestamp >= start_date)
        if end_date:
            query = query.filter(Log.timestamp <= end_date)
        logs = query.order_by(desc(Log.timestamp)).offset(offset).limit(limit).all()
        logger.info(f"Получен список логов: offset={offset}, limit={limit}, start_date={start_date}, end_date={end_date}")
        return logs
    except Exception as e:
        logger.error(f"Ошибка при получении логов: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.get('/logs/{user_id}', response_model=List[LogSchema], summary="Получить логи пользователя",
         description="Возвращает список запросов конкретного пользователя с поддержкой пагинации и фильтрации по дате.")
def get_user_logs(
    user_id: int,
    offset: int = Query(0, ge=0, description="Количество пропущенных записей"),
    limit: int = Query(10, ge=1, le=100, description="Количество возвращаемых записей"),
    start_date: Optional[datetime] = Query(None, description="Начальная дата в формате YYYY-MM-DD"),
    end_date: Optional[datetime] = Query(None, description="Конечная дата в формате YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(Log).filter(Log.user_id == user_id)
        if start_date:
            query = query.filter(Log.timestamp >= start_date)
        if end_date:
            query = query.filter(Log.timestamp <= end_date)
        logs = query.order_by(desc(Log.timestamp)).offset(offset).limit(limit).all()
        if not logs:
            logger.warning(f"Логи не найдены для пользователя ID={user_id}")
            raise HTTPException(status_code=404, detail="Логи не найдены для данного пользователя")
        logger.info(f"Получен список логов для пользователя ID={user_id}: offset={offset}, limit={limit}, start_date={start_date}, end_date={end_date}")
        return logs
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Ошибка при получении логов пользователя ID={user_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
