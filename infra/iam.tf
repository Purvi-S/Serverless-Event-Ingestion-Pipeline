data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingest" {
  name               = "${local.name}-ingest-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Least privilege: write-only to one table, and its own logs.
data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "WriteEvents"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.events.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:*"]
  }

  statement {
    sid       = "Tracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "${local.name}-ingest-policy"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}
