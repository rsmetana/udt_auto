
from nornir import InitNornir
from nornir.core.task import Result, Task
from nornir_netmiko.tasks import netmiko_send_config
from nornir_utils.plugins.functions import print_result
from tqdm import tqdm
import os
from pathlib import Path

CONFIG_DIR = Path("./interface_config")
LOG_DIR = Path("./logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

def send_config_from_file(task: Task) -> Result:
    """
    Pushes a device-specific configuration file using Netmiko.
    Returns a Result with explicit status text for better summary reporting.
    """
    config_file_path = CONFIG_DIR / f"{task.host.name}_config.txt"

    if not config_file_path.exists():
        msg = f"Config file not found for {task.host.name}. Skipping."
        # Store a flag on the host so we can summarize later.
        task.host.data["skipped"] = True
        return Result(host=task.host, changed=False, failed=False, result=msg)

    try:
        r = task.run(
            task=netmiko_send_config,
            config_file=str(config_file_path),
        )
        # Mark success explicitly if no subtask failed
        return Result(
            host=task.host,
            changed=True,  # We intend changes when pushing config
            failed=r.failed,
            result=f"Pushed config from {config_file_path}"
        )
    except Exception as exc:
        # Log the error to a per-host file
        log_path = LOG_DIR / f"{task.host.name}.log"
        with log_path.open("a") as fh:
            fh.write(f"[ERROR] {task.host.name}: {exc}\n")
        return Result(
            host=task.host,
            changed=False,
            failed=True,
            result=f"Error pushing config: {exc}"
        )

def main():
    nr = InitNornir(config_file="config.yaml")

    hosts = list(nr.inventory.hosts.values())
    total_hosts = len(hosts)

    # Per-host progress updates
    with tqdm(total=total_hosts, desc="Pushing Configs", unit="host") as progress_bar:
        result = nr.run(task=send_config_from_file)
        # Advance by 1 per host that has completed.
        # nr.run is synchronous by default; we can simply mark completion after run:
        progress_bar.update(total_hosts)

    # Print detailed results
    print_result(result)

    # Build reliable summary
    processed_hosts = 0
    successful_hosts = 0
    failed_hosts = 0
    skipped_hosts = 0

    for host_name, multi_result in result.items():
        processed_hosts += 1
        # Check our explicit flags and results
        if nr.inventory.hosts[host_name].data.get("skipped"):
            skipped_hosts += 1
            continue

        # If any subtask failed => failed
        if multi_result.failed:
            failed_hosts += 1
        else:
            # We consider success if not failed and not marked skipped.
            successful_hosts += 1

    print("\n--- Deployment Summary ---")
    print(f"Total hosts in inventory: {total_hosts}")
    print(f"Processed (Ran task): {processed_hosts}")
    print(f"Successful operations: {successful_hosts}")
    print(f"Failed operations: {failed_hosts}")
    print(f"Skipped (missing config files): {skipped_hosts}")

if __name__ == "__main__":
    main()
