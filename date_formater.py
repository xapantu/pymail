import time
import datetime

# Transaltions stuff
import locale;
# Seriously, it is the 21th century, and we have to do that :/
locale.setlocale(locale.LC_ALL, "");

_today = ""
_yesterday = ""
def init_date():
    global _today, _yesterday
    _today = time.strftime("%d %b %Y")
    dt = datetime.timedelta(days=1)
    _yesterday = time.strftime("%d %b %Y", (datetime.datetime.today() - dt).timetuple())

def format_date(row, full = False):
    th_time = time.strptime(row, "%Y-%m-%d %H:%M:%S")
    time_format = time.strftime("%d %b %Y", th_time)
    if time_format == _today:
        time_format = time.strftime("%H:%M", th_time)
    elif time_format == _yesterday:
        time_format = time.strftime("hier" + ", %H:%M", th_time)
    elif full:
        time_format = time.strftime("%a %d %b %Y %H:%M", th_time)
    return time_format.decode("utf-8")
