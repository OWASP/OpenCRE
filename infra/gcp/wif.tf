resource "google_service_account" "terraform" {
  project      = data.google_project.opencre.project_id
  account_id   = "opencre-terraform"
  display_name = "OpenCRE Terraform (GitHub Actions WIF)"
  description  = "Least-privilege SA for infra/gcp applies via GitHub OIDC. Not project Owner."

  depends_on = [time_sleep.api_propagation]
}

# Predefined roles instead of a custom role: custom permission strings fail
# closed if GCP renames them. None of these is roles/owner.
resource "google_project_iam_member" "terraform_roles" {
  for_each = toset([
    "roles/apikeys.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/browser",
  ])

  project = data.google_project.opencre.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_storage_bucket_iam_member" "tfstate_admin" {
  bucket = google_storage_bucket.tfstate.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  provider                  = google-beta
  project                   = data.google_project.opencre.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "OIDC from OWASP/OpenCRE workflow GCP IaC only."
  disabled                  = false

  depends_on = [time_sleep.api_propagation]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  provider                           = google-beta
  project                            = data.google_project.opencre.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-opencre"
  display_name                       = "GitHub OpenCRE"
  description                        = "OIDC restricted to main + environment gcp-iac + workflow GCP IaC."
  disabled                           = false

  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.actor"       = "assertion.actor"
    "attribute.repository"  = "assertion.repository"
    "attribute.ref"         = "assertion.ref"
    "attribute.environment" = "assertion.environment"
    "attribute.workflow"    = "assertion.workflow"
  }

  attribute_condition = join(" && ", [
    "assertion.repository == '${var.github_repository}'",
    "assertion.ref == 'refs/heads/main'",
    "assertion.environment == '${var.github_environment}'",
    "assertion.workflow == 'GCP IaC'",
  ])

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "wif_user" {
  service_account_id = google_service_account.terraform.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
