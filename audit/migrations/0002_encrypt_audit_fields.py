
import clinic.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditlog',
            name='details',
            field=clinic.encrypted_fields.EncryptedTextField(blank=True, help_text='Encrypted details'),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='ip_address',
            field=clinic.encrypted_fields.EncryptedCharField(blank=True, help_text='Encrypted IP address', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='resource',
            field=clinic.encrypted_fields.EncryptedCharField(blank=True, help_text='Encrypted target resource', max_length=500),
        ),
    ]
