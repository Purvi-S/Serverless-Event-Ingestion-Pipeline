variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "event-pipeline"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "ttl_days" {
  description = "Days before an event expires from DynamoDB."
  type        = number
  default     = 90
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "throttle_rate" {
  description = "Steady-state requests per second allowed on the API."
  type        = number
  default     = 100
}

variable "throttle_burst" {
  type    = number
  default = 200
}

variable "alert_email" {
  description = "Email for CloudWatch alarm notifications (blank to skip)."
  type        = string
  default     = ""
}
