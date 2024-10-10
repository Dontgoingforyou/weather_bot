import os
import logging
import httpx
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ApplicationBuilder

from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from aiocache import cached, Cache
from aiocache.serializers import JsonSerializer

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка БД
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
Base = declarative_base()


class Log(Base):
    __tablename__ = 'logs'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False)
    command = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    response = Column(Text)


class UserSetting(Base):
    __tablename__ = 'user_settings'
    user_id = Column(BigInteger, primary_key=True, index=True)
    city = Column(String, nullable=False)


Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
WEATHER_URL = 'https://api.openweathermap.org/data/2.5/weather'


async def help_command(update: Update, context: CallbackContext):
    """Обработчик команды /help"""
    user_first_name = update.effective_user.first_name or "Пользователь"
    help_text = (
        f"👋 Привет, {user_first_name}!\n\n"
        "ℹ️ *Доступные команды:*\n"
        "/weather <город> - Получить текущую погоду в указанном городе.\n"
        "/weather - Получить текущую погоду в вашем любимом городе.\n"
        "/setcity <город> - Установить любимый город для постоянных запросов.\n"
        "/getcity - Получить ваш установленный любимый город.\n"
        "/help - Показать список доступных команд."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


# Настройка кэша (in-memory)
@cached(ttl=600, cache=Cache.MEMORY, serializer=JsonSerializer())  # Кэш на 10 минут
async def get_weather(city: str):
    """ Функция получения погоды с кэшированием """
    params = {
        'q': city,
        'appid': OPENWEATHERMAP_API_KEY,
        'units': 'metric',
        'lang': 'ru'
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(WEATHER_URL, params=params)
            response.raise_for_status()
            data = response.json()
            weather = {
                'город': data['name'],
                'температура': data['main']['temp'],
                'ощущается как': data['main']['feels_like'],
                'описание': data['weather'][0]['description'],
                'влажность': data['main']['humidity'],
                'скорость ветра': data['wind']['speed']
            }
            logger.info(f"Получены данные о погоде для города: {city}")
            return weather
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Ошибка при запросе погоды: {e}")
            return None
        except Exception as e:
            logger.error(f"Произошла ошибка: {e}")
            return None


async def weather_command(update: Update, context: CallbackContext):
    """ Обработчик команды /weather """
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} вызвал команду /weather")

    # Получение установленного города из базы данных
    db = SessionLocal()
    try:
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        logger.info(f"Настройки пользователя {user_id} получены: {setting.city if setting else 'Город не установлен'}")
    except Exception as e:
        logger.error(f"Ошибка при получении настроек пользователя {user_id}: {e}")
        await update.message.reply_text("Произошла ошибка при получении настроек. Пожалуйста, попробуйте позже.")
        return
    finally:
        db.close()

    # Определение города либо из аргументов команды, либо из настроек пользователя
    if len(context.args) == 0:
        if setting and setting.city:
            city = setting.city
            logger.info(f"Использование установленного города для пользователя {user_id}: {city}")
        else:
            message = "❓ Укажите город.\nПример: /weather Москва"
            await update.message.reply_text(message)
            logger.info(f"Пользователь {user_id} не указал город и не имеет установленного города.")
            return
    else:
        city = ' '.join(context.args)
        logger.info(f"Пользователь {user_id} запрашивает погоду для города: {city}")

    # Получение данных о погоде
    weather = await get_weather(city)
    if weather and weather.get('город'):
        message = (
            f"🌤 *Погода в {weather['город']}*\n"
            f"🌡 *Температура:* {weather['температура']}°C\n"
            f"🌡 *Ощущается как:* {weather['ощущается как']}°C\n"
            f"☁️ *Описание:* {weather['описание'].capitalize()}\n"
            f"💧 *Влажность:* {weather['влажность']}%\n"
            f"💨 *Скорость ветра:* {weather['скорость ветра']} м/с\n\n"
            "🔹 *Бот создан в качестве теста для компании BobrAi.*"
        )
    else:
        message = "❌ Не удалось получить данные о погоде. Проверьте название города."

    logger.info(f"Ответ пользователю {user_id}: {message}")

    # Отправка ответа пользователю
    try:
        await update.message.reply_text(message, parse_mode='Markdown')
        logger.info(f"Сообщение успешно отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
        return

    # Логирование запроса в базу данных
    db = SessionLocal()
    try:
        log_entry = Log(
            user_id=user_id,
            command=update.message.text,
            response=message
        )
        db.add(log_entry)
        db.commit()
        logger.info(f"Запрос пользователя {user_id} успешно залогирован.")
    except Exception as e:
        logger.error(f"Ошибка при логировании запроса пользователя {user_id}: {e}")
    finally:
        db.close()


async def set_city(update: Update, context: CallbackContext):
    """ Обработчик команды /setcity """
    user_id = update.effective_user.id
    if len(context.args) == 0:
        await update.message.reply_text("❓ Пожалуйста, укажите город.\nПример: /setcity Москва")
        logger.info(f"Пользователь {user_id} вызвал /setcity без указания города.")
        return
    city = ' '.join(context.args)
    logger.info(f"Пользователь {user_id} устанавливает город: {city}")
    db = SessionLocal()
    try:
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if setting:
            setting.city = city
            logger.info(f"Пользователь {user_id} изменил установленный город на: {city}")
        else:
            setting = UserSetting(user_id=user_id, city=city)
            db.add(setting)
            logger.info(f"Пользователь {user_id} установил новый город: {city}")
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка при установке города для пользователя {user_id}: {e}")
        await update.message.reply_text("❌ Произошла ошибка при установке города. Пожалуйста, попробуйте позже.")
        return
    finally:
        db.close()
    await update.message.reply_text(f"✅ Город установлен на {city}")


async def get_city(update: Update, context: CallbackContext):
    """ Обработчик команды /getcity """
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} вызвал команду /getcity")
    db = SessionLocal()
    try:
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if setting:
            message = f"📍 Ваш установленный город: {setting.city}"
            logger.info(f"Пользователь {user_id} имеет установленный город: {setting.city}")
        else:
            message = "❌ Город не установлен. Используйте /setcity <город> для установки."
            logger.info(f"Пользователь {user_id} не имеет установленного города.")
    except Exception as e:
        logger.error(f"Ошибка при получении настроек пользователя {user_id}: {e}")
        message = "❌ Произошла ошибка при получении настроек. Пожалуйста, попробуйте позже."
    finally:
        db.close()
    await update.message.reply_text(message)


def main():
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан в переменных окружения.")
        return

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(CommandHandler("setcity", set_city))
    application.add_handler(CommandHandler("getcity", get_city))

    # Запускаю бота
    logger.info("🔄 Запуск бота...")
    application.run_polling()


if __name__ == '__main__':
    main()
