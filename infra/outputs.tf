output "api_endpoint" {
  value = "${aws_apigatewayv2_api.events.api_endpoint}/events"
}

output "table_name" {
  value = aws_dynamodb_table.events.name
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
