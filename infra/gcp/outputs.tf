output "project_id" {
  value       = data.google_project.opencre.project_id
  description = "GCP project id."
}

output "project_number" {
  value       = data.google_project.opencre.number
  description = "Numeric project number (WIF paths)."
}

output "tfstate_bucket" {
  value       = google_storage_bucket.tfstate.name
  description = "Set GitHub variable TF_STATE_BUCKET to this after the first apply."
}

output "terraform_sa_email" {
  value       = google_service_account.terraform.email
  description = "Set GitHub variable GCP_TF_SA_EMAIL. Used by WIF."
}

output "wif_provider" {
  value       = google_iam_workload_identity_pool_provider.github.name
  description = "Full resource name. Set GitHub variable GCP_WIF_PROVIDER. Not a secret."
}

output "gemini_api_key" {
  value       = google_apikeys_key.gemini.key_string
  description = "Restricted Generative Language API key. Never log. Pushed to Heroku by the workflow."
  sensitive   = true
}

output "heroku_config_nonsecret" {
  value = {
    GOOGLE_PROJECT_ID       = data.google_project.opencre.project_id
    GOOGLE_PROJECT_LOCATION = var.region
    CRE_LLM_CHAT_MODEL      = "gemini/gemini-2.5-flash"
    CRE_EMBED_MODEL         = "gemini/gemini-embedding-001"
  }
  description = "Path A Heroku config the workflow PATCHes alongside GEMINI_API_KEY (LiteLLM gemini/ prefix, not vertex_ai/)."
}
