locals {
  apis = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "apikeys.googleapis.com",
    "generativelanguage.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
  ])

  github_owner = split("/", var.github_repository)[0]
  github_repo  = split("/", var.github_repository)[1]
}

resource "google_project" "opencre" {
  count = var.create_project ? 1 : 0

  name            = var.project_id
  project_id      = var.project_id
  billing_account = var.billing_account
  org_id          = var.org_id != "" ? var.org_id : null
  folder_id       = var.folder_id != "" ? var.folder_id : null
  deletion_policy = "PREVENT"

  labels = {
    app        = "opencre"
    managed-by = "terraform"
    purpose    = "llm-continuity"
  }

  lifecycle {
    prevent_destroy = true
  }
}

data "google_project" "opencre" {
  project_id = var.project_id
  depends_on = [google_project.opencre]
}

resource "google_project_service" "apis" {
  for_each = local.apis

  project            = data.google_project.opencre.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "time_sleep" "api_propagation" {
  create_duration = "60s"
  depends_on      = [google_project_service.apis]
}

resource "google_storage_bucket" "tfstate" {
  name                        = "opencre-tfstate-${data.google_project.opencre.project_id}"
  project                     = data.google_project.opencre.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 20
      with_state         = "ARCHIVED"
    }
  }

  labels = {
    app        = "opencre"
    managed-by = "terraform"
    purpose    = "tfstate"
  }

  depends_on = [time_sleep.api_propagation]

  lifecycle {
    prevent_destroy = true
  }
}
