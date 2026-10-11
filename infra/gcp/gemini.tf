resource "google_apikeys_key" "gemini" {
  provider     = google-beta
  project      = data.google_project.opencre.project_id
  name         = "opencre-gemini"
  display_name = "OpenCRE Gemini Path A (LiteLLM gemini/ prefix, Generative Language API)"

  restrictions {
    api_targets {
      service = "generativelanguage.googleapis.com"
    }
  }

  depends_on = [time_sleep.api_propagation]

  lifecycle {
    prevent_destroy = true
  }
}
