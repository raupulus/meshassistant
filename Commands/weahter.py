def weather_callback(interface, args, msg, metadata):
    print('weather')

    response = 'Tiempo real: ???; Predicción: ???'

    interface.reply_to_message(response, metadata)