import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

import uvicorn
from aiogram.enums import ParseMode
from aiogram.types import Update
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from fastapi import FastAPI
from starlette.responses import Response

from .app.routes import app_routers_include
from .app.middlewares import app_middlewares_register
from .bot import commands
from .bot.routes import bot_routers_include
from .bot.middlewares import bot_middlewares_register
from .config import load_config
from .db.database import Database

config = load_config()
webhook_path = config.webhook.PATH + config.bot.TOKEN
webhook_url = config.webhook.DOMAIN + webhook_path

app = FastAPI()
db = Database(config.database)
bot = Bot(
    token=config.bot.TOKEN,
    parse_mode=ParseMode.HTML,
)
dp = Dispatcher(
    storage=RedisStorage.from_url(config.redis.dsn()),
    config=config,
)


async def bot_webhook(update: dict) -> Response:
    """
    Bot webhook endpoint. Receives updates and feeds them to the bot dispatcher.

    :param update: The update received from the bot webhook.
    """
    await dp.feed_update(bot=bot, update=Update(**update))

    return Response()


@app.on_event("startup")
async def on_startup() -> None:
    """
    Startup event handler. This runs when the app starts.
    """
    await db.init()
    await commands.setup(bot)
    await bot.set_webhook(url=webhook_url, allowed_updates=dp.resolve_used_update_types())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """
    Shutdown event handler. This runs when the app shuts down.
    """
    await db.close()
    await commands.delete(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()


# Register app middlewares
app_middlewares_register(app=app, bot=bot, config=config, session=db.session)
# Include app routes
app_routers_include(app=app)

# Register bot webhook
app.add_api_route(webhook_path, endpoint=bot_webhook, methods=["POST"])
# Register bot middlewares
bot_middlewares_register(dp=dp, config=config, session=db.session)
# Include bot routers
bot_routers_include(dp=dp)

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # noqa
        handlers=[
            TimedRotatingFileHandler(
                filename=f"logs/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log",
                when="midnight",
                interval=1,
                backupCount=1,
            ),
            logging.StreamHandler(),
        ]
    )
    # Set logging level for aiogram to CRITICAL
    aiogram_logger = logging.getLogger("aiogram.event")
    aiogram_logger.setLevel(logging.CRITICAL)
    # Run app with uvicorn
    uvicorn.run(app, host=config.app.HOST, port=config.app.PORT)
