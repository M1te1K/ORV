# ORVI Simulator для macOS

Фоновая версия ORVI для macOS. Программа воспроизводит звуки и случайно открывает
приложения, двигает окна, меняет громкость и показывает красный оверлей. Эффекты
выполняются каждые 3–7 секунд. Код пока не проверен вручную на разных версиях macOS.

Используйте программу только на своём Mac или с явного согласия его владельца.

## Готовое приложение

Распакуйте [`../releases/ORVISimulator-macOS-universal2.zip`](../releases/ORVISimulator-macOS-universal2.zip),
переместите `ORVISimulatorMac.app` в постоянное место (например, `~/Applications`)
**до первого запуска**, затем откройте его. Архив содержит сборку для Apple Silicon
и Intel. Приложение работает без значка в Dock; процесс виден в «Мониторинге системы».

Сборка подписана локальной подписью PyInstaller, но не нотарифицирована Apple.
При первом запуске macOS может запросить подтверждение открытия. Не выдавайте
разрешения приложению, если не доверяете полученному архиву.

## Запуск из исходников

Нужен Python 3 с Tkinter. Проверьте `python3 -c "import tkinter"`, затем:

```bash
cd mac
python3 orvi_mac.py
```

Можно также открыть `Start_ORVI.command` после `chmod +x mac/*.command`.
Этот способ открывает окно Terminal.

## Автозапуск

При обычном первом запуске скрипт создаёт **пользовательский LaunchAgent**
`~/Library/LaunchAgents/com.orvi.simulator.plist`. Он запускает программу при
следующем входе именно этого пользователя в графический сеанс. Пароль и права
администратора не требуются. В `ProgramArguments` хранится полный путь к текущему
интерпретатору и скрипту или к исполняемому файлу внутри `.app`. Поэтому после
перемещения программы запустите её снова, чтобы обновить путь агента.

`RunAtLoad` запускает агент и при регистрации. Второй экземпляр сразу завершится
из-за файловой блокировки. Принудительного перезапуска после остановки нет.

Посмотреть агент:

```bash
launchctl print "gui/$(id -u)/com.orvi.simulator"
plutil -p "$HOME/Library/LaunchAgents/com.orvi.simulator.plist"
```

Чтобы **отключить автозапуск и остановить экземпляр, запущенный агентом**:

```bash
python3 mac/orvi_mac.py --uninstall
```

Для готового приложения вместо команды выше используйте:

```bash
"$HOME/Applications/ORVISimulatorMac.app/Contents/MacOS/ORVISimulatorMac" --uninstall
```

Путь к `.app` замените на фактический. Файлы программы команда не удаляет.
Повторный обычный запуск снова включит автозапуск.

## Остановка текущего процесса

`Stop_ORVI.command` создаёт стоп-файл. Работающий процесс замечает его и
завершается после текущего эффекта. Из Terminal то же действие:

```bash
mkdir -p "$HOME/Library/Application Support/ORVISimulator"
touch "$HOME/Library/Application Support/ORVISimulator/orvi.stop"
```

Это не отключает автозапуск: при следующем входе программа запустится снова.
Оставшийся после остановки без работающего процесса стоп-файл очищается при запуске.

## Разрешения и ограничения

Для дрожания окон потребуется разрешение **Accessibility** для запускающего
приложения или Python и, возможно, разрешение **Automation** для System Events.
Их выдаёт пользователь в System Settings → Privacy & Security. Без этих разрешений
движение окон не работает; ошибки этого эффекта сейчас подавляются. На некоторых
Mac команда открытия «Accessibility Keyboard» может не найти приложение.

Оверлей Tkinter и взаимодействие с рабочим столом требуют графического входа.
LaunchDaemon для запуска до входа пользователя здесь не подходит.

## Сборка приложения

На macOS с universal2 Python 3, Tkinter и PyInstaller:

```bash
python3 -m pip install pyinstaller==6.16.0
python3 -m PyInstaller --clean --noconfirm ORVISimulatorMac.spec
```

Готовый пакет появится в `dist/ORVISimulatorMac.app`. Для архива репозитория:

```bash
mkdir -p releases
ditto -c -k --sequesterRsrc --keepParent dist/ORVISimulatorMac.app \
  releases/ORVISimulator-macOS-universal2.zip
```

PyInstaller собирает приложение только для платформы, на которой запущен.
Windows `.exe` нужно собирать на Windows.
