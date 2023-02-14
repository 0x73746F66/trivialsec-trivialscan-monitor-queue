locals {
    aws_master_account_id = 984310022655
    aws_default_region    = "ap-southeast-2"
    python_version        = "python3.9"
    source_file           = "${lower(var.app_env)}-${var.app_name}.zip"
    function_name         = "${lower(var.app_env)}-trivialscan-monitor-queue"
    tags                  = {
        ProjectName = "trivialscan"
        ProjectLeadEmail = "chris@trivialsec.com"
        CostCenter = var.app_env != "Prod" ? "randd" : "opex"
        SecurityTags = "customer-data"
        AutomationTool = "Terraform"
    }
    timeout               = 60
    memory_size           = 128
    retention_in_days     = var.app_env == "Prod" ? 30 : 7
}
