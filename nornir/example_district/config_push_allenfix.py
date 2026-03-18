from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_config, netmiko_send_command
from nornir_utils.plugins.functions import print_result
from tqdm import tqdm
from pathlib import Path

# Initialize Nornir
nr = InitNornir(config_file="config.yaml")

# Choose how to answer FAZ prompts that appear after certain 'end' lines:
FAZ_CONNECT_REPLY = "n"  # safer default: avoid mid-run connect; set to "y" if you want to connect immediately
FAZ_CONFIRM_REPLY = "y"  # only used if FAZ_CONNECT_REPLY == "y"

def _push_batch(task, batch):
    """Send non-interactive commands together."""
    if not batch:
        return
    task.run(
        task=netmiko_send_config,
        config_commands=batch,
        enter_config_mode=False,   # FortiGate friendly
        exit_config_mode=False,
        cmd_verify=False,
        read_timeout=120,
        delay_factor=2,
    )

def send_config_from_file(task):
    """
    Push per-host config from ./allen_fix/<host>_config.txt, handling:
    - purge + confirm
    - delete + confirm (if used)
    - FAZ/central-management interactive prompts that appear after 'end'
    """
    cfg_path = Path("./allen_fix") / f"{task.host.name}_config.txt"
    if not cfg_path.is_file():
        tqdm.write(f"[{task.host.name}] Config file not found: {cfg_path}")
        return

    with cfg_path.open(encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if ln.strip() != ""]

    batch = []
    # Track which config block we're in so we can anticipate FAZ prompts after 'end'
    context_stack = []  # holds lines like "config system central-management", "config log fortianalyzer setting"

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        lower = line.lower()

        # Entering a block
        if lower.startswith("config "):
            context_stack.append(lower)
            batch.append(raw)
            i += 1
            continue

        # Exiting a block
        if lower == "end":
            batch.append(raw)
            # Flush immediately so we can answer any prompt the device asks right after this 'end'
            _push_batch(task, batch)
            batch = []

            last = context_stack.pop() if context_stack else ""
            if ("log fortianalyzer setting" in last) or ("system central-management" in last):
                # FortiGate may ask: connect now? (y/n)
                task.run(
                    task=netmiko_send_command,
                    command_string=FAZ_CONNECT_REPLY,
                    use_timing=True,
                    delay_factor=2,
                )
                # If you chose to connect now, it may then ask to confirm serial:
                if FAZ_CONNECT_REPLY.lower() == "y":
                    task.run(
                        task=netmiko_send_command,
                        command_string=FAZ_CONFIRM_REPLY,
                        use_timing=True,
                        delay_factor=2,
                    )
            i += 1
            continue

        # Interactive "purge" (e.g., in ipsec phase1/phase2)
        if lower == "purge":
            # Flush pending non-interactive lines
            _push_batch(task, batch)
            batch = []
            # Send purge and immediately answer yes (or respect a literal 'y' next line)
            task.run(task=netmiko_send_command, command_string="purge", use_timing=True, delay_factor=2)
            if i + 1 < len(lines) and lines[i + 1].strip().lower() in ("y", "yes"):
                task.run(task=netmiko_send_command, command_string=lines[i + 1].strip(), use_timing=True, delay_factor=2)
                i += 1
            else:
                task.run(task=netmiko_send_command, command_string="y", use_timing=True, delay_factor=2)
            i += 1
            continue

        # Deletes that often prompt (narrow this if needed)
        if lower.startswith("delete "):
            _push_batch(task, batch)
            batch = []
            task.run(task=netmiko_send_command, command_string=raw, use_timing=True, delay_factor=2)
            task.run(task=netmiko_send_command, command_string="y", use_timing=True, delay_factor=2)
            i += 1
            continue

        # Default: accumulate for batch send
        batch.append(raw)
        i += 1

    # Flush any remaining lines
    _push_batch(task, batch)

def main():
    with tqdm(total=len(nr.inventory.hosts), desc="Pushing Configs") as bar:
        result = nr.run(task=send_config_from_file)
        bar.update(len(nr.inventory.hosts))

    print_result(result)

    # Clean summary (Nornir 3)
    total = len(nr.inventory.hosts)
    processed = len(result)
    failed = len(result.failed_hosts)
    succeeded = processed - failed
    skipped = total - processed

    print("\n--- Deployment Summary ---")
    print(f"Total Hosts in inventory: {total}")
    print(f"Processed (Ran task): {processed}")
    print(f"Successful operations: {succeeded}")
    print(f"Failed operations: {failed}")
    if skipped:
        print(f"Skipped (no task run): {skipped}")

if __name__ == "__main__":
    main()