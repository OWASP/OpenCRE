variable "project_id" {
  type        = string
  description = "GCP project id to create or manage (e.g. opencre-llm-prod). Must be globally unique."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be 6-30 chars, lowercase, start with a letter."
  }
}

variable "billing_account" {
  type        = string
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX). From GitHub secret GCP_BILLING_ACCOUNT_ID."
  sensitive   = true
}

variable "region" {
  type        = string
  description = "Default region (Vertex / API location)."
  default     = "us-central1"
}

variable "org_id" {
  type        = string
  description = "Optional Cloud Organization id. Leave empty for a personal billing account."
  default     = ""
}

variable "folder_id" {
  type        = string
  description = "Optional folder id (folders/123). Mutually exclusive with org_id at the API if both set; leave empty when unused."
  default     = ""
}

variable "github_repository" {
  type        = string
  description = "GitHub repo allowed to federate (owner/name)."
  default     = "OWASP/OpenCRE"
}

variable "github_environment" {
  type        = string
  description = "GitHub Environment name required on the OIDC token."
  default     = "gcp-iac"
}

variable "budget_usd" {
  type        = number
  description = "Monthly cap for a billing budget alert (USD, integer dollars)."
  default     = 50

  validation {
    condition     = var.budget_usd >= 1 && var.budget_usd <= 5000
    error_message = "budget_usd must be between 1 and 5000."
  }
}

variable "manage_budget" {
  type        = bool
  description = "Create a billing budget. Requires the apply identity to have billing budget permissions on the billing account."
  default     = true
}

variable "create_project" {
  type        = bool
  description = "Create the GCP project. Set false if the project already exists and Terraform should only manage in-project resources."
  default     = true
}
