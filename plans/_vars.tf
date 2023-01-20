variable "aws_access_key_id" {
  description = "AWS_ACCESS_KEY_ID"
  type        = string
}
variable "log_level" {
  description = "LOG_LEVEL"
  type        = string
  default     = "WARNING"
}
variable "app_env" {
  description = "default Dev"
  type        = string
  default     = "Dev"
}
variable "app_name" {
  description = "default trivialscan-monitor-queue"
  type        = string
  default     = "trivialscan-monitor-queue"
}
variable "build_env" {
  description = "BUILD_ENV"
  type        = string
  default     = "development"
}
variable "schedule" {
  description = "cron schedule"
  type        = string
  # default     = "rate(15 minutes)"
  default     = "cron(59 14 * * ? *)" # 2:59 PM UTC daily (23:59 Sydney local time)
}
