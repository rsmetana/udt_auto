import os
from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_utils.plugins.functions import print_result
from nornir_jinja2.plugins.tasks import template_file

def generate_config_file(task: Task):
    """
    Renders the Jinja2 template and saves the result to a local file.
    """
    # Render the Jinja2 template
    config = task.run(
        task=template_file,
        template="intfix.j2",
        path="./templates"  # Path to your Jinja2 templates
    )
    
    # Ensure output directory exists
    output_dir = "./intfix"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Save the rendered configuration to a file named after the host
    config_filename = f"{output_dir}/{task.host.name}_config.txt"
    with open(config_filename, "w") as f:
        f.write(config.result)
    
    # Return a success message or the filename for logging
    return Result(
        host=task.host,
        result=f"Configuration successfully generated and saved to {config_filename}"
    )

# Initialize Nornir
# Ensure config.yaml points to your inventory
nr = InitNornir(config_file="config.yaml")

# Run the task on all hosts in the inventory (or filter to just 'cox-ms')
# result = nr.run(task=generate_config_file, filter=F(name="cox-ms"))
result = nr.run(task=generate_config_file)


# Print the result of the task execution (will show where files were saved)
print_result(result)
