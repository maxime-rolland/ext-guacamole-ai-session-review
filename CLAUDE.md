# CLAUDE.md — ext-guacamole-ai-session-review

Contexte de travail destiné à Claude Code pour le développement et le test de l'extension d'audit IA pour Apache Guacamole.

> Lire d'abord [README.md](README.md) pour la vision produit (architecture, modèle de données, API REST, pipeline IA, RGPD). Ce fichier-ci décrit **comment développer et tester l'extension contre la maquette locale**.

---

## 1. Vue d'ensemble du dépôt

- **Ce dépôt** (`/home/user/ext-guacamole-ai-session-review/`) contient **uniquement** l'extension Java Guacamole. Il sera structuré selon l'arborescence donnée dans le README (section *Structure de l'extension*) : `pom.xml`, `src/main/java/edu/example/guacamole/ai/...`, ressources statiques + `guac-manifest.json`.
- La maquette de test (docker-compose, base, enregistrements, outils auxiliaires) vit **un niveau au-dessus**, dans `/home/user/`. Le développement de l'extension ne doit **pas** dupliquer ces fichiers à l'intérieur du dépôt — on consomme la maquette parente comme environnement.

```text
/home/user/                          ← maquette (hors dépôt extension)
├── docker-compose.yml               ← stack Guacamole 1.6 + MySQL 8
├── initdb.sql                       ← schéma + bootstrap JDBC officiel
├── records/                         ← enregistrements montés dans guacd ET guacamole
│   └── <HISTORY_UUID>/recording     ← dump protocole Guacamole d'une session
├── db/                              ← volume persistant MySQL (NE PAS toucher à la main)
├── guacenc-docker/                  ← image `guacenc-extract` : protocole → .m4v + frames
├── guac-agent/                      ← prototype worker (cron-tick.sh + analyze-one.sh, Gemini CLI)
└── ext-guacamole-ai-session-review/ ← CE DÉPÔT (extension Java)
```

---

## 2. État de la maquette

La pile tourne déjà (vérifier avec `docker ps`). Services attendus :

| Conteneur          | Image                      | Rôle                                    | Exposition           |
|--------------------|----------------------------|-----------------------------------------|----------------------|
| `user-guacd-1`     | `guacamole/guacd`          | Backend protocoles (RDP/SSH/VNC)        | interne `4822`       |
| `user-guacamole-1` | `guacamole/guacamole`      | Webapp Tomcat + extensions              | `localhost:8080`     |
| `user-db-1`        | `mysql:8.0`                | Stockage Guacamole (auth-jdbc)          | interne `3306`       |

UI : <http://localhost:8080/guacamole/>

**Extensions déjà chargées dans l'image officielle** (à connaître pour éviter les collisions de namespace) : `guacamole-auth-jdbc`, `guacamole-history-recording-storage`, `guacamole-auth-totp`, `guacamole-auth-ldap`, `guacamole-auth-json`, `guacamole-auth-ban`, `guacamole-auth-quickconnect`, `guacamole-display-statistics`, etc. Notre namespace `ai-session-review` est libre.

`GUACAMOLE_HOME` est généré dynamiquement au démarrage du conteneur dans `/tmp/guacamole-home.XXXX/` — **ne pas y écrire à la main**, ça disparaît au redémarrage. Pour injecter notre `.jar`, on passe par un bind mount (voir §5).

---

## 3. Décisions actées (la maquette fait foi)

Choix arrêtés avec le user — ne pas y revenir sans demande explicite :

1. **Base de données = MySQL 8** (et **non** PostgreSQL comme indiqué dans le README). Le `README.md` est en cours et sera réaligné ; en cas de doute, **la maquette `/home/user/docker-compose.yml` fait référence**. Concrètement :
   - les tables `session_ai_summary` et `suspicious_event` sont créées dans la base `guacamoledb` (à côté des tables `guacamole_*` de l'auth-jdbc) ;
   - le schéma SQL du README doit être adapté à MySQL (`BIGSERIAL` → `BIGINT AUTO_INCREMENT`, `UUID` → `CHAR(36)` ou `BINARY(16)`, `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` reste OK) ;
   - DAO de l'extension : réutiliser le `DataSource` JNDI de l'auth-jdbc si possible, sinon configurer une connexion MySQL séparée pointant sur le même service `db`.
2. **`guac-agent/` + `guacenc-docker/` = maquette de faisabilité validée.** La chaîne `guacenc → frames → LLM → rapport Markdown` est éprouvée sur 4 sessions réelles. Le passage à la V2 (worker Python qui écrit en base au lieu d'un `report.md`) **reprend** :
   - l'image Docker `guacenc-extract` telle quelle ;
   - le mécanisme de scan + verrou de `cron-tick.sh` ;
   - le prompt d'`analyze-one.sh` (à porter du Markdown vers le JSON spécifié au README §pipeline) ;
   - la stratégie de dédup/sous-échantillonnage des frames.
   Ne pas réinventer ces briques.
3. **Version Guacamole = 1.6.x.** `guac-manifest.json` déclare `guacamoleVersion: 1.6.0`. Le `guacenc` de `guacenc-docker/` est figé sur **1.5.5** côté `ARG GUAC_VERSION` — c'est volontaire (le rendu vidéo reste compatible avec les dumps 1.6) et il n'y a pas lieu de l'aligner sans raison.

---

## 4. Convention pivot `HISTORY_UUID`

C'est l'identifiant qui relie **trois mondes** :

```text
records/<HISTORY_UUID>/recording    ← fichier dump créé par guacd
guacamole_connection_history.uuid   ← colonne en base (auth-jdbc)
session_ai_summary.history_uuid     ← clé d'association côté extension
```

Tout endpoint REST de l'extension qui reçoit un `historyUuid` doit :
- valider le format UUID,
- vérifier que l'utilisateur courant a le droit de voir cet historique (via `UserContext`),
- ne jamais faire confiance au chemin disque construit à partir de l'UUID sans normalisation (path traversal).

Exemples de sessions déjà enregistrées dans `/home/user/records/` (utilisables pour tests offline) :
- `3c1501f5-df64-31df-a140-a7b68cb7aad3`
- `52871880-4953-3c46-9b3a-a2ed9b9cbc89`
- `8063df49-c55f-347b-802d-0c1168c0c119`
- `9d4f66ae-b0e6-3d87-a074-e8c04320c961`

Chacune contient déjà `recording`, `recording.m4v`, `recording.frames/`, et un `report.md` produit par `guac-agent`.

---

## 5. Boucle de développement extension Java

L'image officielle charge automatiquement tout `.jar` présent dans `GUACAMOLE_HOME/extensions/`. Comme `GUACAMOLE_HOME` est éphémère, on monte notre dossier `extensions/` **par-dessus** via docker-compose. Avant la première itération, ajouter au service `guacamole` du `docker-compose.yml` parent :

```yaml
    environment:
      GUACAMOLE_HOME: /etc/guacamole         # fige le chemin (sinon il est aléatoire)
    volumes:
      - ./ext-guacamole-ai-session-review/target/extensions:/etc/guacamole/extensions:ro
      - ./records:/var/lib/guacamole/recordings
```

(On peut aussi monter un seul `.jar` directement dans `extensions/`. Le mount d'un dossier `target/extensions` est plus pratique pour itérer avec `mvn package`.)

**Maven n'est pas installé sur l'hôte** ; on construit dans un conteneur, en cachant le repo Maven local sur `/home/user/.m2` pour itérer rapidement, et avec `-u` pour ne pas écrire de fichiers root dans `target/`.

```bash
cd /home/user/ext-guacamole-ai-session-review

# Build dans un conteneur Maven (cache .m2 sur l'hôte, ownership host user)
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v /home/user/.m2:/var/maven/.m2 \
    -e MAVEN_CONFIG=/var/maven/.m2 \
    -v "$PWD:/work" -w /work \
    maven:3.9-eclipse-temurin-17 \
    mvn -B -ntp -Duser.home=/var/maven package

# Stager le JAR pour le bind mount
mkdir -p target/extensions
cp target/guacamole-ai-session-review-*.jar target/extensions/

# Recharger l'extension (Guacamole ne fait pas de hot reload)
docker compose up -d guacamole       # ou: docker restart user-guacamole-1
docker logs --tail=80 user-guacamole-1 | grep -iE "ai-session-review|extension|error"
```

**À l'exécution, ce qui se passe vraiment** : l'entrypoint de l'image officielle régénère un `GUACAMOLE_HOME` éphémère dans `/tmp/guacamole-home.XXXX/` **même quand on positionne `GUACAMOLE_HOME=/etc/guacamole`**. Mais il **copie** les JAR trouvés dans `/etc/guacamole/extensions/` vers ce home temporaire. Notre bind mount sur `/etc/guacamole/extensions:ro` est donc bien la bonne approche, indépendamment de la valeur de `GUACAMOLE_HOME`. On garde la variable par sécurité, mais elle n'est pas strictement requise.

À l'issue du chargement, on doit voir dans les logs :

```
ExtensionModule - Extension "AI Session Review" (ai-session-review) loaded.
```

Pour tester un endpoint REST authentifié (le token vient de `/api/tokens`) :

```bash
TOKEN=$(curl -s -X POST -d 'username=guacadmin&password=guacadmin' \
        http://localhost:8080/guacamole/api/tokens | jq -r .authToken)
curl -s "http://localhost:8080/guacamole/api/session/ext/ai-session-review/summaries?token=$TOKEN" | jq .
```

L'identifiant `guacadmin/guacadmin` est celui par défaut **uniquement** si `initdb.sql` a été appliqué à la base ; sinon vérifier ce que le user a configuré.

---

## 6. Inspecter la base Guacamole

```bash
docker exec -it user-db-1 mysql -uuser -pAzerty01 guacamoledb
# tables utiles : guacamole_user, guacamole_connection, guacamole_connection_history
SELECT uuid, username, connection_name, start_date, end_date
FROM guacamole_connection_history
ORDER BY start_date DESC LIMIT 10;
```

La colonne `uuid` correspond au sous-dossier de `records/`. C'est le point de jonction avec `session_ai_summary.history_uuid`.

Les tables `session_ai_summary` et `suspicious_event` vivent dans la même base `guacamoledb` (cf. §3). Versionner leur schéma dans `db/migrations/` **de ce dépôt** (et pas dans `/home/user/db/` qui est le volume MySQL et ne doit pas être édité à la main).

---

## 7ter. UI AngularJS (lot 4) — patches HTML + JS via /app.js

Lot 4 ajoute un item dans le menu utilisateur (haut-droite) et une modale qui liste les sessions analysées + détails par session. Pas de nouvelle route, pas de nouveau module Angular : on greffe sur l'existant via le modèle de patches HTML de Guacamole 1.6.

**Modèle de chargement Guacamole 1.6** (vérifié empiriquement, pas dans la doc officielle) :
- `manifest.js[]`        → concaténé dans `GET /guacamole/app.js`        (servi après les bundles webpack)
- `manifest.css[]`       → concaténé dans `GET /guacamole/app.css`       (lien `<link>` dans index.html)
- `manifest.html[]`      → exposé via `GET /guacamole/api/patches`        (chaque fichier = un patch indépendant)
- `manifest.translations[]` → fusionné dans `GET /guacamole/translations/<lang>.json` (auto via `api/languages`)

**Mécanisme des patches HTML** (cf. `app/index/config/templateRequestDecorator.js` de la webapp) :
- Chaque patch commence par un `<meta name="OPERATION" content="CSS_SELECTOR">`.
- Opérations supportées : `before`, `after`, `replace`, `before-children`, `after-children`, `replace-children`.
- Le patch est appliqué à **tous les templates AngularJS chargés via `$templateRequest`**. Les sélecteurs qui ne matchent dans aucun template sont silencieusement ignorés.
- ⚠️ `body`, `html`, `head` et tout sélecteur visant `index.html` **ne fonctionnent pas** : `index.html` n'est pas chargé via `$templateRequest`. Cibler un template de directive (ex. `guacUserMenu.html` via `.user-menu`).
- ⚠️ Un template de directive AngularJS doit avoir **exactement une racine** (sinon `$compile:tplrt`). Conséquence : `after`/`before` sur l'élément racine du template casse le directive. Sur `guacUserMenu.html`, dont la racine est `<div class="user-menu">`, **toujours patcher en `*-children`** (`after-children .user-menu`) plutôt qu'en sibling. Idem pour les commentaires HTML hors meta — ils comptent comme des nœuds frères de la racine. Garder les fichiers patches minimaux : meta + fragment, c'est tout.

**Composants UI livrés :**

| Fichier | Rôle |
|---|---|
| `js/ai-review.js` | Récupère l'`$injector` Angular, expose `$rootScope.aiReview` (state + open/close/select/deselect), appelle `requestService` pour `api/session/ext/ai-session-review/...`. Le token Guacamole est injecté automatiquement par `requestService`. Pattern : pas de `angular.module().run()` car la webapp est déjà bootstrappée — on récupère l'injector et on assigne sur `$rootScope`, puis `$apply()`. |
| `css/ai-review.css` | Overlay fixed, modale, badges de risque (low=vert, medium=orange, high=rouge, unknown=gris), tableau scrollable. |
| `html/menu-item.html` | Patch `after-children` sur `.user-menu .action-list:last-of-type` : ajoute un `<li>` avec `ng-click="$root.aiReview.open()"`. Gardé par `ng-if="$root.aiReview"` pour ne pas casser si le JS n'a pas encore tourné. |
| `html/modal.html` | Patch `after` sur `.user-menu` : greffe la modale comme sibling DOM. `position:fixed` la fait flotter peu importe le parent. Liste tabulée des `summaries` + drill-down vers `events`. |
| `translations/fr.json`, `translations/en.json` | Clés `AI_REVIEW.*` fusionnées dans les traductions Guacamole (auto). |

**Comment tester en navigateur :**

1. Hard refresh sur <http://localhost:8080/guacamole/> (Ctrl+Shift+R) — pour purger le cache des bundles.
2. Login (`guacadmin` / `guacadmin`).
3. Cliquer sur le username (haut-droite) → menu déroulant, item « Revue IA des sessions » sous Logout.
4. Click → modale avec la liste des 4 sessions, badge de risque coloré.
5. Click sur une ligne → vue détail avec résumé + (éventuels) events suspects, bouton « Retour à la liste ».
6. Click sur le fond gris ou la croix → ferme.

**Si le menu item n'apparaît pas :**
- Vider le cache navigateur (les bundles JS/CSS sont cachés agressivement).
- Vérifier dans DevTools que `/app.js` contient `aiReview` et que `/api/patches` retourne nos 2 patches.
- Console : taper `angular.element(document.body).scope().$root.aiReview` → doit retourner l'objet state, pas `undefined`.

**Limites connues du lot 4 :**

- Pas de filtre / tri / pagination sur la liste (ok pour le pédagogique sur < 100 sessions, à revoir si on monte en charge).
- Auto-refresh : la modale ne se rafraîchit pas automatiquement après ouverture. Refermer / rouvrir pour recharger.
- Visibilité non restreinte aux admins (cf. [README.md](README.md) §RGPD : « accès réservé aux administrateurs habilités »). Le contrôle se fera côté serveur dans le lot 5.

## 7bis. Worker Python — implémenté dans `worker/`

Le lot 2 est en place. Le worker est un service docker-compose, image construite depuis `worker/Dockerfile` (Node 24 + Python + docker CLI + gemini-cli 0.42.0).

**Architecture :**

```text
[host /home/user/records/] ──┐
                             │ bind mount
                             ▼
┌─ container `worker` (uid 1000, gid docker) ─┐
│  worker.py                                  │
│    1. scan RECORDS_DIR pour UUID-like dirs  │
│    2. flock par session                     │
│    3. INSERT analyzing, mtime/ctime         │
│    4. docker run guacenc-extract (DinD)     │
│    5. dédup MD5 + échantillon MAX_FRAMES    │
│    6. gemini -p ... → analysis.json + JSON  │
│    7. UPDATE done + INSERT suspicious_event │
└─────────────────────────────────────────────┘
    │ pymysql                  │ docker.sock
    ▼                          ▼
[user-db-1 MySQL]      [host dockerd → guacenc-extract]
```

**Points-clés :**

- **Container, pas host + cron** (décision du user) : `restart: always` + `--watch` dans le compose. Pour un balayage one-shot : `docker compose run --rm worker --once`.
- **UID 1000 dans le container** (le user `node` de l'image renommé en `worker`, HOME=/home/user). Toutes les sorties (`analysis.json`, frames, locks) restent propriété du user hôte.
- **Docker socket monté** pour que le worker puisse lancer `guacenc-extract`. `group_add: 989` ajoute le GID `docker` hôte au container.
- **OAuth Gemini partagé** via `/home/user/.gemini` bind-monté. Pas de clé API à configurer ; on réutilise l'auth interactive faite sur l'hôte.
- **Idempotence** :
  - status `done` en base → skip ;
  - status `analyzing` → retry (un précédent run a planté avant `save_result`) ;
  - `frames/` déjà peuplé → on saute `guacenc-extract`.
- **Prompt** : adapté de `guac-agent/analyze-one.sh`, demande du JSON pur conforme à [README.md §Pipeline d'analyse IA](README.md). Réponse parsée et insérée dans `session_ai_summary` + `suspicious_event`. `analysis.json` brut conservé à côté du `recording` (cf. [README.md §Convention pivot](README.md)).
- **DB** : `127.0.0.1:3306` publié sur l'hôte (loopback uniquement) pour le debug avec `mysql` client ; le worker passe par le réseau Docker (`DB_HOST=db`).

**Limites connues (à cracker plus tard) :**

- `username` / `connection_name` restent `NULL`. La dérivation `<UUID dossier dans records/>` ↔ `guacamole_connection_history.history_id` n'est pas évidente : ni `UUID.nameUUIDFromBytes(history_id)`, ni `nameUUIDFromBytes(startDate \0 history_id)` ne donnent les UUID observés sur disque. Le mapping est à trouver dans le code de `guacamole-history-recording-storage` (extension officielle). En attendant, le worker remplit `started_at`/`ended_at` depuis le `mtime`/`ctime` du dossier — approximatif mais utilisable.
- Le LLM peut occasionnellement enrober son JSON de balises markdown malgré la consigne. `parse_llm_output` extrait alors entre la première `{` et la dernière `}` ; on a vu des cas où c'est insuffisant. Mettre `analysis.json` sous les yeux pour debug.

**Commandes utiles :**

```bash
docker compose build worker                     # rebuild après modif worker.py
docker compose up -d worker                     # mode --watch
docker compose run --rm worker --once -v        # un balayage, verbose
docker logs -f user-worker-1                    # surveiller le service

# Forcer la réanalyse d'une session
docker exec user-db-1 mysql -uuser -pAzerty01 -D guacamoledb \
    -e "DELETE FROM session_ai_summary WHERE history_uuid='<UUID>';"
```

## 7. Maquette de faisabilité — pour mémoire

`/home/user/guac-agent/` + `/home/user/guacenc-docker/` constituent une **maquette de faisabilité validée** de la chaîne d'analyse. Elle tourne en local et a produit les `report.md` présents dans les 4 sessions de `records/`. Elle prouve que :

- `guacenc` + `ffmpeg` extraient correctement des frames exploitables depuis un dump protocole 1.6 ;
- un LLM multimodal (Gemini CLI ici) produit un compte rendu structuré utile à partir de ~12 frames échantillonnées ;
- la détection « session terminée » par `find -mmin -1` + verrou par dossier suffit à éviter les analyses concurrentes.

La V2 conforme au README (worker Python écrivant en base) **doit reprendre** ces briques telles quelles :

- image Docker `guacenc-extract` → identique ;
- algorithme de scan/verrou de `cron-tick.sh` → identique (ou équivalent Python) ;
- prompt d'`analyze-one.sh` → à porter en sortie JSON pour alimenter `session_ai_summary` + `suspicious_event` (le squelette du prompt reste pertinent) ;
- stratégie dédup MD5 + sous-échantillonnage `MAX_FRAMES` → identique.

Règle de séparation du README à respecter : **l'extension Java ne lance pas l'IA**. Elle lit en base ce que le worker a écrit. Le worker tourne hors du conteneur Guacamole.

---

## 8. Règles de collaboration

- **Ne pas modifier** `db/` (volume MySQL persistant) ni `records/` (enregistrements de référence pour les tests) sans demander.
- **Ne pas relancer** `docker compose down -v` : ça reset la base Guacamole, les connexions configurées et le compte admin.
- **Ne pas committer** de credentials ; le mot de passe MySQL `Azerty01` est de maquette, mais on ne le copie pas dans la doc publique du dépôt.
- **`guac-manifest.json` est sensible** : une erreur de syntaxe rend l'extension silencieusement invisible. Toujours vérifier `docker logs user-guacamole-1` après un changement de manifest.
- Pour toute action destructive (drop table, suppression d'un volume, rebuild d'image), demander confirmation.
- Tests UI : ouvrir <http://localhost:8080/guacamole/> dans le navigateur et confirmer visuellement avant de déclarer un lot fini ; la compilation Maven ne valide pas le rendu AngularJS.

---

## 9. Commandes de diagnostic rapide

```bash
docker ps                                                   # services up ?
docker logs --tail=120 user-guacamole-1                     # erreurs de chargement d'extension
docker exec user-guacamole-1 ls /tmp/guacamole-home.*/extensions/   # JARs effectivement chargés
ls /home/user/records/                                      # sessions disponibles
docker exec user-db-1 mysql -uuser -pAzerty01 -e \
  'SELECT COUNT(*) FROM guacamoledb.guacamole_connection_history;'
```
