from datetime import datetime, timedelta
from tasks.task_manager import TaskManager
import time

manager = TaskManager()

# Schedule a command to run 1 minute from now
run_time = datetime.utcnow() + timedelta(minutes=1)
task_id = manager.schedule_command("echo 'Hello, Mage!'", run_time)
print(f"Scheduled task with ID: {task_id}")

# Poll for task status every 15 seconds until done
while True:
    status = manager.get_task_status(task_id)
    print(f"Task status: {status['state']}")
    if status['state'] in ['SUCCESS', 'FAILURE', 'REVOKED']:
        print(f"Task result: {status['result']}")
        break
    time.sleep(15)
