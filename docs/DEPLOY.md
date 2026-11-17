# Выкладка SwarmLab (M9c)

Сервер: Ubuntu, `/opt/swarmlab`; сайт: `https://swarmlab.kmashinist.ru`.
Выкладка идёт из опубликованной ветки `master`. Коммиты и push делает Лео.
На ПК нужен PowerShell, Git и вход `ssh -o BatchMode=yes root@5.231.230.25` по ключу.
Пароли и ключи в репозиторий не кладут.

## Первый запуск

1. На ПК проверьте, что текущий `master` закоммичен и отправлен в GitHub:

   ```powershell
   git status --short
   git push origin master
   ```

2. На сервере убедитесь, что внешняя сеть `vaultwarden_default` и контейнер `caddy`
   существуют. Загрузите профиль AppArmor и дайте доступ к каталогу данных только UID 1000:

   ```powershell
   ssh root@5.231.230.25 'docker network inspect vaultwarden_default --format "{{.Name}}"; docker ps --format "{{.Names}}"'
   ssh root@5.231.230.25 'apparmor_parser -r /opt/swarmlab/docker/apparmor-swarmlab-sandbox'
   ```

   При самой первой выкладке файл профиля ещё не скопирован. Сначала выполните
   `git clone https://github.com/quatobyte/swarmlab.git /opt/swarmlab` на сервере,
   затем `apparmor_parser -r /opt/swarmlab/docker/apparmor-swarmlab-sandbox`.
   Для сохранения профиля после перезагрузки скопируйте его в `/etc/apparmor.d/`
   и загрузите оттуда. Проверки M9b проводились именно с этим профилем.

3. Запустите контейнер до добавления блока Caddy:

   ```powershell
   .\tools\deploy.ps1 -SkipHealth
   ```

   Скрипт обновляет только `/opt/swarmlab`, создаёт `deploy/.env` с правами 600,
   записывает адрес Caddy как доверенного прокси в `data/public.yaml`, собирает и
   запускает только сервис `swarmlab`. У приложения нет опубликованных портов.
   `docker compose ps` должен показать работающий контейнер.

4. Перед правкой Caddy сделайте копию на сервере:

   ```powershell
   ssh root@5.231.230.25 'cp -p /root/vaultwarden/Caddyfile /root/vaultwarden/Caddyfile.bak-$(date +%Y%m%d-%H%M%S)'
   ```

   Добавьте блок из `deploy/Caddyfile.snippet` в конец
   `/root/vaultwarden/Caddyfile` **записью в существующий файл** (`>>` или редактор
   с сохранением inode). Не заменяйте файл и не используйте `sed -i`: Caddy видит
   этот файл через bind mount. Сначала проверьте конфиг, затем перезагрузите:

   ```powershell
   ssh root@5.231.230.25 'docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile'
   ssh root@5.231.230.25 'docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile'
   .\tools\deploy.ps1
   ```

5. Создайте первого администратора. Пароль вводится интерактивно на сервере:

   ```powershell
   ssh -t root@5.231.230.25 'cd /opt/swarmlab/deploy && docker compose exec swarmlab swarmlab admin create-admin leo@example.com'
   ```

   Замените почту на свою. Затем войдите на сайт. Ссылка «Админка» в меню ведёт
   на `/admin`; пользователь без роли `admin` получит 403.

6. Установите ночной таймер на сервере:

   ```powershell
   ssh root@5.231.230.25 'cp /opt/swarmlab/deploy/swarmlab-backup.* /etc/systemd/system/; systemctl daemon-reload; systemctl enable --now swarmlab-backup.timer'
   ssh root@5.231.230.25 'systemctl list-timers swarmlab-backup.timer'
   ```

   Проверьте вручную: `systemctl start swarmlab-backup.service`. Архивы находятся
   в `/opt/swarmlab/backups`; скрипт хранит 7 последних.

## Обновление и проверка

```powershell
git push origin master       # выполняет Лео после своего коммита
.\tools\deploy.ps1
```

Скрипт сверяет SHA локального `master` и сервера, затем проверяет HTTP 200 через HTTPS.
До и после можно сравнить `docker ps --format '{{.Names}} {{.Status}}'`:
`caddy` и `amnezia-*` не должны перезапускаться. В браузере проверьте регистрацию,
матч через `wss://`, реплей, админку, консоль и серверные логи
(`docker compose logs --tail=100 swarmlab`). У сертификата проверьте срок действия.

## Бэкап и восстановление

```powershell
.\tools\deploy.ps1 -Backup -BackupDir .\backups
```

Копируется согласованная база через SQLite backup API и папка `users`. Для
восстановления остановите сервис, сохраните текущие данные отдельно и распакуйте
архив в **пустую** папку. Пример на сервере (архив уже в `/opt/swarmlab/backups`):

```powershell
ssh root@5.231.230.25 'cd /opt/swarmlab/deploy && docker compose stop swarmlab'
ssh root@5.231.230.25 'mv /opt/swarmlab/data /opt/swarmlab/data-before-restore && install -d -m 700 -o 1000 -g 1000 /opt/swarmlab/data'
ssh root@5.231.230.25 'cd /opt/swarmlab && python3 tools/backup.py restore backups/swarmlab-YYYYMMDD-HHMMSS.tar.gz data && chown -R 1000:1000 data'
ssh root@5.231.230.25 'cd /opt/swarmlab/deploy && docker compose up -d swarmlab'
```

После восстановления `data/public.yaml` надо снова создать доверенный прокси:
запустите `tools/deploy.ps1` с ПК. Не удаляйте `data-before-restore`, пока не
проверены вход, проекты и реплеи.

## Откат

Найдите предыдущий commit (`git log`) и сделайте в `/opt/swarmlab` checkout этого
SHA, затем `docker compose up -d --build` в `/opt/swarmlab/deploy`. Перед откатом
сделайте бэкап. Если предыдущая версия не понимает новую схему базы, восстановите
архив, сделанный до обновления, по инструкции выше. Откат не затрагивает Caddy
и `amnezia-*`.
