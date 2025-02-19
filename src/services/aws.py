import json
from os import getenv
from enum import Enum
from hashlib import sha256
from typing import Any, Union

import boto3
from retry.api import retry
from botocore.exceptions import (
    CapacityNotAvailableError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    ReadTimeoutError,
)

import internals


STORE_BUCKET = getenv("STORE_BUCKET", default="trivialscan-dashboard-store")
AWS_REGION = getenv("AWS_REGION", default="ap-southeast-2")
if getenv("AWS_EXECUTION_ENV") is None:
    boto3.setup_default_session(
        profile_name=getenv("AWS_PROFILE_NAME"),
        aws_access_key_id=getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=getenv("AWS_SESSION_TOKEN"),
    )

ssm_client = boto3.client(service_name="ssm", region_name=AWS_REGION)
s3_client = boto3.client(service_name="s3", region_name=AWS_REGION)
sqs_client = boto3.client(service_name="sqs", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


class Tables(str, Enum):
    EWS_BINARY_DEFENSE = f'{internals.APP_ENV.lower()}_ews_binarydefense'
    EWS_BRUTE_FORCE_BLOCKER = f'{internals.APP_ENV.lower()}_ews_bruteforceblocker'
    EWS_CH = f'{internals.APP_ENV.lower()}_ews_ch'
    EWS_CRUZIT = f'{internals.APP_ENV.lower()}_ews_cruzit'
    EWS_DATAPLANE = f'{internals.APP_ENV.lower()}_ews_dataplane'
    EWS_DARKLIST = f'{internals.APP_ENV.lower()}_ews_darklist'
    EWS_PROOFPOINT = f'{internals.APP_ENV.lower()}_ews_proofpoint'
    EWS_TALOS = f'{internals.APP_ENV.lower()}_ews_talos'
    LOGIN_SESSIONS = f'{internals.APP_ENV.lower()}_login_sessions'
    REPORT_HISTORY = f'{internals.APP_ENV.lower()}_report_history'
    OBSERVED_IDENTIFIERS = f'{internals.APP_ENV.lower()}_observed_identifiers'
    EARLY_WARNING_SERVICE = f'{internals.APP_ENV.lower()}_early_warning_service'


class StorageClass(str, Enum):
    STANDARD = "STANDARD"
    REDUCED_REDUNDANCY = "REDUCED_REDUNDANCY"
    STANDARD_IA = "STANDARD_IA"
    ONEZONE_IA = "ONEZONE_IA"
    INTELLIGENT_TIERING = "INTELLIGENT_TIERING"
    GLACIER = "GLACIER"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"
    OUTPOSTS = "OUTPOSTS"
    GLACIER_IR = "GLACIER_IR"


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def object_exists(file_path: str, bucket_name: str = STORE_BUCKET, **kwargs):
    internals.logger.info(f"object_exists {file_path} from bucket {bucket_name}")
    try:
        content = s3_client.head_object(Bucket=bucket_name, Key=file_path, **kwargs)
        return content.get("ResponseMetadata", None) is not None
    except ClientError as err:
        internals.logger.info(err, exc_info=True)
        internals.always_log(err)
    return False


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def get_ssm(parameter: str, default: Any = None, **kwargs) -> Any:
    internals.logger.info(f"get_ssm parameter {parameter}")
    try:
        response = ssm_client.get_parameter(Name=parameter, **kwargs)
        return (
            response.get("Parameter", {}).get("Value", default)
            if isinstance(response, dict)
            else default
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ParameterNotFound":  # type: ignore
            internals.logger.warning(f"The requested secret {parameter} was not found")
        elif err.response["Error"]["Code"] == "InvalidRequestException":  # type: ignore
            internals.logger.warning(f"The request was invalid due to: {err}")
        elif err.response["Error"]["Code"] == "InvalidParameterException":  # type: ignore
            internals.logger.warning(f"The request had invalid params: {err}")
        else:
            internals.always_log(err)
    return default


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
        internals.DelayRetryHandler,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def store_ssm(parameter: str, value: str, **kwargs) -> bool:
    internals.logger.info(f"store_ssm parameter {parameter}")
    try:
        response = ssm_client.put_parameter(Name=parameter, Value=value, **kwargs)
        return (
            response.get("Version") is not None if isinstance(response, dict) else False
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ParameterAlreadyExists":  # type: ignore
            internals.logger.warning(f"The secret {parameter} already exists")
        elif err.response["Error"]["Code"] == "InternalServerError":  # type: ignore
            internals.logger.warning(f"The request was invalid due to: {err}")
        elif err.response["Error"]["Code"] == "TooManyUpdates":  # type: ignore
            internals.logger.warning(err, exc_info=True)
            raise internals.DelayRetryHandler(
                msg="Please throttle your requests to continue using this service"
            ) from err
        elif err.response["Error"]["Code"] == "ParameterLimitExceeded":  # type: ignore
            internals.logger.warning(err, exc_info=True)
            raise internals.DelayRetryHandler(
                msh="Platform is exhausted and unable to respond, please try again soon"
            ) from err
        else:
            internals.always_log(err)
    return False


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def list_s3(prefix_key: str, bucket_name: str = STORE_BUCKET) -> list[str]:
    """
    params:
    - bucket_name: s3 bucket with target contents
    - prefix_key: pattern to match in s3
    """
    internals.logger.info(f"list_s3 key prefix {prefix_key}")
    keys = []
    next_token = ""
    base_kwargs = {
        "Bucket": bucket_name,
        "Prefix": prefix_key,
    }
    base_kwargs.update()
    while next_token is not None:
        args = base_kwargs.copy()
        if next_token != "":
            args["ContinuationToken"] = next_token
        try:
            results = s3_client.list_objects_v2(**args)

        except ClientError as err:
            if err.response["Error"]["Code"] == "NoSuchBucket":  # type: ignore
                internals.always_log(
                    f"The requested bucket {bucket_name} was not found"
                )
            elif err.response["Error"]["Code"] == "InvalidObjectState":  # type: ignore
                internals.always_log(f"The request was invalid due to: {err}")
            elif err.response["Error"]["Code"] == "InvalidParameterException":  # type: ignore
                internals.always_log(f"The request had invalid params: {err}")
            else:
                internals.always_log(err)
            return []
        for item in results.get("Contents", []):
            k = item["Key"]  # type: ignore
            if k[-1] != "/":
                keys.append(k)
        next_token = results.get("NextContinuationToken")

    return keys


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def list_s3_objects(prefix_key: str, bucket_name: str = STORE_BUCKET) -> list[str]:
    """
    params:
    - bucket_name: s3 bucket with target contents
    - prefix_key: pattern to match in s3
    """
    internals.logger.info(f"list_s3_objects key prefix {prefix_key}")
    items = []
    next_token = ""
    base_kwargs = {
        "Bucket": bucket_name,
        "Prefix": prefix_key,
    }
    base_kwargs.update()
    while next_token is not None:
        args = base_kwargs.copy()
        if next_token != "":
            args["ContinuationToken"] = next_token
        try:
            results = s3_client.list_objects_v2(**args)

        except ClientError as err:
            if err.response["Error"]["Code"] == "NoSuchBucket":  # type: ignore
                internals.always_log(
                    f"The requested bucket {bucket_name} was not found"
                )
            elif err.response["Error"]["Code"] == "InvalidObjectState":  # type: ignore
                internals.always_log(f"The request was invalid due to: {err}")
            elif err.response["Error"]["Code"] == "InvalidParameterException":  # type: ignore
                internals.always_log(f"The request had invalid params: {err}")
            else:
                internals.always_log(err)
            return []
        for item in results.get("Contents", []):
            k = item["Key"]  # type: ignore
            if k[-1] != "/":
                items.append(item)
        next_token = results.get("NextContinuationToken")

    return items


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def get_s3(path_key: str, bucket_name: str = STORE_BUCKET, default: Any = None) -> Any:
    internals.logger.info(f"get_s3 object key {path_key}")
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=path_key)
        return response["Body"].read().decode("utf8")

    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchKey":  # type: ignore
            internals.logger.warning(
                f"The requested bucket {bucket_name} object key {path_key} was not found"
            )
        elif err.response["Error"]["Code"] == "InvalidObjectState":  # type: ignore
            internals.logger.warning(f"The request was invalid due to: {err}")
        elif err.response["Error"]["Code"] == "InvalidParameterException":  # type: ignore
            internals.logger.warning(f"The request had invalid params: {err}")
        else:
            internals.always_log(err)
    return default


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def delete_s3(path_key: str, bucket_name: str = STORE_BUCKET, **kwargs) -> bool:
    internals.logger.info(f"delete_s3 object key {path_key}")
    try:
        response = s3_client.delete_object(Bucket=bucket_name, Key=path_key, **kwargs)
        return response.get("DeleteMarker") if isinstance(response, dict) else False

    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchKey":  # type: ignore
            internals.logger.warning(
                f"The requested bucket {bucket_name} object key {path_key} was not found"
            )
        elif err.response["Error"]["Code"] == "InvalidObjectState":  # type: ignore
            internals.logger.warning(f"The request was invalid due to: {err}")
        elif err.response["Error"]["Code"] == "InvalidParameterException":  # type: ignore
            internals.logger.warning(f"The request had invalid params: {err}")
        else:
            internals.always_log(err)
    return False


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
        internals.DelayRetryHandler,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def store_s3(
    path_key: str,
    value: Union[str, bytes],
    bucket_name: str = STORE_BUCKET,
    storage_class: StorageClass = StorageClass.STANDARD_IA,
    **kwargs,
) -> bool:
    internals.logger.info(f"store_s3 {path_key}")
    internals.logger.debug(f"store_s3 {value}")
    try:
        response = s3_client.put_object(
            Bucket=bucket_name,
            Key=path_key,
            Body=value,
            StorageClass=str(storage_class.name),  # type: ignore
            **kwargs,
        )
        return response.get("ETag") is not None if isinstance(response, dict) else False
    except ClientError as err:
        if err.response["Error"]["Code"] == "ParameterAlreadyExists":  # type: ignore
            internals.logger.warning(
                f"The object bucket {bucket_name} key {path_key} already exists"
            )
        elif err.response["Error"]["Code"] == "InternalServerError":  # type: ignore
            internals.logger.warning(f"The request was invalid due to: {err}")
        elif err.response["Error"]["Code"] == "TooManyUpdates":  # type: ignore
            internals.logger.warning(err, exc_info=True)
            raise internals.DelayRetryHandler(
                msg="Please throttle your requests to continue using this service"
            ) from err
        elif err.response["Error"]["Code"] == "ParameterLimitExceeded":  # type: ignore
            internals.logger.warning(err, exc_info=True)
            raise internals.DelayRetryHandler(
                msg="Platform is exhausted and unable to respond, please try again soon"
            ) from err
        else:
            internals.always_log(err)
    return False


def _message_attributes(data: dict):
    attributes = {}
    _defaults = {"DataType": "String", "StringValue": ""}
    for key, item in data.items():
        if item is None:
            continue
        attributes[key] = _defaults.copy()
        if isinstance(item, (bool, int)):
            attributes[key]["DataType"] = "Number"
        if isinstance(item, bool):
            attributes[key]["StringValue"] = "1" if item else "0"
        elif isinstance(item, int):
            attributes[key]["StringValue"] = str(item)
        elif isinstance(item, str):
            attributes[key]["StringValue"] = item
        elif isinstance(item, list):
            attributes[key]["StringValue"] = ",".join(
                [str(_item) for _item in item if _item is not None]
            )
        elif isinstance(item, dict):
            attributes[key]["StringValue"] = json.dumps(item, default=str)

    return attributes


@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def store_sqs(
    queue_name: str,
    message_body: str,
    deduplicate: bool = False,
    deduplication_id: Union[str, None] = None,
    message_group_id: Union[str, None] = None,
    **kwargs,
) -> bool:
    internals.logger.info(f"store_sqs {queue_name}")
    internals.logger.debug(f"message {message_body}")
    if queue_name.endswith(".fifo"):
        if deduplicate and not deduplication_id:
            deduplication_id = sha256(message_body.encode()).hexdigest()
        if not message_group_id:
            message_group_id = deduplication_id
    try:
        queue = sqs_client.get_queue_url(QueueName=queue_name)
        if not queue.get("QueueUrl"):
            internals.always_log(f"no queue with name {queue_name}")
            return False

        params: dict[str, Any] = {
            "QueueUrl": queue.get("QueueUrl"),
            "MessageBody": message_body,
        }
        if kwargs:
            params["MessageAttributes"] = _message_attributes({**kwargs})
        if deduplicate:
            params["MessageDeduplicationId"] = deduplication_id
        if message_group_id:
            params["MessageGroupId"] = message_group_id

        response = sqs_client.send_message(**params)
        return (
            response.get("MessageId") is not None
            if isinstance(response, dict)
            else False
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "InvalidMessageContents":  # type: ignore
            internals.always_log(f"InvalidMessageContents: {message_body}")
        elif err.response["Error"]["Code"] == "UnsupportedOperation":  # type: ignore
            internals.always_log(f"UnsupportedOperation: {err}")
        else:
            internals.always_log(err)
    return False

@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def complete_sqs(
    queue_name: str,
    receipt_handle: str
) -> bool:
    internals.logger.info(f"deleting {receipt_handle} {queue_name}")
    try:
        queue = sqs_client.get_queue_url(QueueName=queue_name)
        if not queue.get("QueueUrl"):
            internals.always_log(f"no queue with name {queue_name}")
            return False

        params: dict[str, Any] = {
            "QueueUrl": queue.get("QueueUrl"),
            "ReceiptHandle": receipt_handle,
        }
        return sqs_client.delete_message(**params) is None
    except ClientError as err:
        if err.response["Error"]["Code"] == "InvalidIdFormat":  # type: ignore
            internals.always_log(f"InvalidIdFormat: {err}")
        elif err.response["Error"]["Code"] == "ReceiptHandleIsInvalid":  # type: ignore
            internals.always_log(f"ReceiptHandleIsInvalid: {err}")
        else:
            internals.always_log(err)
    return False

@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def get_dynamodb(item_key: dict, table_name: Tables, default: Any = None, **kwargs) -> Union[dict, None]:
    internals.logger.info(f"get_dynamodb table: {table_name.value}")
    internals.logger.debug(f"item_key: {item_key}")
    try:
        table = dynamodb.Table(table_name.value)
        response = table.get_item(Key=item_key, **kwargs)
        internals.logger.debug(response)
        return response.get("Item", default)

    except Exception as err:
        internals.always_log(err)
    return default

@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def put_dynamodb(item: dict, table_name: Tables, **kwargs) -> bool:
    internals.logger.info(f"put_dynamodb table: {table_name.value}")
    internals.logger.debug(f"item: {item}")
    try:
        raw = json.dumps(item, cls=internals.JSONEncoder)
        data = json.loads(raw, parse_float=str, parse_int=str)
    except json.JSONDecodeError as err:
        internals.logger.info(err, exc_info=True)
        internals.always_log(err.msg)
        return False
    try:
        table = dynamodb.Table(table_name.value)
        response = table.put_item(Item=data, **kwargs)
        return response.get("ResponseMetadata", {}).get("RequestId") is not None

    except Exception as err:
        internals.logger.warning(err, exc_info=True)
        internals.logger.info(f"data: {data}")
    return False

@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def delete_dynamodb(item_key: dict, table_name: Tables, **kwargs) -> bool:
    internals.logger.info(f"delete_dynamodb table: {table_name.value}")
    internals.logger.debug(f"item_key: {item_key}")
    try:
        table = dynamodb.Table(table_name.value)
        response = table.delete_item(Key=item_key, **kwargs)
        internals.logger.debug(response)
        return response.get("ResponseMetadata", {}).get("RequestId") is not None

    except Exception as err:
        internals.always_log(err)
    return False

@retry(
    (
        ConnectionClosedError,
        ReadTimeoutError,
        ConnectTimeoutError,
        CapacityNotAvailableError,
    ),
    tries=3,
    delay=1.5,
    backoff=1,
)
def query_dynamodb(table_name: Tables, **kwargs) -> list[dict]:
    internals.logger.info(f"query_dynamodb table: {table_name.value}")
    internals.logger.debug(f"arguments: {kwargs}")
    try:
        table = dynamodb.Table(table_name.value)
        response = table.query(**kwargs)
        internals.logger.debug(response)
        return response.get("Items", [])

    except Exception as err:
        internals.always_log(err)
    return []
