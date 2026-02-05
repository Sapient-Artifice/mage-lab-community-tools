print("gpu_tasks module loaded")

from tasks.celery_app import app
import csv
import os
from datetime import datetime
from modules import nvidia_monitor

@app.task(name='mage_scheduler.gpu_tasks.gpu_monitor')
def gpu_monitor():
    # Get GPU info by calling nvidia_monitor functions
    output = nvidia_monitor.get_nvidia_smi_output()
    gpu_info = nvidia_monitor.parse_nvidia_smi(output)

    # Define CSV file path
    csv_file = os.path.join(os.path.dirname(__file__), 'gpu_monitor_log.csv')

    # Check if file exists to write headers
    file_exists = os.path.exists(csv_file)

    # Prepare single row for CSV
    timestamp = datetime.utcnow().isoformat()
    row = {'timestamp': timestamp}
    row.update(gpu_info)  # Add all GPU stats fields

    # Write to CSV
    with open(csv_file, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp'] + list(row.keys())[1:])
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    print(f'Logged GPU info at {timestamp}')

# Other tasks and helpers unchanged

@app.task
def sample_task():
    print('Executing sample task...')

@app.task
def ad_hoc_task(arg):
    print(f'Executing ad hoc task with argument: {arg}')

# Helper function to read and parse the CSV log

def read_gpu_monitor_log(csv_path=None):
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(__file__), 'gpu_monitor_log.csv')

    data = []
    if not os.path.exists(csv_path):
        print(f"CSV file {csv_path} does not exist.")
        return data

    with open(csv_path, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields back to int where possible
            for key in row:
                if key == 'timestamp':
                    continue
                try:
                    # gpu_process_memory_mb and others could be list-like strings, skip those for now
                    if 'gpu_process_memory_mb' in key:
                        continue
                    row[key] = int(row[key])
                except ValueError:
                    pass
            data.append(row)
    return data
