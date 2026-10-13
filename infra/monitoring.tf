resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name}-ingest-errors"
  alarm_description   = "Ingest Lambda is throwing errors (DynamoDB writes failing)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.ingest.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_p99_latency" {
  alarm_name          = "${local.name}-ingest-p99-latency"
  alarm_description   = "Ingest p99 duration above 2s."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = aws_lambda_function.ingest.function_name }
  extended_statistic  = "p99"
  period              = 300
  evaluation_periods  = 2
  threshold           = 2000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-5xx"
  alarm_description   = "API Gateway returning 5xx."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.events.id }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "rejection_rate" {
  alarm_name          = "${local.name}-rejection-rate"
  alarm_description   = "More than 10% of events failing validation (likely a bad client release)."
  evaluation_periods  = 3
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  metric_query {
    id          = "rate"
    expression  = "100 * rejected / (accepted + rejected + 1)"
    label       = "Rejection %"
    return_data = true
  }
  metric_query {
    id = "accepted"
    metric {
      namespace   = "EventPipeline"
      metric_name = "EventsAccepted"
      dimensions  = { Service = "ingest" }
      period      = 300
      stat        = "Sum"
    }
  }
  metric_query {
    id = "rejected"
    metric {
      namespace   = "EventPipeline"
      metric_name = "EventsRejected"
      dimensions  = { Service = "ingest" }
      period      = 300
      stat        = "Sum"
    }
  }
}

resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "${local.name}-pipeline"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title  = "Events accepted / rejected / duplicate"
          region = var.region
          stat   = "Sum"
          period = 60
          metrics = [
            ["EventPipeline", "EventsAccepted", "Service", "ingest"],
            [".", "EventsRejected", ".", "."],
            [".", "EventsDuplicate", ".", "."],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title  = "Lambda duration p50 / p99"
          region = var.region
          period = 60
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.ingest.function_name, { stat = "p50" }],
            ["...", { stat = "p99" }],
          ]
        }
      },
    ]
  })
}
