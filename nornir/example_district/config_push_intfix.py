from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_config
from nornir_utils.plugins.functions import print_result
from tqdm import tqdm
import os

# Initialize Nornir
nr = InitNornir(config_file="config.yaml")

# Define a task to send configuration from a file
def send_config_from_file(task):
    """
    Pushes a device-specific configuration file using Netmiko.
    """
    config_file_path = f'./intfix/{task.host.name}_config.txt'

    if not os.path.exists(config_file_path):
        tqdm.write(f"Config file not found for {task.host.name}. Skipping.")
        # Returning None stops this specific task without marking it as a failure
        return 

    task.run(
        task=netmiko_send_config,
        config_file=config_file_path
    )

# Run the task with a progress bar and summary
def main():
    # Wrap the Nornir run with tqdm to get a progress bar
    with tqdm(total=len(nr.inventory.hosts), desc="Pushing Configs") as progress_bar:
        result = nr.run(
            task=send_config_from_file
            # Note: TQDM typically works better by wrapping the iteration of hosts
            # rather than wrapping the nr.run() call directly in Nornir v3 unless
            # using the specific nornir_progress2 library. 
            # The current approach gives a single update when run is complete.
        )
        # Manually update the progress bar to 100% when the run finishes
        progress_bar.update(len(nr.inventory.hosts))


    # Print the detailed result of all tasks (includes success/failure details)
    print_result(result)

    # Print a summary of the results (Nornir 3 compatible way)
    print("\n--- Deployment Summary ---")
    
    successful_hosts = len(result) # Length of the result dictionary
    failed_hosts = len(result.failed_hosts)
    skipped_hosts = len(nr.inventory.hosts) - successful_hosts - failed_hosts # Rough estimate of hosts skipped due to early exit/None return

    print(f"Total Hosts in inventory: {len(nr.inventory.hosts)}")
    print(f"Processed (Ran task): {successful_hosts + failed_hosts}")
    print(f"Successful operations: {successful_hosts}")
    print(f"Failed operations: {failed_hosts}")
    
if __name__ == "__main__":
    main()
