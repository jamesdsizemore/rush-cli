resource "aws_iam_policy" "read_only" {
  name        = "ReadOnlyS3"
  description = "Read only access to s3 bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:s3:::example-bucket/*"
      }
    ]
  })
}
