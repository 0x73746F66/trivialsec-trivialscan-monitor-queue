import json

import internals
import models
import services.aws


def handler(event, context):
    queue_name = f"{internals.APP_ENV.lower()}-reconnaissance.fifo"
    for object_key in services.aws.list_s3(
        prefix_key=f"{internals.APP_ENV}/accounts/"
    ):
        if not object_key.endswith("scanner-record.json"):
            continue
        _, _, account_name, *_ = object_key.split("/")
        internals.logger.info(f"account_name {account_name}")
        scanner_record = models.ScannerRecord(account=models.MemberAccount(name=account_name).load()).load()  # type: ignore
        if not scanner_record or len(scanner_record.monitored_targets) == 0:
            continue
        for monitor_target in scanner_record.monitored_targets:
            if monitor_target.enabled is not True:
                continue
            internals.logger.info(f"monitor_target {monitor_target}")
            services.aws.store_sqs(
                queue_name=queue_name,
                message_body=json.dumps({
                    'hostname': monitor_target.hostname,
                    'port': 443,
                    'type': models.ScanRecordType.MONITORING,
                }, default=str),
                deduplicate=True,
                http_paths=["/"],
                account=account_name,  # type: ignore
                queued_timestamp=monitor_target.timestamp,  # JavaScript support
            )
