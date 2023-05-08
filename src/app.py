import json

from lumigo_tracer import lumigo_tracer

import internals
import models
import services.aws
import services.webhook


def main(event):
    if event.get("source"):
        internals.trace_tag({
            "source": event["source"],
            "resources": ",".join([
                e.split(":")[-1] for e in event["resources"]
            ]),
        })
    queue_name = f"{internals.APP_ENV.lower()}-reconnaissance"
    for object_key in services.aws.list_s3(
        prefix_key=f"{internals.APP_ENV}/accounts/"
    ):
        if not object_key.endswith("scanner-record.json"):
            continue
        _, _, account_name, *_ = object_key.split("/")
        internals.logger.info(f"account_name {account_name}")
        account = models.MemberAccount(name=account_name)
        if not account.load():
            internals.logger.error(f"Account record bug for {account_name}")
            continue
        scanner_record = models.ScannerRecord(account_name=account.name)  # type: ignore
        if not scanner_record.load() or len(scanner_record.monitored_targets) == 0:
            internals.logger.warning(f"No scanner record for {account_name}")
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
    return True


@lumigo_tracer(
    token=services.aws.get_ssm(f'/{internals.APP_ENV}/{internals.APP_NAME}/Lumigo/token', WithDecryption=True),
    should_report=internals.APP_ENV == "Prod",
    skip_collecting_http_body=True,
    verbose=internals.APP_ENV != "Prod"
)
def handler(event, context):  # pylint: disable=unused-argument
    try:
        return main(event)
    except Exception as err:
        internals.always_log(err)
    return False
