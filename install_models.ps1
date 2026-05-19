# Скрипт для автоматической загрузки ИИ-моделей через Ollama
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " Запуск загрузки локальных моделей Ollama " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Проверяем, установлена ли Ollama в системе
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Ошибка: Ollama не установлена в системе!" -ForegroundColor Red
    Write-Host "Пожалуйста, скачайте и установите Ollama с официального сайта: https://ollama.com" -ForegroundColor Yellow
    Read-Host "Нажмите Enter для выхода..."
    exit
}

Write-Host "1. Скачивание текстовой модели Qwen 2.5 (1.5B)..." -ForegroundColor Green
ollama pull qwen2.5:1.5b

Write-Host "2. Скачивание мультимодальной модели Moondream (для анализа картинок)..." -ForegroundColor Green
ollama pull moondream

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✅ Все модели успешно загружены и готовы к работе!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Read-Host "Нажмите Enter, чтобы закрыть окно..."
