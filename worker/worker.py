#!/usr/bin/env python3
"""Worker IA minimal pour ext-guacamole-ai-session-review.

Scanne le dossier des enregistrements Guacamole, déclenche l'extraction
de frames (image Docker `guacenc-extract`, écrite côté maquette), envoie
un échantillon à Gemini, et persiste le résultat dans la base
`guacamoledb` (tables `session_ai_summary` + `suspicious_event`).

Usage :
    python3 worker.py --once       # un balayage puis sortie (mode cron)
    python3 worker.py --watch      # boucle infinie, sleep INTERVAL_S entre balayages

Variables d'environnement :
    RECORDS_DIR          (default: /home/user/records)
    DOCKER_IMAGE         (default: guacenc-extract)
    INTERVAL_FRAMES_S    (default: 2)         secondes entre frames extraites
    MAX_FRAMES           (default: 12)        frames max envoyées à Gemini
    GEMINI_MODEL         (default: vide)      -m passé au CLI gemini, si fourni
    DB_HOST              (default: 127.0.0.1)
    DB_PORT              (default: 3306)
    DB_USER              (default: user)
    DB_PASSWORD          (default: Azerty01)
    DB_NAME              (default: guacamoledb)
    WATCH_SLEEP_S        (default: 60)        delay entre balayages en --watch
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import struct
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymysql

LOG = logging.getLogger("guac-ai-worker")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Namespace UUID utilisé par guacamole-auth-jdbc pour dériver le UUID
# déterministe d'une entrée d'historique (ConnectionRecordSet.UUID_NAMESPACE).
# Ce UUID est aussi le nom du dossier de l'enregistrement dans records/.
_HISTORY_UUID_NS = uuid.UUID("8b55f070-95f4-3d31-93ee-9c5845e7aa40").bytes


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def cfg() -> dict:
    return {
        "records_dir":   Path(env("RECORDS_DIR", "/home/user/records")),
        "docker_image":  env("DOCKER_IMAGE", "guacenc-extract"),
        "interval":      int(env("INTERVAL_FRAMES_S", "2")),
        "max_frames":    int(env("MAX_FRAMES", "12")),
        "gemini_model":  env("GEMINI_MODEL", ""),
        "db_host":       env("DB_HOST", "127.0.0.1"),
        "db_port":       int(env("DB_PORT", "3306")),
        "db_user":       env("DB_USER", "user"),
        "db_password":   env("DB_PASSWORD", "Azerty01"),
        "db_name":       env("DB_NAME", "guacamoledb"),
        "watch_sleep":   int(env("WATCH_SLEEP_S", "60")),
    }


@contextlib.contextmanager
def db_conn(c):
    conn = pymysql.connect(
        host=c["db_host"], port=c["db_port"],
        user=c["db_user"], password=c["db_password"],
        database=c["db_name"], autocommit=False,
    )
    try:
        yield conn
    finally:
        conn.close()


# ---------- scan ----------

def is_session_finished(recording: Path) -> bool:
    """Heuristique : le fichier n'a plus été écrit depuis 60 s."""
    age = time.time() - recording.stat().st_mtime
    return age > 60


def candidate_sessions(records_dir: Path):
    for d in sorted(records_dir.iterdir()):
        if not d.is_dir():
            continue
        if not UUID_RE.match(d.name):
            continue
        recording = d / "recording"
        if recording.is_file() and is_session_finished(recording):
            yield d, recording


# ---------- locks ----------

@contextlib.contextmanager
def session_lock(session_dir: Path):
    """flock non bloquant sur <dir>/.processing.lock — comme guac-agent/."""
    lock_path = session_dir / ".processing.lock"
    fh = open(lock_path, "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ---------- DB helpers ----------

def status_for(conn, history_uuid: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM session_ai_summary WHERE history_uuid = %s",
            (history_uuid,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def mark_analyzing(conn, history_uuid: str, started_at, ended_at):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO session_ai_summary
                (history_uuid, status, started_at, ended_at)
            VALUES (%s, 'analyzing', %s, %s)
            ON DUPLICATE KEY UPDATE
                status     = 'analyzing',
                started_at = COALESCE(VALUES(started_at), started_at),
                ended_at   = COALESCE(VALUES(ended_at),   ended_at),
                error      = NULL
            """,
            (history_uuid, started_at, ended_at),
        )
    conn.commit()


def mark_failed(conn, history_uuid: str, error: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE session_ai_summary SET status='failed', error=%s "
            "WHERE history_uuid=%s",
            (error[:8000], history_uuid),
        )
    conn.commit()


def mark_skipped(conn, history_uuid: str, started_at, ended_at, reason: str):
    """Statut terminal pour une session impossible à analyser — et qui ne
    traduit *pas* un bug du worker : enregistrement vide, connexion
    refusée par le serveur distant... Contrairement à 'analyzing', n'est
    jamais rejouée automatiquement."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO session_ai_summary
                (history_uuid, status, started_at, ended_at, summary, error)
            VALUES (%s, 'skipped', %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                status     = 'skipped',
                started_at = COALESCE(VALUES(started_at), started_at),
                ended_at   = COALESCE(VALUES(ended_at),   ended_at),
                summary    = VALUES(summary),
                risk_level = NULL,
                error      = VALUES(error)
            """,
            (history_uuid, started_at, ended_at,
             f"Session non analysée : {reason}", reason[:8000]),
        )
    conn.commit()


def save_result(conn, history_uuid: str, parsed: dict):
    summary = parsed.get("summary") or ""
    risk = parsed.get("risk_level") or "unknown"
    events = parsed.get("suspicious_events") or []
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE session_ai_summary "
            "SET status='done', summary=%s, risk_level=%s, error=NULL "
            "WHERE history_uuid=%s",
            (summary, risk[:20], history_uuid),
        )
        cur.execute(
            "DELETE FROM suspicious_event WHERE history_uuid=%s",
            (history_uuid,),
        )
        for ev in events:
            cur.execute(
                """
                INSERT INTO suspicious_event
                    (history_uuid, event_time_seconds, severity,
                     category, description, evidence)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    history_uuid,
                    timecode_to_seconds(ev.get("timecode")),
                    (ev.get("severity") or "")[:20] or None,
                    (ev.get("category") or "")[:100] or None,
                    ev.get("description"),
                    ev.get("evidence"),
                ),
            )
    conn.commit()


# ---------- enrichissement métadonnées ----------

def record_uuid(record_id: int) -> str:
    """UUID déterministe d'une entrée guacamole_connection_history.

    Reproduit ModeledActivityRecord#getUUID de guacamole-auth-jdbc :
    MD5 du namespace ConnectionRecordSet.UUID_NAMESPACE concaténé à
    l'history_id encodé en long big-endian, avec les bits de version (3)
    et de variant forcés — exactement java.util.UUID.nameUUIDFromBytes.
    C'est ce UUID qui nomme le dossier de l'enregistrement dans records/."""
    digest = bytearray(hashlib.md5(
        _HISTORY_UUID_NS + struct.pack(">q", record_id)
    ).digest())
    digest[6] = (digest[6] & 0x0f) | 0x30   # version 3
    digest[8] = (digest[8] & 0x3f) | 0x80   # variant RFC 4122
    return str(uuid.UUID(bytes=bytes(digest)))


def reconcile_metadata(conn):
    """Renseigne username / connection_name / started_at / ended_at des
    résumés depuis guacamole_connection_history.

    Le lien dossier d'enregistrement <-> entrée d'historique se fait via
    le UUID déterministe de Guacamole (record_uuid). Idempotent : seules
    les lignes encore dépourvues d'username sont traitées."""
    with conn.cursor() as cur:
        cur.execute("SELECT history_uuid FROM session_ai_summary "
                    "WHERE username IS NULL")
        pending = [r[0] for r in cur.fetchall()]
    if not pending:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT history_id, username, connection_name, "
                    "start_date, end_date FROM guacamole_connection_history")
        by_uuid = {record_uuid(r[0]): r for r in cur.fetchall()}
    updated = 0
    with conn.cursor() as cur:
        for hu in pending:
            row = by_uuid.get(hu)
            if row is None:
                continue
            _, username, connection_name, start_date, end_date = row
            cur.execute(
                "UPDATE session_ai_summary SET "
                "username = %s, connection_name = %s, "
                "started_at = COALESCE(%s, started_at), "
                "ended_at   = COALESCE(%s, ended_at) "
                "WHERE history_uuid = %s",
                (username, connection_name, start_date, end_date, hu),
            )
            updated += 1
    conn.commit()
    if updated:
        LOG.info("reconcile_metadata: %d session(s) enrichie(s) "
                 "depuis guacamole_connection_history", updated)


# ---------- extract / parse ----------

def timecode_to_seconds(tc):
    if not isinstance(tc, str):
        return None
    parts = tc.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        h, m, s = nums
    elif len(nums) == 2:
        h, m, s = 0, nums[0], nums[1]
    elif len(nums) == 1:
        h, m, s = 0, 0, nums[0]
    else:
        return None
    return h * 3600 + m * 60 + s


def extract_recording_metadata(recording: Path):
    """Résolution + durée — même logique que guac-agent/analyze-one.sh."""
    head = recording.open("rb").read(65536).decode("latin-1", errors="ignore")
    width = height = None
    duration_s = None
    syncs = []
    for instr in head.split(";"):
        if instr.startswith(("0.size,", "1.size,")):
            # 7.size,1.0,5.WIDTH,5.HEIGHT
            m = re.match(r"^\d+\.size,1\.0,\d+\.(\d+),\d+\.(\d+)", instr)
            if m and width is None:
                width, height = int(m.group(1)), int(m.group(2))
    # Pour la durée, parcourir tout le fichier (les sync events s'étalent partout)
    with recording.open("rb") as fh:
        data = fh.read().decode("latin-1", errors="ignore")
    for instr in data.split(";"):
        m = re.match(r"^\d+\.sync,\d+\.(-?\d+)", instr)
        if m:
            syncs.append(int(m.group(1)))
    if len(syncs) >= 2:
        duration_s = (syncs[-1] - syncs[0]) / 1000.0
    resolution = f"{width}x{height}" if width and height else None
    return resolution, duration_s


def _guac_elements(instr: str):
    """Découpe une instruction du protocole Guacamole en éléments.

    Chaque élément est encodé `LONGUEUR.VALEUR` ; le préfixe de longueur
    permet de gérer les virgules présentes à l'intérieur d'une valeur
    (ex. un message d'erreur)."""
    out = []
    i = 0
    while i < len(instr):
        dot = instr.find(".", i)
        if dot == -1:
            break
        try:
            length = int(instr[i:dot])
        except ValueError:
            break
        out.append(instr[dot + 1:dot + 1 + length])
        i = dot + 1 + length + 1  # saute la virgule séparatrice
    return out


# Opcodes qui dessinent réellement à l'écran. Leur absence totale d'un
# dump = enregistrement sans image exploitable (connexion refusée, etc.).
_DRAW_OPCODES = {"img", "png", "blob", "rect", "cfill", "copy", "cursor"}


def recording_is_empty(recording: Path):
    """Détecte un dump qui ne produira aucune frame exploitable.

    Une connexion refusée par le serveur distant ne génère qu'une
    instruction `error` suivie de `end` — aucun dessin d'écran, donc
    guacenc encode une vidéo de durée nulle et l'extraction rend 0 frame.

    Renvoie (True, raison) si le dump est inexploitable, (False, None)
    sinon."""
    with recording.open("rb") as fh:
        data = fh.read().decode("latin-1", errors="ignore")
    error_msg = None
    for raw in data.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        els = _guac_elements(raw)
        if not els:
            continue
        opcode = els[0]
        if opcode in _DRAW_OPCODES:
            return False, None
        if opcode == "error" and len(els) >= 2 and els[1]:
            error_msg = els[1]
    return True, error_msg or "enregistrement sans contenu d'écran"


def extract_frames(session_dir: Path, cfg_):
    """Appelle l'image Docker guacenc-extract sur <uuid>/recording.

    Produit <session_dir>/recording.m4v et <session_dir>/recording.frames/.
    """
    records_root = session_dir.parent
    uuid = session_dir.name
    cmd = [
        "docker", "run", "--rm",
        "-u", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{records_root}:/work",
        cfg_["docker_image"],
        f"{uuid}/recording", str(cfg_["interval"]),
    ]
    LOG.info("guacenc-extract: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def sample_frames(frames_dir: Path, max_frames: int):
    all_frames = sorted(frames_dir.glob("frame_*.png"))
    deduped = []
    prev_hash = None
    for f in all_frames:
        h = md5_of(f)
        if h != prev_hash:
            deduped.append(f)
            prev_hash = h
    if len(deduped) <= max_frames:
        return deduped
    # échantillonnage uniforme
    step = len(deduped) / max_frames
    return [deduped[int((i + 0.5) * step)] for i in range(max_frames)]


# ---------- LLM ----------

PROMPT_TEMPLATE = """\
Tu es un analyste sécurité chargé d'auditer des enregistrements de \
sessions distantes Apache Guacamole. Tu reçois ci-dessous une série de \
captures d'écran chronologiques d'une session terminée.

Métadonnées :
- ID de session : {uuid}
- Durée : {duration}
- Résolution : {resolution}
- Nombre de frames transmises : {n_frames} (échantillon)
- Intervalle d'extraction : {interval}s

Captures (ordre chronologique) :
{attachments}

Produis exclusivement un objet JSON valide, sans texte autour, conforme \
à ce schéma :

{{
  "summary": "résumé exécutif en 2-4 phrases, français",
  "risk_level": "low" | "medium" | "high",
  "observed_actions": [
    "action 1", "action 2", "..."
  ],
  "suspicious_events": [
    {{
      "timecode": "HH:MM:SS",
      "severity": "low" | "medium" | "high",
      "category": "ex: sensitive_file_access, privilege_escalation, data_exfiltration, destructive_command, security_disabled, account_creation",
      "description": "ce qui est observé",
      "evidence": "élément visuel qui appuie l'observation"
    }}
  ],
  "limitations": "ce que tu n'as pas pu déterminer faute d'éléments visibles"
}}

Règles strictes :
- Si rien de suspect, "suspicious_events": [].
- Formule en hypothèse ("semble", "probablement") quand l'image est ambiguë.
- N'invente pas d'action non visible.
- Tu réponds UNIQUEMENT par le JSON, sans préfixe ni markdown, sans bloc ```.
"""


def call_gemini(session_dir: Path, sample, meta, cfg_):
    uuid = session_dir.name
    frames_dir = session_dir / "recording.frames"
    duration = f"{meta[1]:.1f}s" if meta[1] else "inconnue"
    resolution = meta[0] or "inconnue"
    attachments = "\n".join(f"@{p}" for p in sample)
    prompt = PROMPT_TEMPLATE.format(
        uuid=uuid,
        duration=duration,
        resolution=resolution,
        n_frames=len(sample),
        interval=cfg_["interval"],
        attachments=attachments,
    )
    args = [
        "gemini",
        "-p", prompt,
        "--yolo",
        "-o", "text",
        "--include-directories", str(frames_dir),
        "--skip-trust",
    ]
    if cfg_["gemini_model"]:
        args += ["-m", cfg_["gemini_model"]]
    LOG.info("calling gemini (%d frames)", len(sample))
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"gemini exit {res.returncode}: {res.stderr.strip()[:1000]}"
        )
    return res.stdout


def parse_llm_output(raw: str) -> dict:
    # Le prompt demande du JSON pur, mais le modèle peut se laisser tenter
    # par un bloc markdown. On extrait alors entre la première { et la
    # dernière }.
    raw = raw.strip()
    if not raw.startswith("{"):
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise ValueError(f"no JSON object in output: {raw[:200]}")
        raw = raw[first:last + 1]
    return json.loads(raw)


# ---------- pipeline ----------

def process_session(session_dir: Path, recording: Path, conn, cfg_):
    uuid = session_dir.name
    LOG.info("=== %s ===", uuid)

    # Statuts terminaux : on ne rejoue jamais automatiquement, sinon une
    # session non analysable est ré-encodée par guacenc à chaque tick (60 s)
    # indéfiniment. Pour forcer une réanalyse : DELETE FROM session_ai_summary
    # (cf. CLAUDE.md §7bis).
    existing = status_for(conn, uuid)
    if existing in ("done", "skipped", "failed"):
        LOG.info("[skip] statut terminal en base (status=%s)", existing)
        return
    if existing == "analyzing":
        # session_lock empêche déjà la concurrence locale. Si on retombe
        # ici sans verrou, c'est qu'un précédent run a planté avant
        # mark_failed/save_result : on retente.
        LOG.info("status=analyzing en base, on retente")

    started_at = datetime.fromtimestamp(
        session_dir.stat().st_ctime, tz=timezone.utc
    ).replace(tzinfo=None)
    ended_at = datetime.fromtimestamp(
        recording.stat().st_mtime, tz=timezone.utc
    ).replace(tzinfo=None)

    # Un dump sans contenu d'écran (connexion refusée, session vide) ne
    # produira aucune frame : inutile de lancer guacenc. On le classe en
    # 'skipped' plutôt que 'failed' — ce n'est pas un échec du worker.
    empty, reason = recording_is_empty(recording)
    if empty:
        LOG.info("[skip] enregistrement non analysable : %s", reason)
        mark_skipped(conn, uuid, started_at, ended_at, reason)
        return

    mark_analyzing(conn, uuid, started_at, ended_at)

    try:
        frames_dir = session_dir / "recording.frames"
        if not frames_dir.is_dir() or not any(frames_dir.glob("frame_*.png")):
            extract_frames(session_dir, cfg_)
        else:
            LOG.info("frames déjà présentes, on saute guacenc-extract")

        meta = extract_recording_metadata(recording)
        sample = sample_frames(frames_dir, cfg_["max_frames"])
        if not sample:
            # guacenc a tourné mais n'a rien produit d'exploitable : ce
            # n'est pas un bug du worker -> statut terminal 'skipped'.
            LOG.info("[skip] guacenc n'a produit aucune frame exploitable")
            mark_skipped(conn, uuid, started_at, ended_at,
                         "guacenc n'a produit aucune frame exploitable")
            return

        raw = call_gemini(session_dir, sample, meta, cfg_)
        (session_dir / "analysis.json").write_text(raw, encoding="utf-8")

        parsed = parse_llm_output(raw)
        save_result(conn, uuid, parsed)
        LOG.info("[ok] risk=%s events=%d",
                 parsed.get("risk_level"),
                 len(parsed.get("suspicious_events") or []))

    except Exception as exc:
        LOG.exception("échec sur %s", uuid)
        mark_failed(conn, uuid, repr(exc))


def tick(cfg_):
    with db_conn(cfg_) as conn:
        try:
            reconcile_metadata(conn)
        except pymysql.Error:
            LOG.exception("reconcile_metadata a échoué, on continue")
        for session_dir, recording in candidate_sessions(cfg_["records_dir"]):
            with session_lock(session_dir) as acquired:
                if not acquired:
                    LOG.info("[skip] verrou pris : %s", session_dir.name)
                    continue
                try:
                    process_session(session_dir, recording, conn, cfg_)
                except pymysql.Error:
                    LOG.exception("erreur DB sur %s, on reconnecte au prochain tick",
                                  session_dir.name)
                    return


def main():
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--once", action="store_true",
                     help="un balayage puis sortie")
    grp.add_argument("--watch", action="store_true",
                     help="boucle continue, sleep WATCH_SLEEP_S entre balayages")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    c = cfg()

    if args.once:
        tick(c)
        return

    while True:
        try:
            tick(c)
        except Exception:
            LOG.exception("tick a planté, on continue")
        time.sleep(c["watch_sleep"])


if __name__ == "__main__":
    sys.exit(main())
