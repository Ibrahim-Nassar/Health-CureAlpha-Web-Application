
import clinic.encrypted_fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_encrypt_patient_profile_pii'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='customuser',
            name='customuser_email_ci_unique',
        ),
        migrations.AddField(
            model_name='customuser',
            name='email_hash',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='email',
            field=clinic.encrypted_fields.EncryptedCharField(max_length=500, verbose_name='email address'),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='first_name',
            field=clinic.encrypted_fields.EncryptedCharField(blank=True, max_length=500, verbose_name='first name'),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='last_name',
            field=clinic.encrypted_fields.EncryptedCharField(blank=True, max_length=500, verbose_name='last name'),
        ),
        migrations.AlterField(
            model_name='doctorprofile',
            name='specialization',
            field=clinic.encrypted_fields.EncryptedCharField(blank=True, help_text='Encrypted specialization', max_length=255),
        ),
    ]
