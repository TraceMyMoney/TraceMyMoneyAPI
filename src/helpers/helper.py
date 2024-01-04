from datetime import datetime

def provide_todays_date(provided_date=None, str_format=True):
    custom_date = provided_date or datetime.now()
    return f'{custom_date.day}-{custom_date.month}-{custom_date.year} 00:00'\
        if str_format else (custom_date.year, custom_date.month, custom_date.day)
