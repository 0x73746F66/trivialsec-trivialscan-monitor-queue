resource "aws_sqs_queue" "trivialscan_reconnaissance_dlq" {
  name                          = "${lower(var.app_env)}-reconnaissance-dlq.fifo"
  fifo_queue                    = true
  content_based_deduplication   = true
  tags                          = local.tags
}

resource "aws_sqs_queue" "trivialscan_reconnaissance_queue" {
  name                          = "${lower(var.app_env)}-reconnaissance.fifo"
  visibility_timeout_seconds    = 3
  message_retention_seconds     = 86400
  redrive_policy                = "{\"deadLetterTargetArn\":\"${aws_sqs_queue.trivialscan_reconnaissance_dlq.arn}\",\"maxReceiveCount\":2}"
  fifo_queue                    = true
  content_based_deduplication   = true
  tags                          = local.tags
}
