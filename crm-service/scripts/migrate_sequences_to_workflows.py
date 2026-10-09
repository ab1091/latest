"""
One-time, idempotent data migration: converts every legacy lead_sequences
row (013_lead_sequences.sql — one fixed linear sequence per business) into
an equivalent workflow graph (017_workflow_engine.sql). Each step becomes a
wait+action node pair chained in order; existing lead_sequence_enrollments
map to lead_workflow_enrollments at the corresponding node. Pending
scheduled_callbacks carrying sequence_enrollment_id/sequence_step_id are
backfilled with workflow_enrollment_id/workflow_node_key on the SAME row —
no new callback rows are created, since the executor primitive carries
over 1:1.

The old lead_sequences/lead_sequence_steps/lead_sequence_enrollments tables
are left in place afterward (deprecated, not dropped) as a one-release
audit fallback.

Run once: crm-service/venv/bin/python scripts/migrate_sequences_to_workflows.py
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from core.db import get_conn, dict_cursor  # noqa: E402


def migrate():
    conn = get_conn()
    cur = dict_cursor(conn)

    cur.execute("SELECT * FROM lead_sequences WHERE is_active")
    sequences = cur.fetchall()
    print(f"Found {len(sequences)} active legacy sequence(s)")

    for seq in sequences:
        seq = dict(seq)
        cur.execute(
            "SELECT template_key FROM workflows WHERE name = %s AND business_id = %s",
            (f"[migrated] {seq['name']}", seq["business_id"]),
        )
        if cur.fetchone():
            print(f"  sequence {seq['id']} already migrated — skipping")
            continue

        cur.execute(
            "SELECT * FROM lead_sequence_steps WHERE sequence_id = %s ORDER BY step_order ASC",
            (seq["id"],),
        )
        steps = [dict(r) for r in cur.fetchall()]
        if not steps:
            print(f"  sequence {seq['id']} has no steps — skipping")
            continue

        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO workflows (id, business_id, name, description, trigger_type, trigger_stage,
                                    is_default_for_trigger, status)
            VALUES (%s, %s, %s, %s, 'stage_enter', 'new_lead', TRUE, 'active')
            """,
            (workflow_id, seq["business_id"], f"[migrated] {seq['name']}",
             "Auto-converted from the legacy single-sequence engine"),
        )

        trigger_key = "trigger"
        cur.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, 'trigger', '{}')",
            (f"wn_{uuid.uuid4().hex[:12]}", workflow_id, trigger_key),
        )

        prev_key = trigger_key
        prev_offset_seconds = 0
        step_node_keys = {}  # step id -> action node key, for scheduled_callbacks backfill

        for step in steps:
            abs_offset = step["day_offset"] * 86400 + step["delay_seconds_within_day"]
            wait_seconds = max(0, abs_offset - prev_offset_seconds)

            wait_key = f"wait_{step['step_order']}"
            cur.execute(
                "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, 'wait', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", workflow_id, wait_key,
                 f'{{"amount": {wait_seconds}, "unit": "seconds"}}'),
            )
            cur.execute(
                "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, %s, %s)",
                (f"we_{uuid.uuid4().hex[:12]}", workflow_id, prev_key, wait_key),
            )

            action_key = f"step_{step['step_order']}"
            action_type = "ai_call" if step["action_type"] == "call" else "send_sms"
            config = f'{{"channel": "{step.get("channel") or "sms"}", "template_ref": {("null" if not step.get("template_ref") else repr(step["template_ref"]))}}}'
            cur.execute(
                "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, %s, %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", workflow_id, action_key, action_type, config),
            )
            cur.execute(
                "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, %s, %s)",
                (f"we_{uuid.uuid4().hex[:12]}", workflow_id, wait_key, action_key),
            )

            step_node_keys[step["id"]] = action_key
            prev_key = action_key
            prev_offset_seconds = abs_offset

        end_key = "end"
        cur.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, 'end', '{}')",
            (f"wn_{uuid.uuid4().hex[:12]}", workflow_id, end_key),
        )
        cur.execute(
            "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, %s, %s)",
            (f"we_{uuid.uuid4().hex[:12]}", workflow_id, prev_key, end_key),
        )

        # Migrate enrollments + backfill scheduled_callbacks in place
        cur.execute("SELECT * FROM lead_sequence_enrollments WHERE sequence_id = %s", (seq["id"],))
        enrollments = [dict(r) for r in cur.fetchall()]
        for enr in enrollments:
            new_enr_id = f"lwe_{uuid.uuid4().hex[:12]}"
            cur.execute(
                """
                INSERT INTO lead_workflow_enrollments (id, lead_id, workflow_id, workflow_version, current_node_key, status, enrolled_at)
                VALUES (%s, %s, %s, 1, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (new_enr_id, enr["lead_id"], workflow_id, trigger_key, enr["status"], enr["enrolled_at"]),
            )
            cur.execute(
                "SELECT id, sequence_step_id FROM scheduled_callbacks WHERE sequence_enrollment_id = %s AND status = 'pending'",
                (enr["id"],),
            )
            for cb in cur.fetchall():
                node_key = step_node_keys.get(cb["sequence_step_id"])
                if node_key:
                    cur.execute(
                        "UPDATE scheduled_callbacks SET workflow_enrollment_id = %s, workflow_node_key = %s WHERE id = %s",
                        (new_enr_id, node_key, cb["id"]),
                    )

        print(f"  migrated sequence {seq['id']} -> workflow {workflow_id} ({len(steps)} steps, {len(enrollments)} enrollments)")

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    migrate()
