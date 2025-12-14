from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from cryptography.fernet import Fernet, InvalidToken


class Command(BaseCommand):
    help = 'Rotate encryption keys for all encrypted fields in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--old-key',
            type=str,
            required=True,
            help='The current encryption key (base64-encoded Fernet key)'
        )
        parser.add_argument(
            '--new-key',
            type=str,
            required=True,
            help='The new encryption key to rotate to (base64-encoded Fernet key)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without making changes'
        )

    def handle(self, *args, **options):
        old_key = options['old_key']
        new_key = options['new_key']
        dry_run = options['dry_run']

        try:
            old_fernet = Fernet(old_key.encode() if isinstance(old_key, str) else old_key)
        except Exception as e:
            raise CommandError(f"Invalid old key: {e}")

        try:
            new_fernet = Fernet(new_key.encode() if isinstance(new_key, str) else new_key)
        except Exception as e:
            raise CommandError(f"Invalid new key: {e}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        from accounts.models import PatientProfile
        from clinic.models import Appointment, MedicalNote

        stats = {
            'PatientProfile': {'processed': 0, 'updated': 0, 'errors': 0},
            'Appointment': {'processed': 0, 'updated': 0, 'errors': 0},
            'MedicalNote': {'processed': 0, 'updated': 0, 'errors': 0},
        }

        self.stdout.write("Starting key rotation...")
        self.stdout.write(f"  Old key: {old_key[:8]}...")
        self.stdout.write(f"  New key: {new_key[:8]}...")

        try:
            with transaction.atomic():
                self.stdout.write("\nProcessing PatientProfile records...")
                for profile in PatientProfile.objects.all():
                    stats['PatientProfile']['processed'] += 1
                    updated = False

                    if profile.phone and profile.phone not in ('', '[DATA_UNAVAILABLE]'):
                        try:
                            raw_phone = PatientProfile.objects.filter(pk=profile.pk).values_list('phone', flat=True).first()
                            if raw_phone:
                                decrypted = old_fernet.decrypt(raw_phone.encode()).decode('utf-8')
                                new_encrypted = new_fernet.encrypt(decrypted.encode()).decode('utf-8')
                                profile.phone = decrypted  
                                updated = True
                        except InvalidToken:
                            self.stdout.write(self.style.ERROR(f"  Failed to decrypt phone for PatientProfile {profile.pk}"))
                            stats['PatientProfile']['errors'] += 1

                    if profile.address and profile.address not in ('', '[DATA_UNAVAILABLE]'):
                        try:
                            raw_address = PatientProfile.objects.filter(pk=profile.pk).values_list('address', flat=True).first()
                            if raw_address:
                                decrypted = old_fernet.decrypt(raw_address.encode()).decode('utf-8')
                                new_encrypted = new_fernet.encrypt(decrypted.encode()).decode('utf-8')
                                profile.address = decrypted
                                updated = True
                        except InvalidToken:
                            self.stdout.write(self.style.ERROR(f"  Failed to decrypt address for PatientProfile {profile.pk}"))
                            stats['PatientProfile']['errors'] += 1

                    if updated and not dry_run:
                        from django.db import connection
                        cursor = connection.cursor()
                        
                        updates = {}
                        if profile.phone and profile.phone not in ('', '[DATA_UNAVAILABLE]'):
                            try:
                                raw_phone = PatientProfile.objects.filter(pk=profile.pk).values_list('phone', flat=True).first()
                                if raw_phone:
                                    decrypted = old_fernet.decrypt(raw_phone.encode()).decode('utf-8')
                                    updates['phone'] = new_fernet.encrypt(decrypted.encode()).decode('utf-8')
                            except InvalidToken:
                                pass
                        
                        if profile.address and profile.address not in ('', '[DATA_UNAVAILABLE]'):
                            try:
                                raw_address = PatientProfile.objects.filter(pk=profile.pk).values_list('address', flat=True).first()
                                if raw_address:
                                    decrypted = old_fernet.decrypt(raw_address.encode()).decode('utf-8')
                                    updates['address'] = new_fernet.encrypt(decrypted.encode()).decode('utf-8')
                            except InvalidToken:
                                pass
                        
                        if updates:
                            PatientProfile.objects.filter(pk=profile.pk).update(**updates)
                            stats['PatientProfile']['updated'] += 1

                self.stdout.write("\nProcessing Appointment records...")
                for appointment in Appointment.objects.all():
                    stats['Appointment']['processed'] += 1
                    
                    if appointment.diagnosis and appointment.diagnosis not in ('', '[DATA_UNAVAILABLE]'):
                        try:
                            raw_diagnosis = Appointment.objects.filter(pk=appointment.pk).values_list('diagnosis', flat=True).first()
                            if raw_diagnosis:
                                decrypted = old_fernet.decrypt(raw_diagnosis.encode()).decode('utf-8')
                                if not dry_run:
                                    new_encrypted = new_fernet.encrypt(decrypted.encode()).decode('utf-8')
                                    Appointment.objects.filter(pk=appointment.pk).update(diagnosis=new_encrypted)
                                stats['Appointment']['updated'] += 1
                        except InvalidToken:
                            self.stdout.write(self.style.ERROR(f"  Failed to decrypt diagnosis for Appointment {appointment.pk}"))
                            stats['Appointment']['errors'] += 1

                self.stdout.write("\nProcessing MedicalNote records...")
                for note in MedicalNote.objects.all():
                    stats['MedicalNote']['processed'] += 1
                    
                    if note.content and note.content not in ('', '[DATA_UNAVAILABLE]'):
                        try:
                            raw_content = MedicalNote.objects.filter(pk=note.pk).values_list('content', flat=True).first()
                            if raw_content:
                                decrypted = old_fernet.decrypt(raw_content.encode()).decode('utf-8')
                                if not dry_run:
                                    new_encrypted = new_fernet.encrypt(decrypted.encode()).decode('utf-8')
                                    MedicalNote.objects.filter(pk=note.pk).update(content=new_encrypted)
                                stats['MedicalNote']['updated'] += 1
                        except InvalidToken:
                            self.stdout.write(self.style.ERROR(f"  Failed to decrypt content for MedicalNote {note.pk}"))
                            stats['MedicalNote']['errors'] += 1

                if dry_run:
                    self.stdout.write(self.style.WARNING("\nDRY RUN - Rolling back all changes..."))
                    raise Exception("Dry run rollback")

        except Exception as e:
            if "Dry run rollback" not in str(e):
                self.stdout.write(self.style.ERROR(f"\nKey rotation failed: {e}"))
                self.stdout.write(self.style.ERROR("All changes have been rolled back."))
                raise CommandError(f"Key rotation failed: {e}")

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("KEY ROTATION SUMMARY"))
        self.stdout.write("=" * 50)
        
        total_updated = 0
        total_errors = 0
        for model_name, model_stats in stats.items():
            self.stdout.write(f"\n{model_name}:")
            self.stdout.write(f"  Processed: {model_stats['processed']}")
            self.stdout.write(f"  Updated:   {model_stats['updated']}")
            if model_stats['errors'] > 0:
                self.stdout.write(self.style.ERROR(f"  Errors:    {model_stats['errors']}"))
            total_updated += model_stats['updated']
            total_errors += model_stats['errors']

        self.stdout.write("\n" + "-" * 50)
        self.stdout.write(f"Total records updated: {total_updated}")
        
        if total_errors > 0:
            self.stdout.write(self.style.WARNING(f"Total errors: {total_errors}"))
            self.stdout.write(self.style.WARNING("Some records could not be decrypted. Check if old key is correct."))
        
        if not dry_run and total_errors == 0:
            self.stdout.write(self.style.SUCCESS("\nKey rotation completed successfully!"))
            self.stdout.write(self.style.WARNING("\nIMPORTANT: Update your FIELD_ENCRYPTION_KEY environment variable to the new key:"))
            self.stdout.write(f"  FIELD_ENCRYPTION_KEY={new_key}")
