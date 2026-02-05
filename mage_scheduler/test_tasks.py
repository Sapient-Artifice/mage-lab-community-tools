from tasks import ad_hoc_task
import time

print('Sending ad hoc task...')
ad_hoc_task.delay('hello from test script')

# Wait some seconds to allow worker to process
print('Waiting for task to complete...')
time.sleep(10)
print('Test finished.')
