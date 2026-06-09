#!/usr/bin/env python
"""Seed the reading-plan catalog tables in DynamoDB (COMPANION_SPEC.md §9.1).

Loads the catalog (`reading_plans`) and per-day content (`reading_plan_days`) from
`plan_content.py` into the env's DynamoDB tables. Idempotent: re-running overwrites
the same items (PUT by primary key), so it is safe to run repeatedly.

Table names follow the repo convention `{env}-{project}-<table>`:
    {env}-{project}-reading-plans          (PK slug)
    {env}-{project}-reading-plan-days       (PK slug, SK dayNumber [Number])

USAGE (from repo root, conda env `versiful_backend`, with AWS creds for the target
account already exported / via your profile):

    conda activate versiful_backend
    # dry run first to see what would be written:
    python lambdas/plans/seed/seed_plans.py --env dev --dry-run
    # then load for real:
    python lambdas/plans/seed/seed_plans.py --env dev

Flags:
    --env       dev | staging | prod        (default: dev)
    --project   project name prefix          (default: versiful)
    --region    AWS region                   (default: us-east-1 / AWS_REGION)
    --dry-run   print what would be written, make no AWS calls

DO NOT run this against prod without an explicit plan/approval. This script is the
documented loader; CI/Terraform do not run it.
"""
import argparse
import os
import sys
from decimal import Decimal

# Import the data module whether run as a script or imported as a package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from plan_content import CATALOG, PLAN_DAYS
except ImportError:  # pragma: no cover - allows `python -m` style invocation too
    from lambdas.plans.seed.plan_content import CATALOG, PLAN_DAYS


def _validate():
    """Fail fast if catalog dayCount doesn't match the authored day content."""
    errors = []
    slugs = {p["slug"] for p in CATALOG}
    for plan in CATALOG:
        slug = plan["slug"]
        days = PLAN_DAYS.get(slug, [])
        if len(days) != plan["dayCount"]:
            errors.append(
                f"{slug}: dayCount={plan['dayCount']} but {len(days)} days authored"
            )
        expected = list(range(1, plan["dayCount"] + 1))
        actual = sorted(d["dayNumber"] for d in days)
        if actual != expected:
            errors.append(f"{slug}: dayNumbers {actual} != expected {expected}")
    for slug in PLAN_DAYS:
        if slug not in slugs:
            errors.append(f"PLAN_DAYS has '{slug}' with no catalog entry")
    if errors:
        raise SystemExit("Seed validation failed:\n  " + "\n  ".join(errors))


def _table_names(env: str, project: str):
    return (
        f"{env}-{project}-reading-plans",
        f"{env}-{project}-reading-plan-days",
    )


def seed(env: str, project: str, region: str, dry_run: bool):
    _validate()
    plans_table_name, days_table_name = _table_names(env, project)

    print(f"Target catalog table : {plans_table_name}")
    print(f"Target days table    : {days_table_name}")
    print(f"Region               : {region}")
    print(f"Dry run              : {dry_run}\n")

    plan_count = len(CATALOG)
    day_count = sum(len(d) for d in PLAN_DAYS.values())

    if dry_run:
        for plan in CATALOG:
            print(f"  [plan] {plan['slug']:<18} {plan['title']} ({plan['dayCount']} days)")
        print(f"\nWould write {plan_count} catalog items and {day_count} day items.")
        return

    import boto3

    dynamodb = boto3.resource("dynamodb", region_name=region)
    plans_table = dynamodb.Table(plans_table_name)
    days_table = dynamodb.Table(days_table_name)

    # Catalog: one PutItem per plan (small table).
    for plan in CATALOG:
        plans_table.put_item(Item=dict(plan))
        print(f"  [plan] wrote {plan['slug']}")

    # Days: batch_writer handles batching/retries. dayNumber must be a Number (SK is N).
    with days_table.batch_writer() as batch:
        for slug, days in PLAN_DAYS.items():
            for day in days:
                item = {
                    "slug": slug,
                    "dayNumber": Decimal(int(day["dayNumber"])),
                    "passageRef": day["passageRef"],
                    "theme": day["theme"],
                    "prompt": day["prompt"],
                }
                batch.put_item(Item=item)
            print(f"  [days] wrote {len(days)} days for {slug}")

    print(f"\nDone. Wrote {plan_count} catalog items and {day_count} day items.")


def main():
    parser = argparse.ArgumentParser(description="Seed reading-plan catalog into DynamoDB.")
    parser.add_argument("--env", default="dev", choices=["dev", "staging", "prod"])
    parser.add_argument("--project", default=os.environ.get("PROJECT_NAME", "versiful"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    seed(args.env, args.project, args.region, args.dry_run)


if __name__ == "__main__":
    main()
