# Worker IA pour ext-guacamole-ai-session-review.
#
# Embarque :
#   - Python 3 + PyMySQL  → écriture vers MySQL Guacamole
#   - Node 24 + gemini-cli → appel LLM (auth OAuth via bind mount ~/.gemini)
#   - docker CLI          → invocation de l'image guacenc-extract sur l'hôte
#                           via /var/run/docker.sock partagé
#
# Tourne sous l'UID hôte (1000) ; les sorties (analysis.json, frames,
# locks) restent propriété du user hôte. Le groupe docker hôte est ajouté
# en runtime via `group_add:` dans docker-compose.yml.

FROM node:24-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pymysql \
        docker.io \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin sur la version testée côté hôte (gemini --version sur l'hôte = 0.42.0).
RUN npm install -g @google/gemini-cli@0.42.0 \
 && npm cache clean --force

# node:24-slim fournit déjà un user `node` en UID 1000. On le repointe
# vers HOME=/home/user pour que le bind mount /home/user/.gemini soit
# accessible sans réimplémenter l'utilisateur hôte.
RUN usermod -d /home/user -l worker node \
 && groupmod -n worker node \
 && mkdir -p /home/user \
 && chown 1000:1000 /home/user

WORKDIR /app
COPY worker.py /app/worker.py
RUN chown -R 1000:1000 /app

USER 1000

ENTRYPOINT ["python3", "/app/worker.py"]
CMD ["--watch"]
