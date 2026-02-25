from celery import Celery

app = Celery('mage_scheduler', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

app.conf.timezone = 'UTC'

app.conf.beat_schedule = {
    'gpu-monitor-every-60-seconds': {
        'task': 'mage_scheduler.gpu_tasks.gpu_monitor',
        'schedule': 60.0,  # seconds
    },
    'check-recurring-tasks-every-60-seconds': {
        'task': 'tasks.recurring_task.check_recurring_tasks',
        'schedule': 60.0,
    },
    'check-waiting-tasks-every-60-seconds': {
        'task': 'tasks.dependency_task.check_waiting_tasks',
        'schedule': 60.0,
    },
}

# Import tasks modules to register decorated tasks
import tasks.gpu_tasks
import tasks.notification_task
import tasks.recurring_task
import tasks.dependency_task

if __name__ == '__main__':
    app.start()
