terraform {
  required_version = ">= 1.8.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.47"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.47"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }

  # Partial backend: bucket/prefix come from `terraform init -backend-config`
  # in GitHub Actions (never commit a bucket name that does not exist yet).
  backend "gcs" {}
}

provider "google" {
  region = var.region
}

provider "google-beta" {
  region = var.region
}
