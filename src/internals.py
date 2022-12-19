# pylint: disable=no-self-argument, arguments-differ
import logging
from os import getenv

CACHE_DIR = getenv("CACHE_DIR", "/tmp")
BUILD_ENV = getenv("BUILD_ENV", "development")
APP_ENV = getenv("APP_ENV", "Dev")
APP_NAME = getenv("APP_NAME", "trivialscan-monitor-queue")
DASHBOARD_URL = "https://www.trivialsec.com"
logger = logging.getLogger(__name__)
