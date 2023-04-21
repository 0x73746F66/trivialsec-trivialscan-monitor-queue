output "trivialscan_monitor_queue_arn" {
  value = aws_lambda_function.trivialscan_monitor_queue.arn
}
output "trivialscan_monitor_queue_role" {
  value = aws_iam_role.trivialscan_monitor_queue_role.name
}
output "trivialscan_monitor_queue_role_arn" {
  value = aws_iam_role.trivialscan_monitor_queue_role.arn
}
output "trivialscan_monitor_queue_policy_arn" {
  value = aws_iam_policy.trivialscan_monitor_queue_policy.arn
}
output "reconnaissance_dlq_arn" {
  value = aws_sqs_queue.trivialscan_reconnaissance_dlq.arn
}
output "reconnaissance_queue_arn" {
  value = aws_sqs_queue.trivialscan_reconnaissance_queue.arn
}
output "reconnaissance_queue_name" {
  value = aws_sqs_queue.trivialscan_reconnaissance_queue.name
}
