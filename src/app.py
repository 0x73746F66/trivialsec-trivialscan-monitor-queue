import json

import internals
import models
import services.aws
import services.webhook


def handler(event, context):
    queue_name = f"{internals.APP_ENV.lower()}-reconnaissance"
    for object_key in services.aws.list_s3(
        prefix_key=f"{internals.APP_ENV}/accounts/"
    ):
        if not object_key.endswith("scanner-record.json"):
            continue
        _, _, account_name, *_ = object_key.split("/")
        internals.logger.info(f"account_name {account_name}")
        account = models.MemberAccount(name=account_name).load()
        scanner_record = models.ScannerRecord(account=account).load()  # type: ignore
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
                    'ports': monitor_target.ports,
                    'path_names': monitor_target.path_names,
                    'type': models.ScanRecordType.MONITORING,
                }, default=str),
                deduplicate=False,
                account=account_name,
                queued_timestamp=monitor_target.timestamp,
            )
            services.webhook.send(
                event_name=models.WebhookEvent.HOSTED_MONITORING,
                account=account,
                data={
                    'hostname': monitor_target.hostname,
                    'ports': monitor_target.ports,
                    'path_names': monitor_target.path_names,
                    'type': models.ScanRecordType.MONITORING,
                    'status': "queued",
                    'account': account_name,
                    'queued_timestamp': monitor_target.timestamp,
                }
            )
