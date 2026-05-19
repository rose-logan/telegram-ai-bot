import requests

def get_weather_moscow():
    """Простой парсер погоды для Москвы."""
    
    # Запрос к API OpenWeatherMap на погоду в Москве
    response = requests.get('https://api.openweathermap.org/data/2.5/weather?q=Москва&appid=<YOUR_API_KEY>')
    
    if response.status_code == 200:
        weather_data = response.json()
        
        # Получение информации о текущей погоде
        current_weather = weather_data['weather'][0]['description']
        temperature = round(weather_data['main']['temp'] - 273.15, 2)  # Цельсий
        
        print(f"Текущая погода в Москве: {current_weather}")
        print(f"Температура: {temperature}°C")
    else:
        print("Ошибка при запросе данных.")

# Пример использования
get_weather_moscow()