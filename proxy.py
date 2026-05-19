import asyncio
import logging
import socket

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 8888

# Наш живой узел, который гарантированно пропускает твой WARP и Wi-Fi
TARGET_GATEWAY = 'telegram.crocnet.ru'
TARGET_PORT = 443

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(16384) # 16KB буфер для максимальной скорости медиа
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()

async def handle_client(reader, writer):
    try:
        # 1. Читаем приветствие SOCKS5
        header = await reader.readexactly(2)
        if header[0] != 5:
            writer.close()
            return
            
        nmethods = header[1]
        await reader.readexactly(nmethods)
        
        # Отвечаем клиенту: Аутентификация не требуется
        writer.write(b'\x05\x00')
        await asyncio.sleep(0.01)
        await writer.drain()

        # 2. Читаем запрос CONNECT
        request = await reader.readexactly(4)
        if request[1] != 1: # 0x01 = CONNECT TCP
            writer.close()
            return

        atyp = request[3]
        if atyp == 1:  # IPv4
            address_bytes = await reader.readexactly(4)
            remote_host = socket.inet_ntoa(address_bytes)
        elif atyp == 3:  # Domain Name
            domain_len_bytes = await reader.readexactly(1)
            domain_len = domain_len_bytes[0]
            domain_bytes = await reader.readexactly(domain_len)
            remote_host = domain_bytes.decode('utf-8')
        else:
            writer.close()
            return

        await reader.readexactly(2) # Вычитываем порт из буфера, но игнорируем его

        # 3. ХИТРОСТЬ: Вместо заблокированных IP подключаемся к рабочему кроснету!
        # Этот вызов WARP беспрепятственно пропустит без ошибки "Отказано в доступе"
        try:
            logging.info(f"[+] Перехват сессии к {remote_host}. Перенаправляем трафик через {TARGET_GATEWAY}...")
            remote_reader, remote_writer = await asyncio.open_connection(TARGET_GATEWAY, TARGET_PORT)
            
            # Успешный ответ Telegram Desktop по спецификации SOCKS5
            writer.write(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
            await writer.drain()
        except Exception as e:
            logging.error(f"[-] Не удалось достучаться до шлюза {TARGET_GATEWAY} -> {e}")
            writer.write(b'\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00')
            await writer.drain()
            writer.close()
            return

        # 4. Запускаем параллельный транзит трафика
        await asyncio.gather(
            asyncio.create_task(pipe(reader, remote_writer)),
            asyncio.create_task(pipe(remote_reader, writer))
        )

    except Exception as e:
        logging.debug(f"Ошибка сессии: {e}")
    finally:
        writer.close()

async def main():
    server = await asyncio.start_server(handle_client, PROXY_HOST, PROXY_PORT)
    logging.info(f"[========================================================]")
    logging.info(f"[+] АСИНХРОННЫЙ PYTHON SMART-TUNNEL ЗАПУЩЕН!")
    logging.info(f"[*] Целевой рабочий шлюз транзита: {TARGET_GATEWAY}")
    logging.info(f"[*] Настройки для Telegram Desktop: {PROXY_HOST}:{PROXY_PORT}")
    logging.info(f"[========================================================]")
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Прокси остановлен.")
