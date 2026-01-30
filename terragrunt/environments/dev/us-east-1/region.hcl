# =============================================================================
# Region Configuration - US East 1
# =============================================================================
# This file contains region-specific settings.
# =============================================================================

locals {
  aws_region   = "us-east-1"
  region_alias = "use1"

  # Region-specific settings
  settings = {
    # Availability zones
    availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]
  }
}
