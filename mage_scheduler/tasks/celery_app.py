from celery import Celery

app = Celery('mage_scheduler', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

app.conf.timezone = 'UTC'

app.conf.beat_schedule = {
    'gpu-monitor-every-60-seconds': {
        'task': 'mage_scheduler.gpu_tasks.gpu_monitor',
        'schedule': 60.0,  # seconds
    },
}

# Import tasks modules to register decorated tasks
import tasks.gpu_tasks
import tasks.notification_task

if __name__ == '__main__':
    app.start()
