# PA3 GCP Deployment

This Terraform stack deploys the PA3 marketplace onto 19 Google Compute Engine VMs:

- 5 customer DB replicas
- 5 product DB replicas
- 4 buyer frontend replicas
- 4 seller frontend replicas
- 1 benchmark VM

The benchmark VM also runs the SOAP financial service on port `8002` so the deployed buyer frontends can keep using the PA2 communication path.

## Layout

Private subnet addresses are fixed:

- Customer DB replicas: `10.10.0.10` to `10.10.0.14`
- Product DB replicas: `10.10.0.20` to `10.10.0.24`
- Buyer frontends: `10.10.0.30` to `10.10.0.33`
- Seller frontends: `10.10.0.40` to `10.10.0.43`
- Benchmark + financial service: `10.10.0.50`

Each VM starts one `systemd` service and unpacks the repo from a GCS bucket populated by Terraform from your local checkout.

To fit the default student-project quotas, the stack gives only the benchmark VM a public IP, uses shared-core machine types by default, and uses standard persistent disks.

## Apply

From the repo root:

```powershell
cd infra\terraform
terraform init
terraform apply
```

If Terraform rejects the default `project_id`, replace it with your actual GCP project ID string in `terraform.tfvars`.

## After Apply

Get the benchmark VM IP:

```powershell
terraform output benchmark_external_ip
```

SSH in:

```powershell
ssh marketplace@<benchmark-external-ip>
```

Run the full PA3 benchmark from the benchmark VM:

```bash
/opt/marketplace/bin/run_pa3_benchmark.sh
```

This writes results to:

```text
/opt/marketplace/app/runtime/pa3_benchmark_results.json
```

## Manual Checks

View the SOAP financial service:

```bash
curl http://127.0.0.1:8002/?wsdl
```

Check any service log:

```bash
sudo journalctl -u marketplace-product-db -n 100 --no-pager
sudo journalctl -u marketplace-customer-db -n 100 --no-pager
sudo journalctl -u marketplace-buyer-frontend -n 100 --no-pager
sudo journalctl -u marketplace-seller-frontend -n 100 --no-pager
sudo journalctl -u marketplace-financial-service -n 100 --no-pager
```

## Destroy

```powershell
terraform destroy
```
