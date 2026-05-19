# ext-guacamole-ai-session-review

> Extension d'audit intelligent pour Apache Guacamole : résumé automatique et détection de comportements suspects sur les sessions distantes enregistrées.

---

## Sommaire

- [Présentation](#présentation)
- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Convention pivot : `HISTORY_UUID`](#convention-pivot--history_uuid)
- [Modèle de données](#modèle-de-données)
- [Structure de l'extension](#structure-de-lextension)
- [API REST exposée](#api-rest-exposée)
- [Pipeline d'analyse IA](#pipeline-danalyse-ia)
- [Roadmap pédagogique](#roadmap-pédagogique)
- [Considérations RGPD & éthique](#considérations-rgpd--éthique)
- [Hors-périmètre (V1)](#hors-périmètre-v1)
- [Références](#références)

---

## Présentation

Apache Guacamole permet d'enregistrer les sessions distantes (RDP, SSH, VNC) sous forme de **dumps du protocole Guacamole**, rejouables dans le navigateur ou convertibles en MP4 via `guacenc`.

Ce projet ajoute une **couche d'audit intelligent** par-dessus ces enregistrements :

- un **worker IA externe** analyse les enregistrements terminés et produit un résumé textuel des actions observées ;
- une **extension Java Guacamole** expose ces analyses via une API REST et les affiche dans une interface réservée aux administrateurs ;
- chaque analyse est associée à la session source via le `HISTORY_UUID` natif de Guacamole.

L'objectif est **pédagogique** : démontrer une chaîne complète enregistrement → traitement IA → restitution sécurisée, sans modifier le code source de Guacamole.

---

## Architecture

```text
Guacamole
  ├── Extension Java (guacamole-ext)
  │   ├── UI admin : résumé IA / warning / niveau de risque
  │   ├── Endpoint REST sécurisé (UserContext)
  │   └── Association résumé ↔ session via HISTORY_UUID
  │
  ├── Stockage enregistrements
  │   └── recordings/${HISTORY_UUID}/...
  │
  ├── Worker IA (externe, Python)
  │   ├── Détection des nouvelles sessions terminées
  │   ├── Conversion via guacenc + ffmpeg
  │   ├── Extraction de frames
  │   ├── Analyse multimodale (résumé + détection)
  │   └── Écriture en base
  │
  └── Base PostgreSQL
      ├── session_ai_summary
      ├── suspicious_event
      └── analysis_status
```

**Règle de séparation des responsabilités :**

```text
Guacamole affiche et sécurise.
Le worker IA analyse.
La base de données fait le lien.
Le HISTORY_UUID est l'identifiant pivot.
```

---

## Stack technique

| Composant            | Choix                                  |
|----------------------|----------------------------------------|
| Guacamole            | 1.6.x                                  |
| Base de données      | PostgreSQL                             |
| Extension serveur    | Java + Maven (`guacamole-ext`)         |
| Worker d'analyse     | Python                                 |
| IA                   | Modèle multimodal (API ou local)       |
| Traitement vidéo     | `guacenc` + `ffmpeg`                   |
| UI                   | Extension Guacamole légère (AngularJS) |

---

## Convention pivot : `HISTORY_UUID`

Guacamole associe chaque enregistrement à une entrée d'historique via un identifiant interne unique. L'extension de playback recherche les fichiers/dossiers dont le nom correspond à cet UUID.

Organisation de stockage attendue :

```text
/var/lib/guacamole/recordings/
└── 8f8e0e9a-6c7e-4f12-b1e4-xxxx/
    ├── recording           # dump protocole Guacamole
    ├── recording.m4v       # vidéo générée par guacenc
    ├── frames/             # frames extraites pour l'IA
    └── analysis.json       # résultat brut de l'analyse
```

---

## Modèle de données

```sql
CREATE TABLE session_ai_summary (
    id              BIGSERIAL PRIMARY KEY,
    history_uuid    UUID        NOT NULL UNIQUE,
    username        VARCHAR(255),
    connection_name VARCHAR(255),
    started_at      TIMESTAMP,
    ended_at        TIMESTAMP,
    status          VARCHAR(50) NOT NULL,
    summary         TEXT,
    risk_level      VARCHAR(20),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE suspicious_event (
    id                  BIGSERIAL PRIMARY KEY,
    history_uuid        UUID NOT NULL,
    event_time_seconds  INTEGER,
    severity            VARCHAR(20),
    category            VARCHAR(100),
    description         TEXT,
    evidence            TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Structure de l'extension

```text
guacamole-ai-session-review/
├── pom.xml
├── src/main/java/edu/example/guacamole/ai/
│   ├── AiReviewAuthenticationProvider.java
│   ├── AiReviewUserContext.java
│   ├── rest/
│   │   └── AiReviewResource.java
│   ├── dao/
│   │   └── SessionAiSummaryDao.java
│   └── model/
│       ├── SessionAiSummary.java
│       └── SuspiciousEvent.java
└── src/main/resources/
    ├── guac-manifest.json
    ├── js/ai-review.js
    ├── css/ai-review.css
    └── html/ai-review.html
```

Manifest minimal :

```json
{
  "guacamoleVersion": "1.6.0",
  "name": "AI Session Review",
  "namespace": "ai-session-review",
  "authProviders": [
    "edu.example.guacamole.ai.AiReviewAuthenticationProvider"
  ],
  "js":   ["js/ai-review.js"],
  "css":  ["css/ai-review.css"],
  "html": ["html/ai-review.html"]
}
```

---

## API REST exposée

Les endpoints sont exposés au niveau `UserContext` → accessibles uniquement aux utilisateurs authentifiés.

```text
GET /guacamole/api/session/ext/ai-session-review/summaries
GET /guacamole/api/session/ext/ai-session-review/summaries/{historyUuid}
GET /guacamole/api/session/ext/ai-session-review/summaries/{historyUuid}/events
```

---

## Pipeline d'analyse IA

```text
1. Surveiller le dossier des recordings.
2. Détecter une nouvelle session terminée.
3. Récupérer le HISTORY_UUID.
4. Convertir l'enregistrement en vidéo via guacenc.
5. Extraire une image toutes les N secondes.
6. Envoyer les frames à un modèle multimodal.
7. Demander : résumé, actions observées, comportements suspects,
   niveau de risque, justification.
8. Stocker le résultat en base.
9. L'extension Guacamole affiche le résumé.
```

**Prompt cible :**

```text
Tu es un assistant d'analyse de sessions d'administration système.
Analyse les images extraites d'une session Apache Guacamole.

Objectifs :
1. Résumer ce que l'utilisateur semble avoir fait.
2. Identifier les actions techniques visibles.
3. Détecter les comportements potentiellement suspects.
4. Classer le risque : faible, moyen, élevé.
5. Ne jamais inventer une action non visible.
6. Formuler les conclusions comme des hypothèses si l'image est ambiguë.

Réponds en JSON :
{
  "summary": "...",
  "risk_level": "low|medium|high",
  "observed_actions": [],
  "suspicious_events": [
    {
      "timecode": "00:03:12",
      "severity": "medium",
      "category": "sensitive_file_access",
      "description": "...",
      "confidence": 0.72
    }
  ],
  "limitations": "..."
}
```

**Exemples de règles suspectes :**

- ouverture d'un terminal administrateur ;
- commandes de suppression massive (`rm -rf`, `del /s`, `format`) ;
- consultation de fichiers sensibles (`/etc/shadow`, `id_rsa`, `.env`) ;
- désactivation de mécanismes de sécurité (firewall, antivirus, auditd) ;
- exfiltration apparente (`scp`, `curl`, `wget` vers domaine externe) ;
- création d'un nouvel utilisateur administrateur.

---

## Roadmap pédagogique

| Lot | Objectif                  | Livrable                                              |
|-----|---------------------------|-------------------------------------------------------|
| 1   | Socle Guacamole           | Session enregistrée visible dans l'historique         |
| 2   | Worker IA minimal         | Table `session_ai_summary` remplie automatiquement    |
| 3   | Extension REST            | Endpoint `/api/session/ext/ai-session-review/...`     |
| 4   | Interface admin           | Écran listant les sessions analysées + badges         |
| 5   | Amélioration sécurité     | Règles avancées, score de confiance, validation humaine |

---

## Considérations RGPD & éthique

À respecter dès le cadrage :

- information claire des utilisateurs ;
- finalité explicite : audit pédagogique / sécurité ;
- durée de conservation limitée ;
- accès réservé aux administrateurs habilités ;
- traçabilité de la consultation des résumés ;
- pas d'analyse automatisée punitive sans validation humaine ;
- bannière indiquant que les sessions peuvent être enregistrées et analysées.

**Formulation des warnings dans l'UI :**

```text
[OK]   Comportement suspect détecté automatiquement.
       Analyse à valider par un administrateur.

[KO]   L'utilisateur a commis une action malveillante.
```

---

## Hors-périmètre (V1)

- modifier directement le code source de Guacamole ;
- faire tourner l'IA dans l'extension Java ;
- analyser la vidéo en temps réel ;
- prétendre détecter toutes les actions précisément ;
- affirmer une intention malveillante ;
- afficher les warnings aux utilisateurs finaux.

---

## Références

- [Viewing session recordings in-browser — Apache Guacamole Manual v1.6.0](https://guacamole.apache.org/doc/gug/recording-playback.html)
- [guacamole-ext — Apache Guacamole Manual v1.5.4](https://guacamole.apache.org/doc/1.5.4/gug/guacamole-ext.html)
- [Guacamole's administrative interface — Apache Guacamole Manual v1.6.0](https://guacamole.apache.org/doc/gug/administration.html)
