resource "aws_iam_policy" "admin_wildcard" {
  name        = "WildcardAdmin"
  description = "Dangerous wildcard policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "*"
        Effect   = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "iam:PassRole",
          "iam:CreatePolicyVersion",
          "iam:SetDefaultPolicyVersion"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}
