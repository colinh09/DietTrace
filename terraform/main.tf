terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Cloud Run / Artifact Registry region"
  type        = string
  default     = "us-central1"
}

variable "gemini_location" {
  description = "Gemini API location (Gemini 3 preview is served from 'global')"
  type        = string
  default     = "global"
}

variable "gemini_model" {
  description = "Gemini model identifier (must be a Gemini 3 model)"
  type        = string
  default     = "gemini-3.1-pro-preview"
}

variable "phoenix_api_key" {
  description = "Arize Phoenix API key"
  type        = string
  sensitive   = true
}

variable "phoenix_collector_endpoint" {
  description = "Phoenix OTEL collector endpoint"
  type        = string
}

variable "phoenix_base_url" {
  description = "Phoenix base URL for the REST API / MCP server"
  type        = string
}

provider "google" {
  project = var.project
  region  = var.region
}

resource "google_artifact_registry_repository" "dietrace" {
  location      = var.region
  repository_id = "dietrace"
  format        = "DOCKER"
  description   = "DietTrace container images"
}

resource "google_cloud_run_v2_service" "dietrace_web" {
  name     = "dietrace-web"
  location = var.region

  template {
    # Scale to zero between demos to conserve the limited GCP credit budget.
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project}/dietrace/dietrace-web:latest"

      ports {
        container_port = 8080
      }

      env {
        name  = "DIETRACE_GEMINI_PROJECT"
        value = var.project
      }
      env {
        name  = "DIETRACE_GEMINI_LOCATION"
        value = var.gemini_location
      }
      env {
        name  = "DIETRACE_GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "PHOENIX_API_KEY"
        value = var.phoenix_api_key
      }
      env {
        name  = "PHOENIX_COLLECTOR_ENDPOINT"
        value = var.phoenix_collector_endpoint
      }
      env {
        name  = "PHOENIX_BASE_URL"
        value = var.phoenix_base_url
      }
    }
  }
}

output "service_url" {
  description = "Public URL of the deployed Cloud Run service"
  value       = google_cloud_run_v2_service.dietrace_web.uri
}
