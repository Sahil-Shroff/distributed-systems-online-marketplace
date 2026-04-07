from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"
RUNTIME_DIR = REPO_ROOT / "runtime" / "cloud_cli"
JSON_MARKER = "__PA3_JSON__="
ACTIVE_TERRAFORM_DIR = TERRAFORM_DIR

DEPLOYMENT_CANDIDATES = [
    {"region": "us-west2", "zones": ["us-west2-a", "us-west2-b", "us-west2-c"]},
    {"region": "us-west1", "zones": ["us-west1-a", "us-west1-b", "us-west1-c"]},
    {"region": "us-east1", "zones": ["us-east1-b", "us-east1-c", "us-east1-d"]},
    {"region": "us-east4", "zones": ["us-east4-a", "us-east4-b", "us-east4-c"]},
    {"region": "us-central1", "zones": ["us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"]},
]

MACHINE_TYPE_CANDIDATES = [
    "e2-small",
    "e2-medium",
    "n1-standard-1",
    "e2-micro",
    "f1-micro",
]


class CommandError(RuntimeError):
    pass


def resolve_executable(name: str) -> str:
    candidates = [name]
    if os.name == "nt":
        candidates = [f"{name}.exe", f"{name}.cmd", f"{name}.bat", name]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    raise CommandError(f"Unable to locate executable on PATH: {name}")


def run_cmd(
    args: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and proc.returncode != 0:
        raise CommandError(
            f"Command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def terraform(args: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    tf_args = [resolve_executable("terraform"), f"-chdir={ACTIVE_TERRAFORM_DIR}"]
    tf_args.extend(args)
    return run_cmd(tf_args, capture=capture, check=check)


def use_fresh_terraform_workdir() -> Path:
    global ACTIVE_TERRAFORM_DIR
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    fresh_dir = Path(tempfile.mkdtemp(prefix=f"pa3-terraform-{timestamp}-"))
    fresh_dir.mkdir(parents=True, exist_ok=True)
    for name in ["main.tf", "variables.tf", "outputs.tf", "versions.tf", ".terraform.lock.hcl"]:
        src = TERRAFORM_DIR / name
        if src.exists():
            shutil.copy2(src, fresh_dir / name)
    templates_src = TERRAFORM_DIR / "templates"
    if templates_src.exists():
        shutil.copytree(templates_src, fresh_dir / "templates", dirs_exist_ok=True)
    main_tf = fresh_dir / "main.tf"
    if main_tf.exists():
        content = main_tf.read_text(encoding="utf-8")
        content = content.replace(
            'source_dir  = abspath("${path.module}/../..")',
            f'source_dir  = "{REPO_ROOT.as_posix()}"',
        )
        main_tf.write_text(content, encoding="utf-8")
    ACTIVE_TERRAFORM_DIR = fresh_dir
    return fresh_dir


def ensure_workspace(project_id: str) -> None:
    select = terraform(["workspace", "select", project_id], capture=True, check=False)
    if select.returncode != 0:
        terraform(["workspace", "new", project_id])


def load_outputs(project_id: str) -> dict:
    ensure_workspace(project_id)
    proc = terraform(["output", "-json"], capture=True)
    return json.loads(proc.stdout)


def output_value(outputs: dict, key: str):
    return outputs[key]["value"]


def instance_inventory(project_id: str) -> dict[str, dict]:
    outputs = load_outputs(project_id)
    return output_value(outputs, "vm_inventory")


def buyer_host_name() -> str:
    return "buyer-frontend-host"


def seller_host_name() -> str:
    return "seller-frontend-host"


def product_instance_names() -> list[str]:
    return [f"product-db-{idx}" for idx in range(5)]


def customer_instance_names() -> list[str]:
    return [f"customer-db-{idx}" for idx in range(5)]


def gcloud_ssh(instance: str, zone: str, project_id: str, command: str, *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    args = [
        resolve_executable("gcloud"),
        "compute",
        "ssh",
        f"marketplace@{instance}",
        f"--project={project_id}",
        f"--zone={zone}",
        "--command",
        command,
    ]
    return run_cmd(args, capture=capture)


def gcloud_scp(local_path: Path, instance: str, zone: str, project_id: str, remote_path: str) -> None:
    args = [
        resolve_executable("gcloud"),
        "compute",
        "scp",
        str(local_path),
        f"marketplace@{instance}:{remote_path}",
        f"--project={project_id}",
        f"--zone={zone}",
    ]
    run_cmd(args)


def wait_for_remote_ready(
    instance: str,
    zone: str,
    project_id: str,
    *,
    timeout_seconds: int = 600,
    interval_seconds: int = 10,
) -> None:
    deadline = time.time() + timeout_seconds
    check_cmd = (
        "test -d /opt/marketplace/app "
        "&& test -x /opt/marketplace/venv/bin/python "
        "&& test -f /opt/marketplace/app/run.py "
        "&& PYTHONPATH=/opt/marketplace/app /opt/marketplace/venv/bin/python -c 'import requests'"
    )
    last_error: CommandError | None = None
    while time.time() < deadline:
        try:
            gcloud_ssh(instance, zone, project_id, check_cmd, capture=True)
            return
        except CommandError as exc:
            last_error = exc
            time.sleep(interval_seconds)
    raise CommandError(
        f"Remote host {instance} did not finish startup within {timeout_seconds}s.\n"
        f"Last error:\n{last_error}"
    )


def run_remote_python(instance: str, zone: str, project_id: str, script_name: str, script_body: str) -> dict:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=f"-{script_name}.py",
        prefix="pa3-cloud-",
        dir=RUNTIME_DIR,
        delete=False,
        encoding="utf-8",
    ) as handle:
        handle.write(script_body)
        temp_path = Path(handle.name)
    remote_path = f"/tmp/{temp_path.name}"
    try:
        wait_for_remote_ready(instance, zone, project_id)
        gcloud_scp(temp_path, instance, zone, project_id, remote_path)
        proc = gcloud_ssh(
            instance,
            zone,
            project_id,
            f"cd /opt/marketplace/app && PYTHONPATH=/opt/marketplace/app /opt/marketplace/venv/bin/python {remote_path}",
            capture=True,
        )
        payload_line = None
        for line in proc.stdout.splitlines():
            if line.startswith(JSON_MARKER):
                payload_line = line[len(JSON_MARKER) :]
        if payload_line is None:
            raise CommandError(
                f"Remote script did not emit JSON marker on {instance}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        return json.loads(payload_line)
    finally:
        temp_path.unlink(missing_ok=True)


def deploy(args: argparse.Namespace) -> None:
    try:
        terraform(["init", "-upgrade"], capture=True)
    except CommandError as exc:
        message = str(exc).lower()
        if "state file could not be read" in message or "locked a portion of the file" in message:
            fresh_dir = use_fresh_terraform_workdir()
            print(f"Using fresh Terraform workdir due to local state lock: {fresh_dir}")
            terraform(["init", "-upgrade"], capture=True)
        else:
            raise
    ensure_workspace(args.project_id)

    explicit_region = "--region" in os.sys.argv
    explicit_zones = "--zones" in os.sys.argv
    explicit_machine_type = "--service-machine-type" in os.sys.argv

    region_zone_candidates: list[tuple[str, list[str]]] = []
    seen_region_zone_keys: set[tuple[str, tuple[str, ...]]] = set()

    preferred_region = args.region
    preferred_zones = list(args.zones or [])
    if preferred_region and preferred_zones:
        key = (preferred_region, tuple(preferred_zones))
        seen_region_zone_keys.add(key)
        region_zone_candidates.append((preferred_region, preferred_zones))

    if not explicit_region and not explicit_zones:
        for candidate in DEPLOYMENT_CANDIDATES:
            key = (candidate["region"], tuple(candidate["zones"]))
            if key in seen_region_zone_keys:
                continue
            seen_region_zone_keys.add(key)
            region_zone_candidates.append((candidate["region"], list(candidate["zones"])))

    machine_types: list[str] = []
    seen_machine_types: set[str] = set()
    if args.service_machine_type:
        machine_types.append(args.service_machine_type)
        seen_machine_types.add(args.service_machine_type)
    if not explicit_machine_type:
        for machine_type in MACHINE_TYPE_CANDIDATES:
            if machine_type in seen_machine_types:
                continue
            machine_types.append(machine_type)
            seen_machine_types.add(machine_type)

    attempts = [
        (region, zones, machine_type)
        for region, zones in region_zone_candidates
        for machine_type in machine_types
    ]

    last_error: CommandError | None = None
    for index, (region, zones, machine_type) in enumerate(attempts, start=1):
        print(
            f"Deploy attempt {index}/{len(attempts)}: "
            f"region={region} zones={zones} machine_type={machine_type}"
        )
        apply_args = [
            "apply",
            "-auto-approve",
            "-parallelism=2",
            f"-var=project_id={args.project_id}",
            f"-var=service_machine_type={machine_type}",
            f"-var=region={region}",
            f"-var=zones={json.dumps(zones)}",
        ]
        try:
            terraform(apply_args, capture=True)
            args.region = region
            args.zones = zones
            args.service_machine_type = machine_type
            print("Terraform apply completed.")
            show_inventory(args)
            return
        except CommandError as exc:
            last_error = exc
            print(f"Deploy attempt failed: {exc}")
            destroy_args = [
                "destroy",
                "-auto-approve",
                "-parallelism=2",
                f"-var=project_id={args.project_id}",
                f"-var=service_machine_type={machine_type}",
                f"-var=region={region}",
                f"-var=zones={json.dumps(zones)}",
            ]
            terraform(destroy_args, capture=True, check=False)

    raise CommandError(f"All deployment attempts failed.\nLast error:\n{last_error}")


def show_inventory(args: argparse.Namespace) -> None:
    outputs = load_outputs(args.project_id)
    inventory = output_value(outputs, "vm_inventory")
    print("Terraform inventory view:")
    print("  If you manually deleted VMs in GCP, run `deploy` or `run-all` first to recreate them.")
    print("Current deployment:")
    for name in sorted(inventory):
        vm = inventory[name]
        print(
            f"  {name}: zone={vm['zone']} internal={vm['internal_ip']} external={vm['external_ip']}"
        )
    print(f"Buyer targets:  {output_value(outputs, 'buyer_frontend_public_targets')}")
    print(f"Seller targets: {output_value(outputs, 'seller_frontend_public_targets')}")


def restart_services(args: argparse.Namespace) -> None:
    inventory = instance_inventory(args.project_id)
    try:
        for name in customer_instance_names():
            vm = inventory[name]
            gcloud_ssh(name, vm["zone"], args.project_id, "sudo systemctl restart marketplace-customer-db")
            print(f"Restarted customer replica on {name}")
        for name in product_instance_names():
            vm = inventory[name]
            gcloud_ssh(name, vm["zone"], args.project_id, "sudo systemctl restart marketplace-product-db")
            print(f"Restarted product replica on {name}")

        buyer_vm = inventory[buyer_host_name()]
        gcloud_ssh(
            buyer_host_name(),
            buyer_vm["zone"],
            args.project_id,
            "sudo systemctl restart marketplace-buyer-frontend-8001 "
            "marketplace-buyer-frontend-8002 marketplace-buyer-frontend-8003 "
            "marketplace-buyer-frontend-8004 marketplace-financial-service",
        )
        print("Restarted buyer frontend host services")

        seller_vm = inventory[seller_host_name()]
        gcloud_ssh(
            seller_host_name(),
            seller_vm["zone"],
            args.project_id,
            "sudo systemctl restart marketplace-seller-frontend-8101 "
            "marketplace-seller-frontend-8102 marketplace-seller-frontend-8103 "
            "marketplace-seller-frontend-8104",
        )
        print("Restarted seller frontend host services")
    except CommandError as exc:
        raise CommandError(
            f"{exc}\n\nOne or more VMs are missing. Run `python tools/pa3_cloud_cli.py --project-id {args.project_id} deploy` "
            "or use `run-all` to recreate the deployment first."
        ) from exc
    print(f"Waiting {args.wait_seconds}s for services to settle...")
    time.sleep(args.wait_seconds)


def _demo_prefix(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}"


def run_api_workflow(args: argparse.Namespace) -> None:
    outputs = load_outputs(args.project_id)
    inventory = output_value(outputs, "vm_inventory")
    buyer_targets = output_value(outputs, "buyer_frontend_public_targets")
    seller_targets = output_value(outputs, "seller_frontend_public_targets")
    prefix = _demo_prefix(args.prefix)

    seller_script = textwrap.dedent(
        f"""
        import json
        from client_side.seller_interface.seller_rest_client import SellerRestClient

        prefix = {prefix!r}
        client = SellerRestClient({seller_targets!r}, 0)
        username = prefix + "_seller"
        password = "pw123"

        seller_id = client.create_account(username, password)
        logged_in_id = client.login(username, password)
        rating_before = client.get_rating()
        item_id = client.register_item_for_sale(
            item_name=prefix + "_item",
            category=1,
            keywords=["demo", prefix.lower()],
            condition="New",
            price=20.0,
            quantity=5,
        )
        items_after_register = client.display_items_for_sale()
        item_before = client.get_item(item_id)
        client.change_item_price(item_id, 25.0)
        new_quantity = client.update_units_for_sale(item_id, 1)
        item_after = client.get_item(item_id)

        print({JSON_MARKER!r} + json.dumps({{
            "username": username,
            "password": password,
            "seller_id": seller_id,
            "logged_in_id": logged_in_id,
            "session_id": client.session_id,
            "rating_before": rating_before,
            "item_id": item_id,
            "item_before": item_before,
            "new_quantity": new_quantity,
            "item_after": item_after,
            "items_after_register": items_after_register,
        }}))
        """
    ).strip()

    seller_vm = inventory[seller_host_name()]
    seller_result = run_remote_python(
        seller_host_name(),
        seller_vm["zone"],
        args.project_id,
        "seller-flow",
        seller_script,
    )

    buyer_script = textwrap.dedent(
        f"""
        import json
        from client_side.buyer_interface.buyer_rest_client import BuyerRestClient

        prefix = {prefix!r}
        buyer_targets = {buyer_targets!r}
        item_id = {seller_result['item_id']!r}
        seller_id = {seller_result['seller_id']!r}

        client = BuyerRestClient(buyer_targets, 0)
        username = prefix + "_buyer"
        password = "pw123"

        buyer_id = client.create_account(username, password)
        logged_in_id = client.login(username, password)
        search_result = client.search_items(category=1, keywords=[prefix.lower()])
        item_view = client.get_item(item_id)
        client.add_to_cart(item_id, 1)
        cart_after_add = client.display_cart()
        seller_rating = client.get_seller_rating(seller_id)
        purchase_history_before = client.get_purchase_history()

        print({JSON_MARKER!r} + json.dumps({{
            "username": username,
            "password": password,
            "buyer_id": buyer_id,
            "logged_in_id": logged_in_id,
            "session_id": client.session_id,
            "search_result": search_result,
            "item_view": item_view,
            "cart_after_add": cart_after_add,
            "seller_rating": seller_rating,
            "purchase_history_before": purchase_history_before,
        }}))
        """
    ).strip()

    buyer_vm = inventory[buyer_host_name()]
    buyer_result = run_remote_python(
        buyer_host_name(),
        buyer_vm["zone"],
        args.project_id,
        "buyer-flow",
        buyer_script,
    )

    summary = {
        "project_id": args.project_id,
        "buyer_targets": buyer_targets,
        "seller_targets": seller_targets,
        "prefix": prefix,
        "seller": seller_result,
        "buyer": buyer_result,
        "manual_next_steps": {
            "seller_cli": [
                f"python run.py seller-rest-cli \"{seller_targets}\" 0",
                f"login {seller_result['username']} {seller_result['password']}",
                "list_items",
                f"get_item {seller_result['item_id']}",
                "logout",
            ],
            "buyer_cli": [
                f"python run.py buyer-rest-cli \"{buyer_targets}\" 0",
                f"login {buyer_result['username']} {buyer_result['password']}",
                "display_cart",
                "save_cart",
                "display_cart",
                f"purchase {buyer_result['username']} 4111111111111111 12/30 123",
                "purchase_history",
                "logout",
            ],
            "notes": [
                "The buyer already has an active cart with one unit of the demo item.",
                "Use display_cart before save_cart to show the active cart state.",
                "After save_cart, run purchase and then purchase_history to show the final flow.",
            ],
        },
    }
    output_path = RUNTIME_DIR / f"{prefix}-api-workflow.json"
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"API workflow completed. Summary written to {output_path}")
    print(json.dumps(summary, indent=2))


def print_db_commands(args: argparse.Namespace) -> None:
    inventory = instance_inventory(args.project_id)
    print("Product DB checks:")
    for name in product_instance_names():
        vm = inventory[name]
        query = "SELECT item_id, item_name, sale_price, quantity, seller_id FROM items;"
        print(
            f"  gcloud compute ssh marketplace@{name} --project={args.project_id} --zone={vm['zone']} "
            f"--command \"sqlite3 /opt/marketplace/app/runtime/sqlite/product-service-50052.db '{query}'\""
        )
    print("Customer DB checks:")
    for idx, name in enumerate(customer_instance_names()):
        vm = inventory[name]
        query = (
            "SELECT seller_id, username, seller_feedback, items_sold FROM sellers; "
            "SELECT buyer_id, username FROM buyers; "
            "SELECT session_id, role, user_id FROM sessions;"
        )
        print(
            f"  gcloud compute ssh marketplace@{name} --project={args.project_id} --zone={vm['zone']} "
            f"--command \"sqlite3 /opt/marketplace/app/runtime/sqlite/customer-db-replica_{idx}/customer-database.sqlite '{query}'\""
        )


def run_all(args: argparse.Namespace) -> None:
    deploy(args)
    restart_services(args)
    run_api_workflow(args)
    print_db_commands(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PA3 cloud deployment and demo CLI")
    parser.add_argument("--project-id", default="prismatic-night-491821-g0")
    parser.add_argument("--region", default="us-west2")
    parser.add_argument("--service-machine-type", default="e2-micro")
    parser.add_argument("--zones", nargs="*", default=["us-west2-a", "us-west2-b", "us-west2-c"])

    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("deploy", help="Create or recreate the GCP deployment with Terraform")
    p.set_defaults(func=deploy)

    p = sub.add_parser("inventory", help="Show VM inventory and public targets")
    p.set_defaults(func=show_inventory)

    p = sub.add_parser("restart-services", help="Restart all systemd services on the deployed VMs")
    p.add_argument("--wait-seconds", type=int, default=20)
    p.set_defaults(func=restart_services)

    p = sub.add_parser("run-apis", help="Run the full buyer/seller API workflow against the cloud deployment")
    p.add_argument("--prefix", default="viva")
    p.set_defaults(func=run_api_workflow)

    p = sub.add_parser("db-commands", help="Print gcloud/sqlite commands for manual DB verification")
    p.set_defaults(func=print_db_commands)

    p = sub.add_parser("run-all", help="Deploy, restart services, run the API workflow, and print DB checks")
    p.add_argument("--prefix", default="viva")
    p.add_argument("--wait-seconds", type=int, default=20)
    p.set_defaults(func=run_all)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
