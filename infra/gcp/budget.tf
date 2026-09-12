resource "google_billing_budget" "monthly" {
  count = var.manage_budget ? 1 : 0

  billing_account = var.billing_account
  display_name    = "opencre-${data.google_project.opencre.project_id}"

  budget_filter {
    projects = ["projects/${data.google_project.opencre.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  depends_on = [time_sleep.api_propagation]
}
