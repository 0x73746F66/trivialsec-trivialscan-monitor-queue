# pylint: disable=no-self-argument, arguments-differ
import contextlib
import logging
import threading
import json
from inspect import getframeinfo, stack
from typing import Union
from time import sleep
from datetime import datetime, date
from os import getenv
from uuid import UUID
from ipaddress import (
    IPv4Address,
    IPv6Address,
    IPv4Network,
    IPv6Network,
)

import boto3
import requests
from lumigo_tracer import add_execution_tag, error as lumigo_error
from pydantic import (
    HttpUrl,
    AnyHttpUrl,
    PositiveInt,
    PositiveFloat,
)


DEFAULT_LOG_LEVEL = logging.WARNING
LOG_LEVEL = getenv("LOG_LEVEL", default="WARNING")
NAMESPACE = UUID('bc6e2cd5-1f59-487f-b05b-49946bd078b2')
CACHE_DIR = getenv("CACHE_DIR", default="/tmp")
BUILD_ENV = getenv("BUILD_ENV", default="development")
JITTER_SECONDS = int(getenv("JITTER_SECONDS", default="30"))
APP_ENV = getenv("APP_ENV", default="Dev")
APP_NAME = getenv("APP_NAME", default="trivialscan-monitor-queue")
ORIGIN_HOST = "dev.trivialsec.com" if APP_ENV == "Dev" else "www.trivialsec.com"
DASHBOARD_URL = f"https://{ORIGIN_HOST}"

logger = logging.getLogger(__name__)
if getenv("AWS_EXECUTION_ENV") is not None:
    boto3.set_stream_logger('boto3', getattr(logging, LOG_LEVEL, DEFAULT_LOG_LEVEL))
logger.setLevel(getattr(logging, LOG_LEVEL, DEFAULT_LOG_LEVEL))


def always_log(message: Union[str, Exception]):
    caller = getframeinfo(stack()[1][0])
    alert_type = (
        message.__class__.__name__
        if hasattr(message, '__class__') and message is not str
        else "UnhandledError"
    )
    filename = caller.filename.replace(getenv("LAMBDA_TASK_ROOT", ""), "") if getenv("AWS_EXECUTION_ENV") is not None and getenv("LAMBDA_TASK_ROOT") else caller.filename.split('/src/')[1]
    lumigo_error(f"{filename}:{caller.function}:{caller.lineno} - {message}", alert_type, extra={
        'LOG_LEVEL': LOG_LEVEL,
        'NAMESPACE': NAMESPACE.hex,
    })


class DelayRetryHandler(Exception):
    """
    Delay the retry handler and provide a useful message when retries are exceeded
    """
    def __init__(self, **kwargs):
        sleep(kwargs.get("delay", 3) or 3)
        Exception.__init__(self, kwargs.get("msg", "Max retries exceeded"))


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, datetime):
            return o.replace(microsecond=0).isoformat()
        if isinstance(o, int) and o > 10^38-1:
            return str(o)
        if isinstance(
            o,
            (
                PositiveInt,
                PositiveFloat,
            ),
        ):
            return int(o)
        if isinstance(
            o,
            (
                HttpUrl,
                AnyHttpUrl,
                IPv4Address,
                IPv6Address,
                IPv4Network,
                IPv6Network,
                UUID,
            ),
        ):
            return str(o)
        if hasattr(o, "dict"):
            return json.dumps(o.dict(), cls=JSONEncoder)

        return super().default(o)


def _request_task(url: str, body: dict, headers: dict):
    with contextlib.suppress(requests.exceptions.ConnectionError):
        requests.post(url, data=json.dumps(body, cls=JSONEncoder), headers=headers, timeout=(15, 30))


def post_beacon(url: HttpUrl, body: dict, headers: dict = None):
    """
    A beacon is a fire and forget HTTP POST, the response is not
    needed so we do not even wait for one, so there is no
    response to discard because it was never received
    """
    if headers is None:
        headers = {"Content-Type": "application/json"}
    threading.Thread(target=_request_task, args=(url, body, headers)).start()


def trace_tag(data: dict[str, str]):
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in data.items()
    ):
        raise ValueError(data)
    for key, value in data.items():
        if 1 > len(key) > 50:
            logger.warning(f"Trace key must be less than 50 for: {key} See: https://docs.lumigo.io/docs/execution-tags#execution-tags-naming-limits-and-requirements")
        if 1 > len(value) > 70:
            logger.warning(f"Trace value must be less than 70 for: {value} See: https://docs.lumigo.io/docs/execution-tags#execution-tags-naming-limits-and-requirements")
    if getenv("AWS_EXECUTION_ENV") is None or APP_ENV != "Prod":
        return
    for key, value in data.items():
        add_execution_tag(key[:50], value=value[:70])
