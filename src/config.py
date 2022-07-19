import datetime
import pytz

# DEFINE GLOBAL PARAMETERS
APP_TITLE = "ResiDoodle"
ABOUT_MARKDOWN = f'''# 🦝 {APP_TITLE}
*There is no trash cannot, only trash can.*

© 2022 Maxwell Spadafore
'''
APP_PAGES = ['Home', 'About', 'Feedback']

TZ = pytz.timezone('America/Detroit')
CALENDAR_URL = 'http://www.shiftadmin.com/schedule_ical_group.php?cd=UIwfTiYhARsmldQIKdk1addmZLRORGLhbHKREh1COb8%3D&gfs=g9,f1,f2,f3&local=0&vc=1'
SCHED_ICAL_START_DATE = TZ.localize(datetime.datetime(2022, 7, 1, 6, 0, 0)).astimezone(pytz.utc)
SCHED_ICAL_END_DATE = TZ.localize(datetime.datetime(2023, 6, 30, 23, 59, 59)).astimezone(pytz.utc)
RESIDENTS_CSV = 'data/residents.csv'
MASTER_BLOCK_SCHEDULE_CSV = 'data/master_block_schedule.csv'
OFF_SERVICE_HOURS_CSV = 'data/off_service_hours.csv'