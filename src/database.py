import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from src.config import BASE_DIR, Config

logger = logging.getLogger("FaceGuard.Database")

CACHE_FILE = BASE_DIR / "logs" / ".owner_cache.npz"


class FaceDatabase:
    def __init__(self, auto_connect: bool = True):
        self.conn = None
        self.cached_embeddings: Optional[np.ndarray] = None  # Shape: (N, 512)
        self.cached_labels: List[str] = []

        if auto_connect:
            self.connect()
            self.reload_cache()

    def connect(self) -> bool:
        """Establishes connection to PostgreSQL and registers pgvector."""
        if self.conn is not None and self.conn.closed == 0:
            return True

        try:
            self.conn = psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                connect_timeout=3
            )
            self.conn.autocommit = True
            try:
                register_vector(self.conn)
            except Exception as e:
                logger.warning("Could not register pgvector extension on connection: %s", e)
            logger.info("Successfully connected to PostgreSQL (%s:%s/%s)", Config.DB_HOST, Config.DB_PORT, Config.DB_NAME)
            return True
        except Exception as e:
            logger.warning("PostgreSQL connection failed: %s (will use local cache if available)", e)
            self.conn = None
            return False

    def is_connected(self) -> bool:
        return self.conn is not None and self.conn.closed == 0

    def reload_cache(self) -> bool:
        """
        Loads owner embeddings from PostgreSQL into RAM (In-Memory Caching).
        Falls back to local encrypted/persisted cache file if DB is temporarily offline.
        """
        loaded_from_db = False
        if self.connect():
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT pose_label, embedding FROM owner_embeddings ORDER BY id ASC;")
                    rows = cur.fetchall()

                if rows:
                    labels = [r[0] for r in rows]
                    raw_vectors = []
                    for r in rows:
                        val = r[1]
                        if hasattr(val, "to_numpy"):
                            raw_vectors.append(val.to_numpy())
                        elif hasattr(val, "to_list"):
                            raw_vectors.append(np.array(val.to_list(), dtype=np.float32))
                        else:
                            raw_vectors.append(np.asarray(val, dtype=np.float32))
                    embs = np.array(raw_vectors, dtype=np.float32)
                    # Ensure normalized
                    norms = np.linalg.norm(embs, axis=1, keepdims=True)
                    norms[norms == 0] = 1.0
                    self.cached_embeddings = embs / norms
                    self.cached_labels = labels
                    loaded_from_db = True

                    # Persist local cache for offline fallback
                    try:
                        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                        np.savez_compressed(
                            str(CACHE_FILE),
                            embeddings=self.cached_embeddings,
                            labels=np.array(self.cached_labels)
                        )
                    except Exception as e:
                        logger.warning("Failed to save local offline cache: %s", e)

                    logger.info("Loaded %d owner embeddings from PostgreSQL into RAM cache.", len(self.cached_labels))
                    return True
                else:
                    logger.info("No owner embeddings found in PostgreSQL table 'owner_embeddings'.")
            except Exception as e:
                logger.warning("Failed to query owner embeddings from DB: %s", e)

        # Fallback to local cache file if DB failed or had no records
        if not loaded_from_db and CACHE_FILE.exists():
            try:
                data = np.load(str(CACHE_FILE), allow_pickle=True)
                self.cached_embeddings = data["embeddings"]
                self.cached_labels = data["labels"].tolist()
                logger.info("Loaded %d owner embeddings from local offline cache file.", len(self.cached_labels))
                return True
            except Exception as e:
                logger.error("Failed to load local offline cache: %s", e)

        return False

    def clear_owner_embeddings(self) -> bool:
        """Clears previous enrollment records before re-registering."""
        if not self.connect():
            logger.error("Cannot clear owner embeddings: PostgreSQL disconnected.")
            return False

        try:
            with self.conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE owner_embeddings RESTART IDENTITY;")
            self.cached_embeddings = None
            self.cached_labels = []
            if CACHE_FILE.exists():
                try:
                    CACHE_FILE.unlink()
                except OSError:
                    pass
            logger.info("Cleared owner embeddings table.")
            return True
        except Exception as e:
            logger.error("Error clearing owner embeddings: %s", e)
            return False

    def save_owner_embedding(self, pose_label: str, embedding: np.ndarray) -> bool:
        """Saves a normalized 512-D owner facial embedding to PostgreSQL."""
        if not self.connect():
            logger.error("Cannot save embedding: PostgreSQL disconnected.")
            return False

        norm_emb = embedding / np.linalg.norm(embedding)
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO owner_embeddings (pose_label, embedding) VALUES (%s, %s);",
                    (pose_label, norm_emb.tolist())
                )
            return True
        except Exception as e:
            logger.error("Error inserting owner embedding: %s", e)
            return False

    def verify_face(self, query_embedding: np.ndarray, use_cache: bool = True) -> Tuple[bool, float, str]:
        """
        Matches a captured face embedding against enrolled owner embeddings.
        Returns: (is_owner, max_similarity_score, matched_pose_label)

        Uses In-Memory Caching by default (<0.05ms) per PRD Section 4.4 and 9.1.
        Falls back to PostgreSQL pgvector query if cache is empty.
        """
        norm_query = query_embedding / np.linalg.norm(query_embedding)

        # In-Memory Fast Vectorized Cosine Match
        if use_cache and self.cached_embeddings is not None and len(self.cached_embeddings) > 0:
            similarities = np.dot(self.cached_embeddings, norm_query)
            best_idx = int(np.argmax(similarities))
            best_similarity = float(similarities[best_idx])
            best_label = self.cached_labels[best_idx]
            is_owner = best_similarity >= Config.SIMILARITY_THRESHOLD
            return is_owner, best_similarity, best_label

        # Fallback: SQL pgvector query
        if self.connect():
            try:
                with self.conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT pose_label, 1 - (embedding <=> %s) AS similarity
                        FROM owner_embeddings
                        ORDER BY embedding <=> %s ASC
                        LIMIT 1;
                        """,
                        (norm_query.tolist(), norm_query.tolist())
                    )
                    row = cur.fetchone()
                    if not row:
                        return False, 0.0, "none"

                    pose_label, similarity = row[0], float(row[1])
                    is_owner = similarity >= Config.SIMILARITY_THRESHOLD
                    return is_owner, similarity, pose_label
            except Exception as e:
                logger.error("DB verify_face failed: %s", e)

        return False, 0.0, "none"

    def check_repeat_intruder(self, intruder_embedding: np.ndarray, threshold: float = 0.55) -> Optional[int]:
        """Checks if this unknown face was previously recorded in security logs."""
        if not self.connect():
            return None

        norm_emb = intruder_embedding / np.linalg.norm(intruder_embedding)
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, 1 - (intruder_embedding <=> %s) AS similarity
                    FROM security_logs
                    WHERE event_type = 'INTRUDER_ALERT' AND intruder_embedding IS NOT NULL
                    ORDER BY intruder_embedding <=> %s ASC
                    LIMIT 1;
                    """,
                    (norm_emb.tolist(), norm_emb.tolist())
                )
                row = cur.fetchone()
                if row and float(row[1]) >= threshold:
                    return int(row[0])
        except Exception as e:
            logger.warning("Error checking repeat intruder: %s", e)

        return None

    def log_security_event(
        self,
        event_type: str,
        similarity_score: Optional[float] = None,
        intruder_embedding: Optional[np.ndarray] = None,
        snapshot_path: Optional[str] = None,
        is_notified: bool = False
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Logs a security incident to PostgreSQL.
        Returns: (new_log_id, repeat_offender_log_id)
        """
        if not self.connect():
            logger.warning("PostgreSQL offline: Security event '%s' logged locally only.", event_type)
            return None, None

        repeat_id = None
        norm_emb = None

        if intruder_embedding is not None:
            norm_emb = intruder_embedding / np.linalg.norm(intruder_embedding)
            repeat_id = self.check_repeat_intruder(norm_emb)

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO security_logs 
                    (event_type, similarity_score, intruder_embedding, repeat_offender_of, snapshot_path, is_notified)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        event_type,
                        similarity_score,
                        norm_emb.tolist() if norm_emb is not None else None,
                        repeat_id,
                        snapshot_path,
                        is_notified
                    )
                )
                new_id = cur.fetchone()[0]
                return new_id, repeat_id
        except Exception as e:
            logger.error("Failed to insert security log: %s", e)
            return None, None

    def get_pending_notifications(self) -> List[Dict]:
        """Retrieves intruder alerts that could not be delivered to Telegram due to offline status."""
        if not self.connect():
            return []

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, event_type, similarity_score, snapshot_path, detected_at, repeat_offender_of
                    FROM security_logs
                    WHERE is_notified = FALSE AND event_type = 'INTRUDER_ALERT'
                    ORDER BY detected_at ASC
                    LIMIT 10;
                    """
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": r[0],
                        "event_type": r[1],
                        "similarity_score": r[2],
                        "snapshot_path": r[3],
                        "detected_at": r[4],
                        "repeat_offender_of": r[5]
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Failed to query pending notifications: %s", e)
            return []

    def mark_as_notified(self, log_id: int):
        """Marks a security log as successfully sent via Telegram."""
        if not self.connect():
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE security_logs SET is_notified = TRUE WHERE id = %s;", (log_id,))
        except Exception as e:
            logger.error("Failed to update notification status for log #%s: %s", log_id, e)

