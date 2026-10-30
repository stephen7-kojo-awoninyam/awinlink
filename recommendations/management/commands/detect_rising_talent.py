from django.core.management.base import BaseCommand, CommandError
from recommendations.rising_talent import BATCH_SIZE, record_snapshots
from recommendations.rising_job import run_alerts


class Command(BaseCommand):
    help = "Record opted-in public baselines and deliver relevant, capped Rising Talent alerts."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview counts without any writes or delivery.")
        parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
        parser.add_argument("--recipient-after", type=int, default=0, help="Resume after this preference ID.")
        parser.add_argument("--max-recipients", type=int, default=None)

    def handle(self, *args, **options):
        if not 1 <= options["batch_size"] <= BATCH_SIZE or options["recipient_after"] < 0 or (
                options["max_recipients"] is not None and options["max_recipients"] < 1):
            raise CommandError(f"Batch size must be 1–{BATCH_SIZE}; cursor must be non-negative; max recipients must be positive.")
        snapshots = 0 if options["dry_run"] else record_snapshots(batch_size=options["batch_size"])
        result = run_alerts(dry_run=options["dry_run"], batch_size=options["batch_size"],
            after=options["recipient_after"], max_recipients=options["max_recipients"],
            progress=lambda cursor, processed: self.stdout.write(f"Checkpoint: recipient-after={cursor}; {processed} processed."))
        self.stdout.write(f"{'Preview' if options['dry_run'] else 'Complete'}: {result['matches']} matches, {snapshots} new baselines, {result['alerts']} alerts; {result['processed']} recipients processed; recipient-after={result['recipient_after']}.")
