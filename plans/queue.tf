resource "aws_sqs_queue" "trivialscan_reconnaissance_dlq" {
  name = "${lower(var.app_env)}-reconnaissance-dlq"
  tags = local.tags
}

resource "aws_sqs_queue" "trivialscan_reconnaissance_queue" {
  name                       = "${lower(var.app_env)}-reconnaissance"
  visibility_timeout_seconds = 150
  message_retention_seconds  = 86400
  redrive_policy             = "{\"deadLetterTargetArn\":\"${aws_sqs_queue.trivialscan_reconnaissance_dlq.arn}\",\"maxReceiveCount\":2}"
  tags                       = local.tags
}
