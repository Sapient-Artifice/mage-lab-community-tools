from celery_app import app
from celery.beat import ScheduleEntry
from celery.schedules import crontab
from datetime import datetime

# Simplistic in-memory schedule, for real use store in DB or use custom beat schedule
custom_schedule = {}


def add_periodic_task(name, task, minute='*', hour='*'):
    entry = ScheduleEntry(name, task, crontab(minute=minute, hour=hour), datetime.utcnow())
    custom_schedule[name] = entry
    # Patching the Celery beat_schedule
    app.conf.beat_schedule[name] = {
        'task': task,
        'schedule': crontab(minute=minute, hour=hour),
    }

def remove_periodic_task(name):
    if name in custom_schedule:
        del custom_schedule[name]
    if name in app.conf.beat_schedule:
        del app.conf.beat_schedule[name]


def list_tasks():
    return list(app.conf.beat_schedule.keys())
