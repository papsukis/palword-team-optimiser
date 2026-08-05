# Déploiement sur le serveur (Rocky Linux 10)

Guide pour déployer `palworld_team_optimizer` sur ton serveur Rocky Linux 10.2,
avec PostgreSQL déjà installé, exposé publiquement sur **palword.technomind.ma**
via nginx + HTTPS (Let's Encrypt).

Toutes les commandes ci-dessous sont à exécuter **en SSH sur le serveur**, pas sur
ta machine locale.

## 1. Copier le projet sur le serveur

Depuis ta machine Windows (PowerShell), en supposant que ton user SSH est `ali` :

```bash
scp -r C:\Users\alibe\Documents\palword\palworld_team_optimizer ali@<IP_SERVEUR>:~/
```

(ou via `git push`/`git clone` si tu préfères passer par un dépôt distant.)

## 2. Paquets système (dnf)

```bash
sudo dnf install -y python3 python3-pip nginx
python3 --version   # doit être >= 3.10
```

## 3. Base PostgreSQL dédiée

PostgreSQL est déjà installé. On crée un rôle et une base dédiés à l'app :

```bash
sudo -u postgres psql
```

Dans le prompt `psql` :

```sql
CREATE ROLE palworld_optimizer WITH LOGIN PASSWORD 'CHANGE_MOI';
CREATE DATABASE palworld_optimizer OWNER palworld_optimizer;
\q
```

Choisis un vrai mot de passe fort à la place de `CHANGE_MOI`.

Vérifie que la connexion en TCP local avec mot de passe est autorisée. Ouvre
`pg_hba.conf` (chemin typique : `/var/lib/pgsql/data/pg_hba.conf` ou
`/var/opt/rh/.../data/pg_hba.conf` selon la version installée) et assure-toi
qu'il existe une ligne du type :

```
host    palworld_optimizer    palworld_optimizer    127.0.0.1/32    scram-sha-256
```

Si tu dois l'ajouter, recharge Postgres ensuite :

```bash
sudo systemctl reload postgresql
```

## 4. Environnement Python de l'app

```bash
cd ~/palworld_team_optimizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Configuration `.env`

```bash
cp .env.example .env
```

Édite `.env` :

```
DATABASE_URL=postgresql://palworld_optimizer:CHANGE_MOI@127.0.0.1:5432/palworld_optimizer
```

## 6. Charger les données dans Postgres

```bash
python migrate.py
```

Tu dois voir 7 lignes `Loaded N rows into '...'`.

## 7. Service systemd (lance l'app en arrière-plan, redémarre au boot)

Crée `/etc/systemd/system/palworld-optimizer.service` :

```ini
[Unit]
Description=Palworld Team Optimizer (Streamlit)
After=network.target postgresql.service

[Service]
Type=simple
User=ali
WorkingDirectory=/home/ali/palworld_team_optimizer
EnvironmentFile=/home/ali/palworld_team_optimizer/.env
ExecStart=/home/ali/palworld_team_optimizer/.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Adapte `User=` et les chemins si ton utilisateur SSH n'est pas `ali`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now palworld-optimizer
sudo systemctl status palworld-optimizer
```

L'app écoute uniquement sur `127.0.0.1:8501` — elle n'est pas exposée
directement à internet, seul nginx (étape suivante) doit y accéder.

## 8. Reverse proxy nginx

Crée `/etc/nginx/conf.d/palworld.conf` :

```nginx
server {
    listen 80;
    server_name palword.technomind.ma;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Les en-têtes `Upgrade`/`Connection` sont indispensables : Streamlit utilise des
WebSockets pour ses mises à jour en direct.

```bash
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

## 9. SELinux

Rocky Linux applique SELinux en mode enforcing par défaut. Sans ce réglage,
nginx renverra une erreur 502 en essayant de proxifier vers l'app :

```bash
sudo setsebool -P httpd_can_network_connect on
```

Si tu vois quand même des 502, regarde les refus SELinux avec :

```bash
sudo ausearch -m avc -ts recent
```

## 10. Pare-feu (firewalld)

Ouvre seulement HTTP/HTTPS publiquement — jamais le port 8501 :

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 11. HTTPS avec Let's Encrypt

```bash
sudo dnf install -y epel-release
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d palword.technomind.ma
```

Certbot édite automatiquement la config nginx pour ajouter le certificat et
la redirection HTTP → HTTPS, et installe un timer de renouvellement
automatique. Vérifie-le avec :

```bash
sudo certbot renew --dry-run
```

## 12. Vérification finale

```bash
curl -I https://palword.technomind.ma
```

Puis ouvre `https://palword.technomind.ma` dans un navigateur : les 3 onglets
(Team Builder, Element Candidates, Reference Data) doivent fonctionner.

## Mettre à jour l'app plus tard

```bash
cd ~/palworld_team_optimizer
# récupère les nouveaux fichiers (git pull, ou re-scp)
source .venv/bin/activate
pip install -r requirements.txt
python migrate.py            # seulement si les CSV dans data/ ont changé
sudo systemctl restart palworld-optimizer
```

## Logs / débogage

```bash
sudo journalctl -u palworld-optimizer -f    # logs de l'app Streamlit
sudo tail -f /var/log/nginx/error.log       # logs nginx
```
