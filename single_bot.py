import atexit
import fcntl
import os
import signal
import sys


class SingletonBot:
    def __init__(self, lock_file_path='bot.lock'):
        self.lock_file_path = lock_file_path
        self.lock_file = None

    def __enter__(self):
        """Блокування при вході в контекст"""
        try:
            self.lock_file = open(self.lock_file_path, 'w')
            # Неблокуючий ексклюзивний лок
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Записуємо PID поточного процесу
            self.lock_file.write(str(os.getpid()))
            self.lock_file.flush()

            # Реєструємо очищення при завершенні
            atexit.register(self.cleanup)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

            return self
        except (IOError, OSError):
            if self.lock_file:
                self.lock_file.close()
            print("❌ Бот вже запущений! Неможливо запустити другу копію.")
            sys.exit(1)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Розблокування при виході з контексту"""
        self.cleanup()

    def cleanup(self):
        """Очищення lock-файлу"""
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                # Видаляємо файл блокування
                if os.path.exists(self.lock_file_path):
                    os.unlink(self.lock_file_path)
            except:
                pass

    def _signal_handler(self, signum, frame):
        """Обробник сигналів для коректного завершення"""
        print(f"\n🛑 Отримано сигнал {signum}. Завершуємо роботу бота...")
        self.cleanup()
        sys.exit(0)
