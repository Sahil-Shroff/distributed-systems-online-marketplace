variable "project_id" {
  description = "GCP project ID. Replace the default if 69629390218 is only your project number."
  type        = string
  default     = "69629390218"
}

variable "region" {
  description = "GCP region for the PA3 deployment."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Legacy single-zone override. Ignored when `zones` is set."
  type        = string
  default     = "us-central1-a"
}

variable "zones" {
  description = "Zones used for the PA3 deployment. Instances are spread across these zones."
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"]
}

variable "service_machine_type" {
  description = "Machine type used for customer DB, product DB, and frontend replicas."
  type        = string
  default     = "f1-micro"
}

variable "benchmark_machine_type" {
  description = "Machine type used for the benchmark VM."
  type        = string
  default     = "g1-small"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size for each VM."
  type        = number
  default     = 10
}

variable "boot_disk_type" {
  description = "Boot disk type for each VM."
  type        = string
  default     = "pd-standard"
}

variable "admin_source_ranges" {
  description = "CIDR ranges allowed to SSH into the VMs and hit the frontend ports directly."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "network_cidr" {
  description = "Subnet CIDR for the PA3 VPC."
  type        = string
  default     = "10.10.0.0/24"
}

variable "repo_archive_excludes" {
  description = "Paths excluded from the uploaded source archive."
  type        = list(string)
  default = [
    ".git",
    ".git/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".terraform",
    ".terraform/**",
    "__pycache__",
    "**/__pycache__/**",
    "*.pyc",
    "*.pyo",
    ".venv",
    ".venv/**",
    "venv",
    "venv/**",
    "runtime",
    "runtime/**",
    "database",
    "database/**",
    "infra/terraform/.terraform",
    "infra/terraform/.terraform/**",
    "infra/terraform/*.tfstate",
    "infra/terraform/*.tfstate.*",
    "infra/terraform/marketplace-source.zip",
  ]
}
