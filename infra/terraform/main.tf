provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  customer_db_nodes = {
    customer-db-0 = {
      role        = "customer-db"
      internal_ip = "10.10.0.10"
      replica_id  = 0
    }
    customer-db-1 = {
      role        = "customer-db"
      internal_ip = "10.10.0.11"
      replica_id  = 1
    }
    customer-db-2 = {
      role        = "customer-db"
      internal_ip = "10.10.0.12"
      replica_id  = 2
    }
    customer-db-3 = {
      role        = "customer-db"
      internal_ip = "10.10.0.13"
      replica_id  = 3
    }
    customer-db-4 = {
      role        = "customer-db"
      internal_ip = "10.10.0.14"
      replica_id  = 4
    }
  }

  product_db_nodes = {
    product-db-0 = {
      role        = "product-db"
      internal_ip = "10.10.0.20"
      replica_id  = 0
    }
    product-db-1 = {
      role        = "product-db"
      internal_ip = "10.10.0.21"
      replica_id  = 1
    }
    product-db-2 = {
      role        = "product-db"
      internal_ip = "10.10.0.22"
      replica_id  = 2
    }
    product-db-3 = {
      role        = "product-db"
      internal_ip = "10.10.0.23"
      replica_id  = 3
    }
    product-db-4 = {
      role        = "product-db"
      internal_ip = "10.10.0.24"
      replica_id  = 4
    }
  }

  buyer_frontend_hosts = {
    buyer-frontend-host = {
      role        = "buyer-frontend-host"
      internal_ip = "10.10.0.30"
    }
  }

  seller_frontend_hosts = {
    seller-frontend-host = {
      role        = "seller-frontend-host"
      internal_ip = "10.10.0.40"
    }
  }

  buyer_replica_ports    = [8001, 8002, 8003, 8004]
  seller_replica_ports   = [8101, 8102, 8103, 8104]
  financial_service_port = 8005

  node_zone_sequence = concat(
    sort(keys(local.customer_db_nodes)),
    sort(keys(local.product_db_nodes)),
    sort(keys(local.buyer_frontend_hosts)),
    sort(keys(local.seller_frontend_hosts)),
  )

  zone_assignments = {
    for idx, name in local.node_zone_sequence :
    name => var.zones[idx % length(var.zones)]
  }

  customer_targets   = join(",", [for _, node in local.customer_db_nodes : "${node.internal_ip}:50051"])
  customer_peer_spec = join(",", [for _, node in local.customer_db_nodes : "${node.replica_id}:${node.internal_ip}:56061"])
  product_targets    = join(",", [for _, node in local.product_db_nodes : "${node.internal_ip}:50052"])
  product_raft_peers = [for _, node in local.product_db_nodes : "${node.internal_ip}:6001"]
  buyer_targets      = join(",", [for port in local.buyer_replica_ports : "${local.buyer_frontend_hosts["buyer-frontend-host"].internal_ip}:${port}"])
  seller_targets     = join(",", [for port in local.seller_replica_ports : "${local.seller_frontend_hosts["seller-frontend-host"].internal_ip}:${port}"])
  financial_wsdl     = "http://${local.buyer_frontend_hosts["buyer-frontend-host"].internal_ip}:${local.financial_service_port}/?wsdl"

  instance_definitions = merge(
    {
      for name, node in local.customer_db_nodes : name => {
        role                = node.role
        internal_ip         = node.internal_ip
        machine_type        = var.service_machine_type
        assign_external_ip  = false
        service_name        = "marketplace-customer-db"
        service_description = "Marketplace customer DB replica"
        command             = "/opt/marketplace/venv/bin/python /opt/marketplace/app/server_side/db_service.py"
        tags                = ["pa3", "customer-db"]
        zone                = local.zone_assignments[name]
        env_content = join("\n", [
          "DB_SERVICE_BIND=0.0.0.0:50051",
          "DB_SERVICE_PORT=50051",
          "CUSTOMER_DB_REPLICA_ID=${node.replica_id}",
          "CUSTOMER_DB_REPLICA_PEERS=${local.customer_peer_spec}",
          "CUSTOMER_DB_REPLICATION_BIND_HOST=0.0.0.0",
          "CUSTOMER_DB_REPLICATION_BIND_PORT=56061",
          "CUSTOMER_DB_NAME=customer-database",
          "CUSTOMER_DB_PATH=/opt/marketplace/app/runtime/sqlite/customer-db-replica_${node.replica_id}/customer-database.sqlite",
          "PRODUCT_DB_BACKEND=sqlite",
          "PRODUCT_SQLITE_PATH=/opt/marketplace/app/runtime/sqlite/product-shadow.db",
        ])
        extra_setup = ""
      }
    },
    {
      for name, node in local.product_db_nodes : name => {
        role                = node.role
        internal_ip         = node.internal_ip
        machine_type        = var.service_machine_type
        assign_external_ip  = false
        service_name        = "marketplace-product-db"
        service_description = "Marketplace product DB Raft replica"
        command             = "/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py product-service --host 0.0.0.0 --port 50052"
        tags                = ["pa3", "product-db"]
        zone                = local.zone_assignments[name]
        env_content = join("\n", [
          "PRODUCT_SERVICE_BIND=0.0.0.0:50052",
          "PRODUCT_SERVICE_PORT=50052",
          "PRODUCT_RAFT_SELF=${node.internal_ip}:6001",
          "PRODUCT_RAFT_PARTNERS=${join(",", [for peer in local.product_raft_peers : peer if peer != "${node.internal_ip}:6001"])}",
          "PRODUCT_DB_BACKEND=sqlite",
          "PRODUCT_SQLITE_PATH=/opt/marketplace/app/runtime/sqlite/product-service-50052.db",
          "PRODUCT_SERVICE_DISABLE_PRODUCT_DB=0",
          "CUSTOMER_SERVICE_ADDR=${local.customer_targets}",
          "PRODUCT_SERVICE_DISABLE_CUSTOMER_DB=1",
        ])
        extra_setup = ""
      }
    },
    {
      for name, node in local.buyer_frontend_hosts : name => {
        role                = node.role
        internal_ip         = node.internal_ip
        machine_type        = var.service_machine_type
        assign_external_ip  = true
        service_name        = "marketplace-buyer-frontend-8001"
        service_description = "Marketplace buyer REST frontend replica 1"
        command             = "/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py buyer-rest-server --host 0.0.0.0 --port 8001"
        tags                = ["pa3", "buyer-frontend"]
        zone                = local.zone_assignments[name]
        env_content = join("\n", [
          "CUSTOMER_SERVICE_ADDR=${local.customer_targets}",
          "PRODUCT_SERVICE_ADDR=${local.product_targets}",
          "FINANCIAL_SERVICE_WSDL=${local.financial_wsdl}",
        ])
        extra_setup = <<-EOT
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-buyer-frontend-8002.service
          [Unit]
          Description=Marketplace buyer REST frontend replica 2
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-buyer-frontend-8001.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py buyer-rest-server --host 0.0.0.0 --port 8002
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-buyer-frontend-8002.log
          StandardError=append:/var/log/marketplace/marketplace-buyer-frontend-8002.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-buyer-frontend-8003.service
          [Unit]
          Description=Marketplace buyer REST frontend replica 3
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-buyer-frontend-8001.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py buyer-rest-server --host 0.0.0.0 --port 8003
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-buyer-frontend-8003.log
          StandardError=append:/var/log/marketplace/marketplace-buyer-frontend-8003.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-buyer-frontend-8004.service
          [Unit]
          Description=Marketplace buyer REST frontend replica 4
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-buyer-frontend-8001.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py buyer-rest-server --host 0.0.0.0 --port 8004
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-buyer-frontend-8004.log
          StandardError=append:/var/log/marketplace/marketplace-buyer-frontend-8004.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          cat <<'ENVEOF' >/etc/marketplace/marketplace-financial-service.env
          FINANCIAL_SERVICE_HOST=0.0.0.0
          FINANCIAL_SERVICE_PORT=${local.financial_service_port}
          ENVEOF
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-financial-service.service
          [Unit]
          Description=Marketplace financial SOAP service
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-financial-service.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py financial-service
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-financial-service.log
          StandardError=append:/var/log/marketplace/marketplace-financial-service.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          systemctl enable marketplace-buyer-frontend-8002 marketplace-buyer-frontend-8003 marketplace-buyer-frontend-8004 marketplace-financial-service
          systemctl restart marketplace-buyer-frontend-8002 marketplace-buyer-frontend-8003 marketplace-buyer-frontend-8004 marketplace-financial-service
        EOT
      }
    },
    {
      for name, node in local.seller_frontend_hosts : name => {
        role                = node.role
        internal_ip         = node.internal_ip
        machine_type        = var.service_machine_type
        assign_external_ip  = true
        service_name        = "marketplace-seller-frontend-8101"
        service_description = "Marketplace seller REST frontend replica 1"
        command             = "/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py seller-rest-server --host 0.0.0.0 --port 8101"
        tags                = ["pa3", "seller-frontend"]
        zone                = local.zone_assignments[name]
        env_content = join("\n", [
          "CUSTOMER_SERVICE_ADDR=${local.customer_targets}",
          "PRODUCT_SERVICE_ADDR=${local.product_targets}",
        ])
        extra_setup = <<-EOT
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-seller-frontend-8102.service
          [Unit]
          Description=Marketplace seller REST frontend replica 2
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-seller-frontend-8101.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py seller-rest-server --host 0.0.0.0 --port 8102
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-seller-frontend-8102.log
          StandardError=append:/var/log/marketplace/marketplace-seller-frontend-8102.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-seller-frontend-8103.service
          [Unit]
          Description=Marketplace seller REST frontend replica 3
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-seller-frontend-8101.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py seller-rest-server --host 0.0.0.0 --port 8103
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-seller-frontend-8103.log
          StandardError=append:/var/log/marketplace/marketplace-seller-frontend-8103.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          cat <<'SVCEOF' >/etc/systemd/system/marketplace-seller-frontend-8104.service
          [Unit]
          Description=Marketplace seller REST frontend replica 4
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=marketplace
          WorkingDirectory=/opt/marketplace/app
          EnvironmentFile=/etc/marketplace/marketplace-seller-frontend-8101.env
          ExecStart=/opt/marketplace/venv/bin/python /opt/marketplace/app/run.py seller-rest-server --host 0.0.0.0 --port 8104
          Restart=always
          RestartSec=5
          StandardOutput=append:/var/log/marketplace/marketplace-seller-frontend-8104.log
          StandardError=append:/var/log/marketplace/marketplace-seller-frontend-8104.log

          [Install]
          WantedBy=multi-user.target
          SVCEOF
          systemctl enable marketplace-seller-frontend-8102 marketplace-seller-frontend-8103 marketplace-seller-frontend-8104
          systemctl restart marketplace-seller-frontend-8102 marketplace-seller-frontend-8103 marketplace-seller-frontend-8104
        EOT
      }
    }
  )
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "tls_private_key" "marketplace" {
  algorithm = "ED25519"
}

resource "google_compute_network" "pa3" {
  name                    = "pa3-marketplace-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "pa3" {
  name                     = "pa3-marketplace-subnet"
  ip_cidr_range            = var.network_cidr
  region                   = var.region
  network                  = google_compute_network.pa3.id
  private_ip_google_access = true
}

resource "google_compute_router" "pa3" {
  name    = "pa3-marketplace-router"
  region  = var.region
  network = google_compute_network.pa3.id
}

resource "google_compute_router_nat" "pa3" {
  name                               = "pa3-marketplace-nat"
  router                             = google_compute_router.pa3.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

resource "google_compute_firewall" "allow_internal" {
  name    = "pa3-allow-internal"
  network = google_compute_network.pa3.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  source_ranges = [var.network_cidr]
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "pa3-allow-ssh"
  network = google_compute_network.pa3.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.admin_source_ranges
}

resource "google_compute_firewall" "allow_frontends" {
  name    = "pa3-allow-frontends"
  network = google_compute_network.pa3.name

  allow {
    protocol = "tcp"
    ports    = ["8001-8004", "8101-8104"]
  }

  source_ranges = var.admin_source_ranges
  target_tags   = ["buyer-frontend", "seller-frontend"]
}

data "archive_file" "source_bundle" {
  type        = "zip"
  source_dir  = abspath("${path.module}/../..")
  output_path = "${path.module}/marketplace-source.zip"
  excludes    = var.repo_archive_excludes
}

resource "google_storage_bucket" "source" {
  name                        = "pa3-marketplace-source-${random_id.bucket_suffix.hex}"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket_object" "source_bundle" {
  name   = "marketplace-source.zip"
  bucket = google_storage_bucket.source.name
  source = data.archive_file.source_bundle.output_path
}

resource "google_compute_instance" "node" {
  for_each     = local.instance_definitions
  name         = each.key
  machine_type = each.value.machine_type
  zone         = each.value.zone
  tags         = each.value.tags

  boot_disk {
    initialize_params {
      image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
      size  = var.boot_disk_size_gb
      type  = var.boot_disk_type
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.pa3.id
    network_ip = each.value.internal_ip

    dynamic "access_config" {
      for_each = each.value.assign_external_ip ? [1] : []
      content {}
    }
  }

  metadata = {
    ssh-keys = "marketplace:${trimspace(tls_private_key.marketplace.public_key_openssh)}"
  }

  metadata_startup_script = templatefile("${path.module}/templates/startup.sh.tftpl", {
    source_bucket       = google_storage_bucket.source.name
    source_object       = google_storage_bucket_object.source_bundle.name
    service_name        = each.value.service_name
    service_description = each.value.service_description
    command             = each.value.command
    env_content         = each.value.env_content
    extra_setup         = each.value.extra_setup
  })

  service_account {
    scopes = ["cloud-platform"]
  }

  depends_on = [
    google_storage_bucket_object.source_bundle,
    google_compute_firewall.allow_internal,
    google_compute_firewall.allow_ssh,
  ]
}
