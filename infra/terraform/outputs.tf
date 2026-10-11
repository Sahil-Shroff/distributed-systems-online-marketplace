output "buyer_frontend_targets" {
  description = "Internal buyer frontend addresses for clients and benchmarks."
  value       = local.buyer_targets
}

output "seller_frontend_targets" {
  description = "Internal seller frontend addresses for clients and benchmarks."
  value       = local.seller_targets
}

output "customer_db_targets" {
  description = "Internal customer DB gRPC targets."
  value       = local.customer_targets
}

output "product_db_targets" {
  description = "Internal product DB gRPC targets."
  value       = local.product_targets
}

output "buyer_frontend_public_ip" {
  description = "External IP of the buyer frontend host."
  value       = try(google_compute_instance.node["buyer-frontend-host"].network_interface[0].access_config[0].nat_ip, null)
}

output "seller_frontend_public_ip" {
  description = "External IP of the seller frontend host."
  value       = try(google_compute_instance.node["seller-frontend-host"].network_interface[0].access_config[0].nat_ip, null)
}

output "buyer_frontend_public_targets" {
  description = "Public buyer frontend replica addresses."
  value = join(",", [
    for port in local.buyer_replica_ports :
    "${try(google_compute_instance.node["buyer-frontend-host"].network_interface[0].access_config[0].nat_ip, "")}:${port}"
  ])
}

output "seller_frontend_public_targets" {
  description = "Public seller frontend replica addresses."
  value = join(",", [
    for port in local.seller_replica_ports :
    "${try(google_compute_instance.node["seller-frontend-host"].network_interface[0].access_config[0].nat_ip, "")}:${port}"
  ])
}

output "financial_service_internal_wsdl" {
  description = "Internal WSDL URL used by the buyer frontends."
  value       = local.financial_wsdl
}

output "vm_inventory" {
  description = "Role, internal IP, and external IP for every deployed VM."
  value = {
    for name, vm in google_compute_instance.node : name => {
      internal_ip = vm.network_interface[0].network_ip
      external_ip = try(vm.network_interface[0].access_config[0].nat_ip, null)
      zone        = vm.zone
      tags        = vm.tags
    }
  }
}

output "ssh_private_key" {
  description = "SSH private key for the marketplace user."
  value       = tls_private_key.marketplace.private_key_openssh
  sensitive   = true
}
