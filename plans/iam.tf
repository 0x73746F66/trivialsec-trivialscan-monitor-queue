data "aws_iam_policy_document" "trivialscan_monitor_queue_assume_role_policy" {
  statement {
    sid = "${var.app_env}TrivialScannerMonitorQueueAssumeRole"
    actions    = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}
data "aws_iam_policy_document" "trivialscan_monitor_queue_iam_policy" {
  statement {
    sid = "${var.app_env}TrivialScannerMonitorQueueLogging"
    actions   = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${local.aws_default_region}:${local.aws_master_account_id}:log-group:/aws/lambda/${local.function_name}:*"
    ]
  }
  statement {
    sid = "${var.app_env}TrivialScannerMonitorQueueSQS"
    actions   = [
      "sqs:SendMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:Get*",
    ]
    resources = [
      aws_sqs_queue.trivialscan_reconnaissance_queue.arn
    ]
  }
  statement {
    sid = "${var.app_env}TrivialScannerMonitorQueueSecrets"
    actions   = [
      "ssm:GetParameter",
    ]
    resources = [
      "arn:aws:ssm:${local.aws_default_region}:${local.aws_master_account_id}:parameter/${var.app_env}/${var.app_name}/*",
    ]
  }
  statement {
    sid = "${var.app_env}TrivialScannerMonitorQueueObjList"
    actions   = [
      "s3:Head*",
      "s3:List*",
    ]
    resources = [
      "arn:aws:s3:::${data.terraform_remote_state.trivialscan_s3.outputs.trivialscan_store_bucket}",
      "arn:aws:s3:::${data.terraform_remote_state.trivialscan_s3.outputs.trivialscan_store_bucket}/*",
    ]
  }
  statement {
    sid = "${var.app_env}TrivialScannerMonitorQueueObjAccess"
    actions   = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      "arn:aws:s3:::${data.terraform_remote_state.trivialscan_s3.outputs.trivialscan_store_bucket}/${var.app_env}/*",
    ]
  }
}
resource "aws_iam_role" "trivialscan_monitor_queue_role" {
  name               = "${lower(var.app_env)}_trivialscan_monitor_queue_lambda_role"
  assume_role_policy = data.aws_iam_policy_document.trivialscan_monitor_queue_assume_role_policy.json
  lifecycle {
    create_before_destroy = true
  }
}
resource "aws_iam_policy" "trivialscan_monitor_queue_policy" {
  name        = "${lower(var.app_env)}_trivialscan_monitor_queue_lambda_policy"
  path        = "/"
  policy      = data.aws_iam_policy_document.trivialscan_monitor_queue_iam_policy.json
}
resource "aws_iam_role_policy_attachment" "policy_attach" {
  role       = aws_iam_role.trivialscan_monitor_queue_role.name
  policy_arn = aws_iam_policy.trivialscan_monitor_queue_policy.arn
}
