from datetime import date
from calendar import monthrange

def maremoto_callback(interface, args, msg, metadata):
    from data import last_maremoto_date

    today = date.today()

    years = today.year - last_maremoto_date.year
    months = today.month - last_maremoto_date.month
    days = today.day - last_maremoto_date.day

    if days < 0:
        months -= 1
        # Obtengo días del mes anterior para restar correctamente
        prev_month = today.month - 1 if today.month > 1 else 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days += monthrange(prev_year, prev_month)[1]

    if months < 0:
        years -= 1
        months += 12

    str_years = "año" if years == 1 else "años"
    str_months = "mes" if months == 1 else "meses"
    str_days = "día" if days == 1 else "días"

    response = (f'Han pasado {years} {str_years}, {months} {str_months} y '
                f'{days} {str_days} desde el último maremoto en Chipiona. ('
                f'1/11/1755)')

    interface.reply_to_message(response, metadata)