#!/usr/bin/env python3
"""Remove every lookup in a category (default: adult) from Network Watch's history, for good.

Deletes the lookups whose domain, or a parent domain, is on the category's list, and the record of which of those
domains were ever seen (domcat); then rebuilds the file so nothing of them is left in it. A backup of the database as
it was goes beside it (it still holds what was removed; delete it once you're happy).

Run with Network Watch stopped, since it writes the same database. Purge Pi-hole first (horae/scripts/adult-content.sh):
Network Watch re-reads the last minute from Pi-hole when it starts.
    docker compose stop pihole-watch
    docker compose run --rm --no-deps --name pihole-watch-purge pihole-watch python -u purge.py adult
    docker compose up -d pihole-watch
(./deploy.sh adult does all of this, Pi-hole included.)
"""
import sqlite3
import sys
import time

import app  # Network Watch itself: its database path, category lists and the same matching rules


def matches(domain, listed):
    labels = domain.split(".")
    return any(".".join(labels[i:]) in listed for i in range(len(labels) - 1))


def main(category="adult"):
    if category not in app.CATEGORY_LISTS:
        sys.exit(f"Unknown category {category!r}; known: {', '.join(app.CATEGORY_LISTS)}")
    app.refresh_lists()  # loads the saved list; downloads it only if it is missing or a day old
    listed = app.CATEGORY_STATE.get(category, {}).get("domains", set())
    if len(listed) < 1000:
        sys.exit(f"The {category} list has only {len(listed)} domains; it looks broken, so nothing was changed.")

    backup = f"{app.DB_PATH}.before-{category}-purge-{time.strftime('%Y%m%d-%H%M%S')}"
    with sqlite3.connect(app.DB_PATH) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)  # a consistent copy, write-ahead log included

    con = sqlite3.connect(app.DB_PATH, timeout=60)
    con.execute("PRAGMA secure_delete = ON")  # deleted rows are overwritten with zeros, not just unlinked
    hits = [d for (d,) in con.execute("SELECT DISTINCT domain FROM q") if matches(d, listed)]
    con.execute("CREATE TEMP TABLE purge (domain TEXT PRIMARY KEY)")
    con.executemany("INSERT INTO purge VALUES (?)", [(d,) for d in hits])
    with con:
        lookups = con.execute("DELETE FROM q WHERE domain IN (SELECT domain FROM purge)").rowcount
        seen = con.execute("DELETE FROM domcat WHERE category = ? OR domain IN (SELECT domain FROM purge)", (category,)).rowcount
    con.execute("VACUUM")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    print(f"Network Watch: removed {lookups:,} lookups of {len(hits):,} {category} sites ({seen:,} tags); "
          f"the list has {len(listed):,} domains.")
    print(f"Backup of the database as it was (still holds them): {backup}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
